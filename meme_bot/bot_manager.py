import functools
import itertools
import asyncstdlib
import contextlib
from typing import Dict, List, cast
import asyncio
from solana.rpc.websocket_api import connect, SolanaWsClientProtocol
from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.rpc.responses import SubscriptionResult, ProgramNotificationJsonParsed, RpcKeyedAccountJsonParsed # type: ignore
from solana.rpc import types
import websockets.exceptions
from solana.rpc.async_api import AsyncClient
from spl.token.constants import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from .bot import MemeBot, SaleType # type: ignore
from . import USDC, DEBUG, BotStatus, AccountInfo, utils, get_redis_client, REDIS_MINTS_KEY

(ENDPOINT_API, ENDPOINT_WSS) = utils.get_env_rpc_url()

class BotManager:
    # -- Keypair & Pubkey
    _bot_key: Keypair
    _bot_pk: Pubkey

    # -- Options
    _sale_type:SaleType
    _timeout:int
    _min_profit:float
    _poll_interval:int
    _amount:int
    _program_id: Pubkey

    # -- internal
    _subscription_ids:List[int] # programId to subscription id

    _trade_lock:asyncio.Lock # to be used to ensure transation are sent one at a time

    def __init__(
            self, 
            *,
            target_addr:str,
            bot_secret:str, 
            amount:int = 5,  #$5
            sale_type: SaleType = SaleType.BOTH,
            timeout:int=5*60, #5 mins
            min_profit:float=1, #dollar
            poll_interval:int=5*60 #5 mins
        ):
        
        self._bot_key = Keypair.from_seed(
                    bytes.fromhex(bot_secret)
                ) if len(bot_secret) == 64 else Keypair.from_base58_string(bot_secret)
        
        self._bot_pk = self._bot_key.pubkey()
        self._target_pk = Pubkey.from_string(target_addr)

        self._amount = amount
        self._sale_type = sale_type
        self._timeout = timeout
        self._min_profit = min_profit
        self._poll_interval = poll_interval
        
        self._subscription_ids = []
        
        self._trade_lock = asyncio.Lock() 

    async def _spawn_bot(self, ata:AccountInfo, skip_success:bool=True, force:bool=False):
        # Spawn a bot
        if DEBUG:
            ata = ata._replace(mint=Pubkey.from_string(USDC))
        async with get_redis_client() as redis_client:
            existing_bot_status = await redis_client.hget(str(ata.mint), "status")
            if existing_bot_status:
                existing_bot_status = BotStatus(existing_bot_status)
            
            bot_status = existing_bot_status or BotStatus.IDLE
            
            if bot_status == BotStatus.SUCCESS:
                force = (not skip_success) and force
                # skip bot creation already sold here
                print(f"{ata.mint} skip bot creation already sold here")
            
            elif bot_status == BotStatus.STARTED or force:
                # spawn bot with skip purchase and continue to sale
                if bot_status == BotStatus.STARTED:
                    print(f"{ata.mint} spawn bot with skip purchase and continue to sale")
                else:
                    print(f"{ata.mint} Spawning new bot for a new task")
                #spawn bot
                bot = MemeBot(
                        lock=self._trade_lock,
                        bot_secret=self._bot_key.secret().hex(),
                        target_account_info=ata,
                        amount=self._amount,
                        sale_type=self._sale_type,
                        timeout=self._timeout,
                        min_profit=self._min_profit,
                        poll_interval=self._poll_interval,
                        skip_purchase=bot_status == BotStatus.STARTED
                    )
                try:
                    await bot()
                except Exception as e:
                    print("Error in bot: ", e)
            
            else:
                # spawn bot with idle start but could not make purchase
                print(f"{ata.mint} spawn bot is idle and not active") # would decide later whether to spawn a bot on this or not
        
    
    @staticmethod
    def to_account_info(result: RpcKeyedAccountJsonParsed):
        data =  AccountInfo(
            result.account.owner,
            result.account.data.parsed["info"]["owner"],
            result.pubkey,
            result.account.data.parsed["info"]["mint"],
            int(result.account.data.parsed["info"]["tokenAmount"]["amount"])
        )
        return data

    @classmethod
    async def get_token_accounts(cls, client:AsyncClient, program_id:Pubkey, target_pk:Pubkey):
        resp = await client.get_token_accounts_by_owner_json_parsed(
                owner=target_pk,
                opts=types.TokenAccountOpts(
                    program_id=program_id
                )
            )

        _target_ata_info = list(
                    map(
                        lambda result:cls.to_account_info(result), 
                    resp.value)
        )

        return _target_ata_info
            
    async def _subscribe_token_program(self, websocket: SolanaWsClientProtocol, _programId:Pubkey):
        # Subscribe to program notifications (Token Program)
        await websocket.program_subscribe(
            _programId,  # Token program ID
            encoding="jsonParsed",
            filters=[
                types.MemcmpOpts(
                    offset=32,
                    bytes=str(self._target_pk)
                ) # Owner field in SPL token account
            ]
        )
        print(f"[BOT]:[{_programId}]:Program Subscribed")
 
    async def _unsubscribe_token_program(self, websocket: SolanaWsClientProtocol):
        for sub_id in self._subscription_ids:
            await websocket.program_unsubscribe(sub_id)
        self._subscription_ids.clear()

    async def _resume_task(self, program_id:Pubkey):
        # to be populated on init
        print("Trying to resume task for program ", program_id)
        async with get_redis_client() as redis_client:
            async with asyncio.TaskGroup() as tg:
                async with AsyncClient(ENDPOINT_API) as client:
                    # 1. Get the token accounts for the target wallet
                    try:    
                        _target_ata_info = await self.get_token_accounts(
                            client,
                            program_id,
                            self._target_pk
                        )
                        
                        target_mints = list(map(lambda info:info.mint, _target_ata_info))
                        existing_tokens =  await redis_client.smembers(REDIS_MINTS_KEY)
                        is_members  = list(map(lambda x: x in existing_tokens, target_mints))
                        
                        for i, is_member in enumerate(is_members):
                            if is_member:
                                print(f"Target mint {target_mints[i]} already in bot skipped or resume")
                            else:
                                print(f"Target mint {target_mints[i]} scheduled to run newly")
                                    
                        for account in _target_ata_info:
                            # check for existing bot status running for the current account
                             tg.create_task(
                                    self._spawn_bot(account)
                                )
                    except Exception as e:
                        print("Failed to Resume Task with error: ", e)
        print("RESUME TASK END for program ", program_id)

    async def _watch_task(self, program_ids:List[Pubkey]):
        print("Watching for token balance update")
        _target_ata_map = dict()
        
        async with AsyncClient(ENDPOINT_API) as client:
            # 1. Get the token accounts for the target wallet
            # print("Getting target token account")
            _target_atas = itertools.chain.from_iterable(
                await asyncio.gather(
                    *map(
                        lambda program_id:
                            self.get_token_accounts(
                            client,
                            program_id,
                            self._target_pk
                        ),
                        program_ids
                    )
                )
            )
            
            
            _target_ata_map: Dict[str, AccountInfo] = functools.reduce(
                lambda atas_map, ata: {**atas_map, (str(ata.mint)):ata},
                _target_atas,
                _target_ata_map
            )
        
        async with get_redis_client() as redis_client:  
            async with asyncio.TaskGroup() as tg:
                try:
                    async for websocket in connect(ENDPOINT_WSS):
                        with contextlib.suppress(websockets.exceptions.ConnectionClosed):
                            await asyncio.gather(*[
                                self._subscribe_token_program(websocket, program_id) for program_id in program_ids
                            ])
                            print("Subscribed to Token Program")
                            async for idx, [msg_] in asyncstdlib.enumerate(websocket):
                                print(f"Got Event {idx}")
                                if isinstance(msg_, SubscriptionResult):
                                    msg = cast(SubscriptionResult, msg_)
                                    self._subscription_ids.append(msg.result)
                                    print("Subscription Event:", msg.result)
                                elif isinstance(msg_, ProgramNotificationJsonParsed):
                                    msg = cast(ProgramNotificationJsonParsed, msg_)
                                    if not msg.subscription in self._subscription_ids:
                                        print("Adding subscription ID into box ", msg.subscription)
                                        self._subscription_ids.append(msg.subscription)
                                    ata = self.to_account_info(msg.result.value)
                                    print("Program Event:", ata)
                                    mint_pk = str(ata.mint)
                                    if mint_pk in _target_ata_map:
                                        if ata.amount > _target_ata_map[mint_pk].amount:
                                            # for balance increase
                                            #spawn bot
                                            tg.create_task(
                                                self._spawn_bot(ata, force=True)
                                            )
                                        elif ata.amount < _target_ata_map[mint_pk].amount:
                                            # for balance decrease
                                            pass

                                        else:
                                            # No balance increase just account change
                                            pass
                                    else:
                                        # account not present before
                                        # new account created
                                        _target_ata_map[mint_pk] = ata
                                        await redis_client.sadd(REDIS_MINTS_KEY, mint_pk) # add mint to tokens set
                                        if ata.amount > 0: # check if amount is increased
                                            # spawn bot
                                            tg.create_task(
                                                self._spawn_bot(ata),
                                                force=True
                                            )
                                    
                                    _target_ata_map[mint_pk] = ata # update local map with new account info
                                else:
                                    print("Unknown Event:", msg_)                   
                        self._subscription_ids.clear() # Clear subscription IDS HERE
                
                except asyncio.CancelledError:
                    with contextlib.suppress(websockets.exceptions.WebSocketException):
                        await self._unsubscribe_token_program(websocket) # closing websocket
                    
                except Exception as e:
                    # when the error is different
                    print("[ERROR-OCCURED]:", e)
                finally:
                    print("Watcher Ended")
                    
    async def run(self):
        try:
            async with asyncio.TaskGroup() as tg: 
                tg.create_task(self._resume_task(TOKEN_2022_PROGRAM_ID))
                tg.create_task(self._resume_task(TOKEN_PROGRAM_ID))
                tg.create_task(self._watch_task([TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID]))
            
        except Exception as e:
            print("Exception in main", e)
        finally:
            print("RUN END")

# 1. Get the token accounts for the target wallet
    # save mint 
# 2. Subscribe to the token account for the target wallet
    # if the balance of the token account:
        # increases spawn a bot
    # else if decreases 
        # do nothiing
    # unsubscribe from the account
    # 
# 3. Watch out for ata account creation for target wallet
    # spawn a bot
# 4. On Seeing an ata subscribe to the token account

#if condition:
    # if new mint not already purchased or sold:
        # save mint
        # spawn bot
            # initial price
            # purchase mint
            # price after purchase would be intial price + current price / 2
            # wait for timeout
                # while True:
                    # check price
                    # if increase to capped:
                        # sell
                    # else
                        # sleep for poll intervale
