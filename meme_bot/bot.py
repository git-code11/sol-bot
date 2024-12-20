import logging
import contextlib
import datetime
from typing import Optional, cast
import asyncio
import inquirer
import redis
import redis.exceptions
from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.transaction_status import TransactionStatus # type: ignore
from solders.token.state import Mint # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.rpc.core import RPCException
from solana.rpc.async_api import AsyncClient
from . import TX_RETRIES, USDC, WRAPPED_SOL, AccountInfo, BotStatus, JupiterApi, SaleType, get_redis_client, print_screen
from . import utils, DEBUG, LAG_TIME

logger = logging.getLogger(__name__)


#(ENDPOINT_API, ENDPOINT_WSS) = utils.get_env_rpc_url("prod")
(ENDPOINT_API, ENDPOINT_WSS) = utils.get_env_rpc_url("prod" if DEBUG else None)

class MemeBot:
    _bot_key: Keypair
    _bot_pk: Pubkey
    _target_ata_info: AccountInfo

    _mint_info: Mint
    _mint_price: Optional[float]

    _purchased:bool
    
    _timeout:int
    _sale_type:SaleType
    _min_profit:float
    _amount:int
    poll_interval:int
    
    def __init__(
            self, 
            *,
            lock: asyncio.Lock,
            bot_secret:str, 
            target_account_info: AccountInfo,
            amount:int,
            sale_type: SaleType = SaleType.BOTH,
            timeout:int=5*60, #5 mins
            min_profit:float=1, #dollar
            poll_interval:int=2*50, #2 mins
            skip_purchase:bool=False
        ):
        self._lock = lock
        self._bot_key = Keypair.from_seed(
                    bytes.fromhex(bot_secret)
                )
        self._bot_pk = self._bot_key.pubkey() if not DEBUG else Pubkey.from_string("7rhxnLV8C77o6d8oz26AgK8x8m5ePsdeRawjqvojbjnQ")
        self._target_ata_info = target_account_info if not DEBUG else target_account_info._replace(mint=Pubkey.from_string(USDC))
        self._amount = amount
        self._purchased = skip_purchase
        self._sale_type = sale_type
        self._min_profit = min_profit if not DEBUG else 0.000002
        self._mint_price = None
        self._timeout = timeout if not DEBUG else 30
        self.poll_interval = poll_interval if not DEBUG else 12

    async def recover(self):
        bot_status = None
        async with get_redis_client() as redis_client:
            # update the 
            data = await redis_client.hgetall(str(self._target_ata_info.mint))
            if data:
                bot_status = data.get('status')
                if bot_status:
                    bot_status = BotStatus(bot_status)
                if bot_status == BotStatus.STARTED:
                    self._purchased = True
        return bot_status
        
    async def _init(self, client:AsyncClient):
        try:
            meme_acct_info = (await client.get_account_info(self._target_ata_info.mint)).value
            if not meme_acct_info:
                logging.critical("Meme coin does not exist")
                raise asyncio.CancelledError("Meme coin Invalid")
            
            # get token info
            self._mint_info = Mint.from_bytes(meme_acct_info.data)
            self._target_ata_info = self._target_ata_info._replace(
                program_id=meme_acct_info.owner
            )
            # get token price
            await self._refresh_mint_price()
        except Exception as e:
            logger.critical(f"ERRROR in INIT: {e}")
            raise asyncio.CancelledError(f"[INIT-BOT]: Error occured: {e}")

    async def _refresh_mint_price(self):
        meme_addr = str(self._target_ata_info.mint)
        resp = await JupiterApi.get_token_price(
            meme_addr,
            #vsToken=USDC
            )
        
        if resp and resp['data'][meme_addr]:
            self._mint_price = float(resp['data'][meme_addr]['price'])
        else:
            logging.critical("No price for token please kindly check jupiter in token exists there and contact the programmer")
            raise asyncio.CancelledError("No price for token")
        return self._mint_price
    
    async def _mint_price_difference(self):
        old_mint_price = self._mint_price
        if old_mint_price != None:
            mint_price = await self._refresh_mint_price()
            meme_addr = str(self._target_ata_info.mint)
            logging.info(f"[{meme_addr}]:Mint price is currently {mint_price}")
            return mint_price - old_mint_price
        return 0
      
    async def _buy_task(self, client:AsyncClient):
        meme_addr = str(self._target_ata_info.mint)
        logging.info(f"[{meme_addr}]:Making purchase here, Amount: [{self._amount}]")
        retries = TX_RETRIES
        raw_tx = None
        #print("Amount ", self._amount)
        while retries > 0:
            try:
                with contextlib.suppress(RPCException, redis.exceptions.ConnectionError):
                    if not self._purchased:
                        resp = await JupiterApi.swap_tx(
                            inputMint=WRAPPED_SOL,
                            outputMint=meme_addr,
                            amount=self._amount,
                            payer_pk_sk=self._bot_pk if DEBUG else self._bot_key
                        )
                        raw_tx = resp["txn"]
                
                    if raw_tx:
                        if DEBUG:
                            async with self._lock:
                                await asyncio.sleep(LAG_TIME) # lag the call for payment
                                result = await client.simulate_transaction(txn=raw_tx)
                            logging.info(f"[{meme_addr}]: Transaction error: {result.value.err}")
                            logging.info(f"[{meme_addr}]: Unit Consumd: {result.value.units_consumed}")
                            #print("Unit Consumd => ", result.value.units_consumed)
                            if result.value.err:
                                # error occured retry
                                logger.error(f"[{meme_addr}]: Error occured in simulated BUY TX ")
                            else:
                                self._purchased = True
                        else:
                            async with self._lock:
                                await asyncio.sleep(LAG_TIME) # lag the call for payment
                                result = await JupiterApi.sendAndConfirmTransaction(
                                    client,
                                    raw_tx,
                                    opts=JupiterApi.opts(),
                                    verbose=True
                                )
                            tx_status = cast(TransactionStatus, result[1])
                            logging.info(f"[{meme_addr}]: Transaction error: {tx_status.err}")
                            logging.info(f"[{meme_addr}]: Transaction status: {tx_status.err}")
                            # print("Tx Status: ", tx_status.confirmation_status)
                            # print("Errors=> ", tx_status.err)
                            if tx_status.err:
                                logger.error('An error occured in Buy Tx')
                            else:
                                self._purchased = True
                        logging.info(f"Purchase Allowed {self._purchased}")
                        if self._purchased:
                            await self._refresh_mint_price()
                            async with get_redis_client() as redis_client:
                                await redis_client.hmset(
                                    str(self._target_ata_info.mint),
                                    dict(
                                        buy_price=self._mint_price,
                                        buy_amount=self._amount,
                                        status=BotStatus.STARTED.value,
                                        buy_time=datetime.datetime.now().timestamp()
                                    )
                                )
                            logging.info("Purchase completed")
                            break

            except Exception as e:
                logger.error(f"Error Occured during buy {e}")
                #continue
            finally:
                if not self._purchased:
                    logger.info(f"[{meme_addr}]: Retrying BUY :RETRY LEFT = {retries}")
                    retries -= 1
                    await asyncio.sleep(60) # wait for 60seonds

    async def _sell_task(self, client: AsyncClient):

        if self._sale_type == SaleType.TIMER:
            await asyncio.sleep(self._timeout)
            await self._sell(client)
        
        elif self._sale_type == SaleType.CAPPED:
            while True:
                mint_price_diff = await self._mint_price_difference()
                if mint_price_diff >= self._min_profit:
                    logger.info(f"Profit reached {mint_price_diff}")
                    await self._sell(client)
                    break
                await asyncio.sleep(self.poll_interval)

        else:
            #print("Poll Interval ", self.poll_interval)
            #print("Timeout ", self._timeout)
            with contextlib.suppress(asyncio.TimeoutError):
                async with asyncio.timeout(self._timeout):
                    while True:
                        mint_price_diff = await self._mint_price_difference()
                        if mint_price_diff >= self._min_profit:
                            logger.info(f"Profit reached {mint_price_diff}")
                            break
                        await asyncio.sleep(self.poll_interval)
            logger.debug("Selling now")
            await self._sell(client)
            
    async def _sell(self, client:AsyncClient):
        logger.info("Making sales here")
        meme_addr = str(self._target_ata_info.mint)
        retries = int(TX_RETRIES * 1.5) # retries for sale 
        _bot_ata_pk = utils.get_ata_pub_key(
            self._bot_pk,
            self._target_ata_info.mint,
            self._target_ata_info.program_id
        )
        token_balance = await client.get_token_account_balance(_bot_ata_pk)
        token_balance = int(token_balance.value.amount)//(1000 if DEBUG else 1)
        logger.info(f"Token Amount in sale {token_balance}")
        _is_sold = False
        raw_tx = None
        while retries > 0:
            try:
                with contextlib.suppress(RPCException, redis.exceptions.RedisError):
                    if not _is_sold: 
                        resp = await JupiterApi.swap_tx(
                            inputMint=meme_addr,
                            outputMint=WRAPPED_SOL,
                            amount=token_balance,
                            payer_pk_sk=self._bot_pk if DEBUG else self._bot_key
                        )
                        raw_tx = resp["txn"]
                    if raw_tx:
                        if DEBUG:
                            async with self._lock:
                                await asyncio.sleep(LAG_TIME) # lag the call for payment
                                result = await client.simulate_transaction(txn=raw_tx)
                            logger.info(f"Errors => {result.value.err}")
                            logger.info(f"Unit Consumd => {result.value.units_consumed}")
                            if result.value.err:
                                # error occured retry
                                logger.error("Error occured in simulated SELL TX")
                            else:
                                _is_sold = True
                        else:
                            async with self._lock:
                                await asyncio.sleep(LAG_TIME) # lag the call for payment
                                result = await JupiterApi.sendAndConfirmTransaction(
                                    client,
                                    raw_tx,
                                    opts=JupiterApi.opts(),
                                    verbose=True
                                )                    
                            tx_status = cast(TransactionStatus, result[1])
                            logger.info("Tx Status: {tx_status.confirmation_status}")
                            logger.info("Errors=> {tx_status.err}")
                            if tx_status.err:
                                logger.error('An error occured in Sell Tx')
                            else:
                                _is_sold = True
                        
                        if _is_sold:
                            async with get_redis_client() as redis_client:
                                await redis_client.hmset(
                                    str(self._target_ata_info.mint),
                                    dict(
                                        sell_price=self._mint_price,
                                        sell_amount=token_balance,
                                        status=BotStatus.SUCCESS.value,
                                        sell_time=datetime.datetime.now().timestamp()
                                    )
                                )
                            logger.info("Sales completed")
                            break

            except Exception as e:
                logger.error(f"Error Occured during sell {e}")
                #continue
            finally:
                if not _is_sold:
                    logger.info(f"Retrying Sales RETRY LEFT = {retries}")
                    retries -= 1
                    await asyncio.sleep(60) # wait for 60seonds
            
    async def _run(self, client: AsyncClient):
        logger.info("[BOT STARTED]")
        if not self._purchased:
            await self._buy_task(client)
        
        if self._purchased:
            await self._sell_task(client)

 
    async def __call__(self, skip_recover=True):
        logger.debug("Bot target ATA", self._target_ata_info)
        
        async with AsyncClient(ENDPOINT_API) as client:
            
            if await client.is_connected():      
                     
                logger.info("""BOT WALLET: %s\nMEME COIN: %s"""%(self._bot_pk, self._target_ata_info.mint))
                
                execute_bot = True
                if not skip_recover:
                    execute_bot = await self.recover() != BotStatus.SUCCESS

                if execute_bot:
                    await self._init(client)
                    await self._run(client)
                else:
                    logger.info("Bot already ran for this meme")
            else:
                logger.critical("[BOT]: Failed to connect to rpc")


def start():
    non_empty_validator = lambda _, x: len(x)>0
    questions = [
        inquirer.Text("meme_addr", 
                      message="Enter meme coin address", 
                      validate=non_empty_validator, 
                      default="7WjqfEHWGExm1Gz3F3EUQz1pCSTjgCzJ83YVeE57hQBp"
                      ),
        inquirer.Text("target_addr", 
                      message="Enter target address", 
                      validate=non_empty_validator,
                      default="87esLg2WdmndkRjYrxNene4cXrGsSAeVyQxAG9tcRh1m"),
        inquirer.Text("amount", 
                      message="Enter amount in sol to purchase", 
                      validate=non_empty_validator, 
                      default=0.001),
        inquirer.Text("timeout", 
                      message="Enter the sale time interval from sales in seconds", 
                      validate=non_empty_validator, 
                      default=30),
        inquirer.Text("min_profit", 
                      message="Enter the profit amount for sales in dollars", 
                      validate=non_empty_validator, 
                      default=2.75),
        inquirer.Text("poll_interval", 
                      message="Enter Polling Interval in seconds", 
                      validate=non_empty_validator, 
                      default=12),
        inquirer.Text("bot_secret", 
                      message="Enter Bot SecretKey", 
                      validate=non_empty_validator,
                      default="8e41ad5b7a6c5e9a7cee9d3b46a9c34bf2ac5efeb1fcfc9b62522c0d862ceb24"),
        inquirer.Checkbox(
            "sale_type",
            message="Select the meme coin sales strategy?",
            choices=[
                ("Timed Interval", SaleType.TIMER),
                ("Capped Amount", SaleType.CAPPED),
                ("Combined Strategy", SaleType.BOTH),
            ],
            default=[SaleType.BOTH]
        ),
    ]
        
    data = inquirer.prompt(questions)
    # preprocess
    data['amount'] = utils.sol_to_lamport(float(data['amount']))
    data['timeout'] = int(data['timeout'])
    data['min_profit'] = float(data['min_profit'])
    data['sale_type'] = data['sale_type'][0]
    data['poll_interval'] = int(data['poll_interval'])

    ata = AccountInfo(
        utils.TOKEN_2022_PROGRAM_ID,
        Pubkey.from_string(data['target_addr']),
        utils.get_associated_token_address(
            Pubkey.from_string(data['target_addr']),
            Pubkey.from_string(data['meme_addr']),
            utils.TOKEN_2022_PROGRAM_ID,
        ),
        Pubkey.from_string(data['meme_addr']),
        17
    )
    wallet_lock = asyncio.Lock()
    bot = MemeBot(
        lock=wallet_lock,
        bot_secret=data['bot_secret'],
        target_account_info=ata,
        amount=data['amount'],
        sale_type=data['sale_type'],
        timeout=data['timeout'],
        min_profit=data['min_profit'],
        poll_interval=data['poll_interval']
    )

    print_screen()
    asyncio.run(bot())

if __name__ == '__main__':
    start()