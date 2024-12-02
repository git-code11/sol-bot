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
import websockets


from solana.rpc.types import TxOpts
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed

from jupiter_python_sdk.jupiter import Jupiter, Jupiter_DCA

from . import JupiterApi
from . import utils

import json

# use Colorama to make Termcolor work on Windows too
just_fix_windows_console()


ENDPOINT_API = utils.get_env_rpc_url()
ENDPOINT_WSS = "wss://api.devnet.solana.com"

class MemeBot:
    _bot_key: Keypair
    _bot_pk: Pubkey
    _meme_pk: Pubkey
    _target_addr: str
    _target_ata_pk: Optional[Pubkey]
    _token_program: Pubkey
    
    _mint_info: Mint

    _timeout:int
    _target_balance: Optional[UiTokenAmount]
    _purchased:bool
  
    
    def __init__(self, bot_secret:str, target_addr:str, meme_addr:str, timeout:int):
        self._bot_key = Keypair.from_seed(
                    bytes.fromhex(bot_secret)
                )
        self._bot_pk = self._bot_key.pubkey()
        self._meme_pk = Pubkey.from_string(meme_addr)
        self._target_ata_pk = None # to be populated on init
        self._target_addr = target_addr
        self._target_balance = None
        self._timeout = timeout
        self._purchased = False

    async def _init(self, client:AsyncClient):
        meme_acct_info = (await client.get_account_info(self._meme_pk)).value
        if not meme_acct_info:
            print("Meme coin does not exist")
            raise asyncio.CancelledError("Meme coin Invalid")

        self._token_program = meme_acct_info.owner

        # get token info
        self._mint_info = Mint.from_bytes(meme_acct_info.data)
        
        if not self._target_ata_pk:
            _target_pk = Pubkey.from_string(self._target_addr)
            self._target_ata_pk = get_associated_token_address(
                _target_pk,
                self._meme_pk,
                self._token_program
            ) if _target_pk.is_on_curve() else _target_pk
        
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
            target_balance = (await client.get_token_account_balance(self._target_ata_pk)).value
            print("Target balance is currently %s"%target_balance.ui_amount_string)
            return int(target_balance.amount) - int(old_target_balance.amount)
        return 0
    
    async def _buy_handler(self, client: AsyncClient, websocket: SolanaWsClientProtocol):
        target_already_exist = await self._wait_for_target(client, websocket)
        target_balance = await self._refresh_target_balance(client)
        # make purchase here if initial balance is greater than zero after account creation
        if not target_already_exist and target_balance.ui_amount > 0:
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

    async def _sell_handler(self, client: AsyncClient, websocket: SolanaWsClientProtocol):
        try:
            async with asyncio.timeout(self._timeout):
                async for idx, [msg] in enumerate(websocket):
                    msg_ = cast(LogsNotification, msg)
                    print(f"[BOT-LOG]: {msg_.result.value.signature} mentions Target {self._target_ata_pk}")
                    balance_change = await self._target_balance_difference(client)
                    if balance_change < 0:
                        print("Target balance has decreased")
                        print("Sell now")
                        await self._sell(client)
                        break
        except asyncio.TimeoutError:
            print("Making sales immediately now")
            print("Sell now")
            await self._sell(client)

    async def _buy(self, client:AsyncClient):
        print("Making purchase here")
        self._purchased = True
        pass

    async def _sell(self, client:AsyncClient):
        print("Making sale here")
        pass

    async def _run(self, client: AsyncClient):
        print("[BOT STARTED]")
        subscription_id:Optional[int] = None
        async for websocket in connect(ENDPOINT_WSS):
            try:
                # subscribe to log for target token account
                    await websocket.logs_subscribe(
                        RpcTransactionLogsFilterMentions(self._target_ata_pk)
                    )
                    print(f"[BOT]: Log Subscribe to {self._target_ata_pk}")
                    resp = await websocket.recv()
                    subscription_id = cast(SubscriptionResult, resp[0]).result
                    if not self._purchased:
                        await self._buy_handler(client, websocket)
                    await self._sell_handler(client, websocket)
            except asyncio.CancelledError:
                pass
            except websockets.exceptions.ConnectionClosed:
                subscription_id = None
                print("Websocket Failed")
                continue
            finally:
                if subscription_id:
                    await websocket.logs_unsubscribe(subscription_id)
                break

    async def _refresh_target_balance(self, client:AsyncClient):
        self._target_balance = (await client.get_token_account_balance(self._target_ata_pk)).value
        return self._target_balance
    
    async def _tell_price(self, client: AsyncClient):
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        jupiter = JupiterApi()
        res = await jupiter.get_token_price(
            [SOL, USDC],
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
                #await self._tell_price(client)
                print("[BOT]: Failed to connect to rpc")

    def _j_client(self, client:AsyncClient):
        jupiter = Jupiter(
            async_client=client,
            keypair=self._bot_key,
            # quote_api_url="https://quote-api.jup.ag/v6/quote?",
            # swap_api_url="https://quote-api.jup.ag/v6/swap",
            # open_order_api_url="https://jup.ag/api/limit/v1/createOrder",
            # cancel_orders_api_url="https://jup.ag/api/limit/v1/cancelOrders",
            # query_open_orders_api_url="https://jup.ag/api/limit/v1/openOrders?wallet=",
            # query_order_history_api_url="https://jup.ag/api/limit/v1/orderHistory",
            # query_trade_history_api_url="https://jup.ag/api/limit/v1/tradeHistory"
        )

        return jupiter


TARGET_ADDR = "87esLg2WdmndkRjYrxNene4cXrGsSAeVyQxAG9tcRh1m"
BOT_KEY = "6878f7061c40114ce10b7af8fb4469d98a9bb7957a56fd8c43203ad545199014"
MEME_ADDR = "7WjqfEHWGExm1Gz3F3EUQz1pCSTjgCzJ83YVeE57hQBp"
SALE_TIMEOUT = 2 * 60 # 3 minutes


async def main():
    q_subscription_ids = asyncio.Queue()
    bot = MemeBot(
        bot_secret=BOT_KEY,
        target_addr=TARGET_ADDR,
        meme_addr=MEME_ADDR,
        timeout=SALE_TIMEOUT
    )
    bot_task = asyncio.create_task(bot(q_subscription_ids))
    await bot_task
    print("Done")


def start():
    cprint(pyfiglet.figlet_format("MEMEBOT", font="larry3d"), "blue", attrs=["bold"], end="")
    cprint(pyfiglet.figlet_format("-- Meme Bot Started --", font="term"), "blue", attrs=["bold", "underline"])
    asyncio.run(main())

if __name__ == '__main__':
    start()