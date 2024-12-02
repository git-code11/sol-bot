# import yaml
from typing import cast

from colorama import just_fix_windows_console
import pyfiglet
from termcolor import colored, cprint

import asyncio
from asyncstdlib import enumerate

from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair # type: ignore
from solders.rpc.responses import AccountNotification, LogsNotification # type: ignore
from solders.token.state import TokenAccount # type: ignore
from solders.account_decoder import UiTokenAmount # type: ignore
from solders.token.state import Mint # type: ignore
from solders.rpc.config import RpcTransactionLogsFilterMentions # type: ignore

from solana.rpc.async_api import AsyncClient
from solana.rpc.types import DataSliceOpts
from solana.rpc.websocket_api import connect


import utils

# use Colorama to make Termcolor work on Windows too
just_fix_windows_console()

# CONFIG_PATH = "./config.yaml"

# with open(CONFIG_PATH) as config_file:
#     config = yaml.load(config_file, yaml.SafeLoader)


TARGET_ADDR = "87esLg2WdmndkRjYrxNene4cXrGsSAeVyQxAG9tcRh1m"
BOT_KEY = "c55d63dde19980053c75ff7dadeb586767d73f964f90ca8b266a47bca91e463b"
MEME_ADDR = "7WjqfEHWGExm1Gz3F3EUQz1pCSTjgCzJ83YVeE57hQBp"
SALE_TIMEOUT = 3 * 60 # 3 minutes
ENDPOINT_API = "https://api.devnet.solana.com"
ENDPOINT_WSS = "wss://api.devnet.solana.com"


async def bot(queue:asyncio.Queue):
    if not (TARGET_ADDR and BOT_KEY and MEME_ADDR):
        raise asyncio.CancelledError("Invalid Address")
    
    bot_key = Keypair.from_seed(bytes.fromhex(BOT_KEY))
    meme_pk = Pubkey.from_string(MEME_ADDR)
    target_ata_pk = Pubkey.from_string(TARGET_ADDR)
    
    if target_ata_pk.is_on_curve():
        target_ata_pk = utils.get_ata_pub_key(target_ata_pk, meme_pk)
    bot_ata_pk = utils.get_ata_pub_key(bot_key.pubkey(), meme_pk)
    
    print("""BOT WALLET: %s
        TARGET WALLET: %s
        MEME COIN: %s"""%(bot_ata_pk, target_ata_pk, meme_pk))

    async with AsyncClient(ENDPOINT_API) as client:
        
        if await client.is_connected():
            # Check for Meme coin existence
            meme_acct_info = (await client.get_account_info(meme_pk)).value
            if not meme_acct_info:
                print("Meme coin does not exist")
                raise asyncio.CancelledError("Meme coin Invalid")

            # get token info
            meme_info = Mint.from_bytes(meme_acct_info.data)
            _TOKEN_PROGRAM_ID = meme_acct_info.owner

            # Check for target account existence and blocks
            while True:
                target_info = await client.get_account_info(target_ata_pk, data_slice=DataSliceOpts(length=0, offset=0))
                if target_info.value:
                    print("Target wallet exists")
                    break
                else:
                    print("Target wallet does not exists")
                    async with connect(ENDPOINT_WSS) as websocket:
                        await websocket.logs_subscribe(
                            RpcTransactionLogsFilterMentions(target_ata_pk)
                        )
                        print(f"[BOT]: Log Subscribe to {target_ata_pk}")
                        resp = await websocket.recv()
                        subscription_id = resp[0].result

                        async for idx, [msg] in enumerate(websocket):
                            msg_ = cast(LogsNotification, msg)
                            print("[Logs]=> ", msg_.result.value)
                            break
                        await websocket.logs_unsubscribe(subscription_id)

            target_balance = (await client.get_token_account_balance(target_ata_pk)).value
            
            print("""Target Account: %s\nCurrent Balance: %s"""%(target_ata_pk, target_balance.ui_amount_string))
            

            print("[BOT STARTED]")
            if int(target_balance.amount) > 0:
                #maybe just go straight to token purchase
                pass

            async with connect(ENDPOINT_WSS) as websocket:
                try:
                    await websocket.logs_subscribe(
                        RpcTransactionLogsFilterMentions(target_ata_pk)
                    )
                    print(f"[BOT]: Log Subscribe: {target_ata_pk}")
                    resp = await websocket.recv()
                    subscription_id = resp[0].result
                    
                    # monitor purchase here
                    async for idx, [msg] in enumerate(websocket):
                        msg_ = cast(LogsNotification, msg)
                        print(f"[BOT-LOG]: {msg_.result.value.signature} mentions Target {target_ata_pk}")
                        old_target_balance = target_balance
                        target_balance = (await client.get_token_account_balance(target_ata_pk)).value
                        print("Target balance is currently %s"%target_balance.ui_amount_string)

                        if(int(target_balance.amount) > int(old_target_balance.amount)):
                            print("Target balance has increased")
                            print("Purchase now")
                            break
                     
                    # monitor sales here
                    try:
                        async with asyncio.Timeout(SALE_TIMEOUT):
                            async for idx, [msg] in enumerate(websocket):
                                msg_ = cast(LogsNotification, msg)
                                print(f"[BOT-LOG]: {msg_.result.value.signature} mentions Target {target_ata_pk}")
                                old_target_balance = target_balance
                                target_balance = (await client.get_token_account_balance(target_ata_pk)).value
                                print("Target balance is currently %s"%target_balance.ui_amount_string)

                                if(int(target_balance.amount) < int(old_target_balance.amount)):
                                    print("Target balance has decreased")
                                    print("Sell now")
                                    break
                    except asyncio.TimeoutError:
                        print("Making sales immediately now")
                        print("Sell now")

                except asyncio.CancelledError as e:
                        print("Error: ", e.args)
                finally:
                    await websocket.account_unsubscribe(subscription_id)
                                
async def main():
    q_subscription_ids = asyncio.Queue()
    bot_task = asyncio.create_task(bot(q_subscription_ids))
    await bot_task
    print("Done")


# async for websocket in connect(...):
#     try:
#         ...
#     except websockets.exceptions.ConnectionClosed:
#         continue


if __name__ == '__main__':
    
    cprint(pyfiglet.figlet_format("MEMEBOT", font="larry3d"), "blue", attrs=["bold"], end="")
    cprint(pyfiglet.figlet_format("-- Meme Bot Started --", font="term"), "blue", attrs=["bold", "underline"])
    asyncio.run(main())