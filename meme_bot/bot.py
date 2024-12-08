import contextlib
import enum
from typing import List, Optional, cast

from colorama import just_fix_windows_console
import pyfiglet
from termcolor import colored, cprint


import asyncio
from asyncstdlib import enumerate

from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.rpc.responses import SubscriptionResult, LogsNotification # type: ignore
from solders.token.state import Mint # type: ignore
from solders.rpc.config import RpcTransactionLogsFilterMentions # type: ignore
from solders.account_decoder import UiTokenAmount # type: ignore

from spl.token.instructions import get_associated_token_address


from solana.rpc.async_api import AsyncClient
from solana.rpc.types import DataSliceOpts
from solana.rpc.websocket_api import connect, SolanaWsClientProtocol
from solana.rpc.core import RPCException

from solana.rpc.types import TxOpts
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
import websockets.exceptions
import websockets


from . import JupiterApi
from . import utils

import json

# use Colorama to make Termcolor work on Windows too
just_fix_windows_console()


(ENDPOINT_API, ENDPOINT_WSS) = utils.get_env_rpc_url()

class SaleType(enum.Enum):
    CAPPED="CAPPED"
    TIMER="TIMER"
    BOTH=""

WRAPPED_SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

DEBUG = True
TX_RETRIES = 3

class MemeBot:
    _bot_key: Keypair
    _bot_pk: Pubkey
    _meme_pk: Pubkey
    _target_addr: str
    _target_ata_pk: Optional[Pubkey]
    _token_program: Pubkey
    
    _mint_info: Mint
    _target_balance: Optional[UiTokenAmount]
    _purchased:bool
    _subscription_id:Optional[int]
    _mint_price: Optional[float]

    _timeout:int
    _sale_type:SaleType
    _min_profit:float
    _amount:int

    poll_interval:int
    
    def __init__(
            self, 
            *,
            bot_secret:str, 
            target_addr:str, 
            meme_addr:str,
            amount:int,
            sale_type: SaleType = SaleType.BOTH,
            timeout:int=5*60, #5 mins
            min_profit:float=1, #dollar
            poll_interval:int=5*50 #5 mins
        ):
        self._bot_key = Keypair.from_seed(
                    bytes.fromhex(bot_secret)
                )
        self._bot_pk = self._bot_key.pubkey()
        self._meme_pk = Pubkey.from_string(meme_addr)
        self._target_ata_pk = None # to be populated on init
        self._target_addr = target_addr
        self._target_balance = None
        self._amount = amount
        self._purchased = False
        self._sale_type = sale_type
        self._timeout = timeout
        self._min_profit = min_profit
        self._mint_price = None
        self._subscription_id = None
        self.poll_interval = poll_interval

    async def _init(self, client:AsyncClient):
        meme_acct_info = (await client.get_account_info(self._meme_pk)).value
        if not meme_acct_info:
            print("Meme coin does not exist")
            raise asyncio.CancelledError("Meme coin Invalid")

        self._token_program = meme_acct_info.owner
        
        # get token info
        self._mint_info = Mint.from_bytes(meme_acct_info.data)
        
        # get token price
        await self._refresh_mint_price()

        if not self._target_ata_pk:
            _target_pk = Pubkey.from_string(self._target_addr)
            self._target_ata_pk = get_associated_token_address(
                _target_pk,
                self._meme_pk,
                self._token_program
            ) if _target_pk.is_on_curve() else _target_pk
    
    async def _unsubscribe_from_log(self, websocket: SolanaWsClientProtocol):
        if self._subscription_id != None:
            await websocket.logs_unsubscribe(self._subscription_id)
            self._subscription_id = None

    async def _subscribe_to_log(self, websocket: SolanaWsClientProtocol):
        await websocket.logs_subscribe(
                RpcTransactionLogsFilterMentions(self._target_ata_pk)
            )

    async def _wait_for_target(self, client: AsyncClient, websocket: SolanaWsClientProtocol):
        target_info = await client.get_account_info(self._target_ata_pk, data_slice=DataSliceOpts(length=0, offset=0))
        if target_info.value:
            print("Target wallet exists")
            return True
        
        # Catch event that mentions the wallet
        await websocket.recv()
        print("[Bot-Logs]=> Target wallet active")
        # Check infinitely if account is ready to be used a token account
        while True:
            target_balance = (await client.get_token_account_balance(self._target_ata_pk)).value
            if target_balance:
                break
            await asyncio.sleep(30) # wait for 30 seconds
        return False
    
    async def _target_balance_difference(self, client: AsyncClient):
        old_target_balance = self._target_balance
        if old_target_balance:
            target_balance = await self._refresh_target_balance(client)
            print("Target balance is currently %s"%target_balance.ui_amount_string)
            return int(target_balance.amount) - int(old_target_balance.amount)
        return 0
    
    async def _mint_price_difference(self):
        old_mint_price = self._mint_price
        if old_mint_price != None:
            mint_price = await self._refresh_mint_price()
            print("Mint price is currently %f" % mint_price)
            return mint_price - old_mint_price
        return 0

    async def _buy_handler(self, client: AsyncClient, websocket: SolanaWsClientProtocol):
        target_already_exist = await self._wait_for_target(client, websocket)
        target_balance = await self._refresh_target_balance(client)
        # make purchase here if initial balance is greater than zero after account creation
        if not target_already_exist and target_balance.ui_amount > 0:
            print("Target was created newly with token")
            await self._buy()
        else:
            async for idx, [msg] in enumerate(websocket):
                msg_ = cast(LogsNotification, msg)
                print(f"[BOT-LOG]: {msg_.result.value.signature} mentions Target {self._target_ata_pk}")
                balance_change = await self._target_balance_difference(client)
                if balance_change > 0:
                    print("Target balance has increased")
                    print("Purchase now")
                    await self._buy(client)
                    break
                elif balance_change < 0:
                    print("Target balance has descrease due to sales of meme")
                    print("You might want to consider terminating this task")
        
    async def _buy_task(self, client: AsyncClient):
        _shutdown = False
        
        async for websocket in connect(ENDPOINT_WSS):
            try:
                
                if self._purchased: # Purchase already make continue from last checkpoint
                    break
                # subscribe to log for target token account
                
                await self._subscribe_to_log(websocket)
                print("HERE")
                print(f"[BOT]: Log Subscribe to {self._target_ata_pk}")
                resp = await websocket.recv()
                self._subscription_id = cast(SubscriptionResult, resp[0]).result
                await self._buy_handler(client, websocket)
            except asyncio.CancelledError:
                print("Cancelled")
                _shutdown = True
            except websockets.exceptions.ConnectionClosed:
                self._subscription_id = None
                print("Websocket Failed")
                continue
            finally:
                with contextlib.suppress(websockets.exceptions.WebSocketException):
                    await self._unsubscribe_from_log(websocket)
                break
        
        if _shutdown:
            pass
            #raise asyncio.CancelledError()
    
    async def _buy(self, client:AsyncClient):
        print("Making purchase here")
        meme_addr = str(self._meme_pk)
        retries = TX_RETRIES

        while retries > 0 and not self._purchased:
            try:           
                resp = await JupiterApi.swap_tx(
                    inputMint=WRAPPED_SOL,
                    outputMint=meme_addr,
                    amount=self._amount,
                    payer_pk_sk=self._bot_key
                )
                raw_tx = resp["txn"]
                if raw_tx:
                    if DEBUG:
                        result = await client.simulate_transaction(txn=raw_tx)
                        print("Errors => ", result.value.err)
                        print("Unit Consumd => ", result.value.units_consumed)
                    else:
                        refresh_task = asyncio.create_task(self._refresh_mint_price())
                        result = await JupiterApi.sendAndConfirmTransaction(
                            client,
                            raw_tx,
                            opts=JupiterApi.opts(),
                            verbose=True
                        )
                        print(result[0])
                        self._purchased = True
                        await refresh_task
            except RPCException as e:
                print(e.args[0])
                retries -= 1
                continue

            break

    
    async def _sell_task(self, client: AsyncClient):

        if self._sale_type == SaleType.TIMER:
            await asyncio.sleep(self._timeout)
            await self._sell(client)
        
        elif self._sale_type == SaleType.CAPPED:
            while True:
                mint_price_diff = await self._mint_price_difference()
                if mint_price_diff >= self._min_profit:
                    await self._sell(client)
                    break
                asyncio.sleep(self.poll_interval)
        
        else:
            with contextlib.suppress(asyncio.TimeoutError):
                async with asyncio.timeout(self._timeout) as _timeout:
                    while True:
                        mint_price_diff = await self._mint_price_difference()
                        if mint_price_diff >= self._min_profit:
                            break
                        asyncio.sleep(self.poll_interval)
            print("Sell now")
            await self._sell(client)
            
    async def _sell(self, client:AsyncClient):
        print("Making sales here")
        meme_addr = str(self._meme_pk)
        retries = TX_RETRIES
        _bot_ata_pk = utils.get_ata_pub_key(
            self._bot_pk,
            self._meme_pk,
            self._token_program
        )
        token_balance = await client.get_token_account_balance(_bot_ata_pk)
        _is_sold = False
        while retries > 0 and not _is_sold:
            try:           
                resp = await JupiterApi.swap_tx(
                    inputMint=meme_addr,
                    outputMint=WRAPPED_SOL,
                    amount=token_balance,
                    payer_pk_sk=self._bot_key
                )
                raw_tx = resp["txn"]
                if raw_tx:
                    if DEBUG:
                        result = await client.simulate_transaction(txn=raw_tx)
                        print("Errors => ", result.value.err)
                        print("Unit Consumd => ", result.value.units_consumed)
                    else:
                        result = await JupiterApi.sendAndConfirmTransaction(
                            client,
                            raw_tx,
                            opts=JupiterApi.opts(),
                            verbose=True
                        )
                        print(result[0])
                        _is_sold = True
            except RPCException as e:
                print(e.args[0])
                retries -= 1
                continue
            break


    async def _run(self, client: AsyncClient):
        print("[BOT STARTED]")
        await self._buy_task(client)
        
        if self._purchased:
            await self._sell_task(client)

    async def _refresh_target_balance(self, client:AsyncClient):
        self._target_balance = (await client.get_token_account_balance(self._target_ata_pk)).value
        return self._target_balance
    
    async def _refresh_mint_price(self):
        meme_addr = str(self._meme_pk)
        resp = await JupiterApi.get_token_price(meme_addr)
        if resp and resp['data'][meme_addr]['price']:
            self._mint_price = float(resp['data'][meme_addr]['price'])
        return self._mint_price
    
    async def _tell_price(self):
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        jupiter = JupiterApi()
        res = await jupiter.get_token_price(
            SOL, USDC,
            vsToken=USDC
        )
        print(res)

    async def __call__(self,  *args, **kwargs):
        async with AsyncClient(ENDPOINT_API) as client:
            if await client.is_connected():
                
                await self._init(client)

                print("""BOT WALLET: %s
                    TARGET WALLET: %s
                    MEME COIN: %s"""%(self._bot_pk, self._target_ata_pk, self._meme_pk))
                
                await self._run(client)
            else:
                print("[BOT]: Failed to connect to rpc")


def print_screen():
    cprint(pyfiglet.figlet_format("MEMEBOT", font="larry3d"), "blue", attrs=["bold"], end="")
    cprint(pyfiglet.figlet_format("-- Meme Bot Started --", font="term"), "blue", attrs=["bold", "underline"])

#account
TARGET_ADDR = "87esLg2WdmndkRjYrxNene4cXrGsSAeVyQxAG9tcRh1m"
BOT_KEY = "6878f7061c40114ce10b7af8fb4469d98a9bb7957a56fd8c43203ad545199014"
#token

MEME_ADDR = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
#settings
SALE_TIMEOUT = 2 * 60 # 3 minutes
MIN_PROFIT_AMOUNT = 200 # in USD


async def main():
    
    bot = MemeBot(
        bot_secret=BOT_KEY,
        target_addr=TARGET_ADDR,
        meme_addr=MEME_ADDR,
        amount=utils.sol_to_lamport(0.05),
        timeout=SALE_TIMEOUT
    )
    bot_task = asyncio.create_task(bot())
    await bot_task
    print("Done")


def start():
    meme_addr=input(colored("Enter meme coin address =>", "magenta"))
    target_addr = input(colored("Enter target address =>", "blue"))
    amount=input(colored("Enter amount in sol to purchase=>", "yellow"))
    amount = utils.sol_to_lamport(float(amount))
    timeout=input(colored("Enter the sale time interval from sales in seconds=>"))
    timeout = int(timeout)
    capped_amount = input(colored("Enter the sale capped amount from sales in dollars=>", "yellow"))
    capped_amount = float(capped_amount)
    bot_secret= input(colored("Enter Bot SecretKey=>", "red"))
    sale_type = input(colored("Enter T for timed interval or C for capped amount profit strategy on meme coin sales=>", "yellow"))
    sale_type = sale_type.lower()
    data = dict(
        target_addr=target_addr,
        meme_addr=meme_addr,
        amount=amount,
        timeout=timeout,
        min_profit=capped_amount,
        bot_secret=bot_secret,
        sale_type= SaleType.TIMER if sale_type=='T' else SaleType.CAPPED
    )
    
    bot = MemeBot(
        **data,
        poll_interval=1*60 # 1 mins
    )

    print_screen()
    asyncio.run(bot())

if __name__ == '__main__':
    start()