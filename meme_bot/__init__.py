import os
import enum
from typing import NamedTuple, Optional
import redis.asyncio as redis
from solders.pubkey import Pubkey # type: ignore

from dotenv import load_dotenv
load_dotenv()


def get_env_rpc_url(env_var:Optional[str]=None,default:str="prod"):
    #print("ENV ", os.environ.get("MEME_BOT_ENV", default))
    IS_PRODUCTION = env_var or os.environ.get("MEME_BOT_ENV", default)
    
    if IS_PRODUCTION:
        IS_PRODUCTION = IS_PRODUCTION.lower().startswith("prod")
    else:
        IS_PRODUCTION = False
    
    if IS_PRODUCTION:
        return (
            os.environ.get("RPC_ENDPOINT_URL_PROD"), 
            os.environ.get("RPC_ENDPOINT_WSS_PROD")
        )
    else:
        return (
            os.environ.get("RPC_ENDPOINT_URL_DEV"), 
            os.environ.get("RPC_ENDPOINT_WSS_DEV")
        )


WRAPPED_SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

REDIS_URL = "127.0.0.1"
REDIS_MINTS_KEY = "tokens"

DEBUG = False
TX_RETRIES = 3
LAG_TIME = 60


class SaleType(enum.Enum):
    CAPPED="CAPPED"
    TIMER="TIMER"
    BOTH="BOTH"


class BotStatus(enum.Enum):
    IDLE = "IDLE" # WAITING
    STARTED = "STARTED" # MADE PURCHASE
    SUCCESS = "SUCCESS" # MADE SALES


class AccountInfo(NamedTuple):
    program_id: Pubkey
    owner:Pubkey
    ata:Pubkey
    mint:Pubkey
    amount: int

def get_redis_client():
    return redis.Redis(host=REDIS_URL, decode_responses=True)

def print_screen():
    from colorama import just_fix_windows_console
    import pyfiglet
    from termcolor import cprint
    # # use Colorama to make Termcolor work on Windows too
    just_fix_windows_console()

    cprint(pyfiglet.figlet_format("MEMEBOT", font="larry3d"), "blue", attrs=["bold"], end="")
    cprint(pyfiglet.figlet_format("-- Meme Bot Started --", font="term"), "blue", attrs=["bold", "underline"])


from . import utils
from . import helper
from .jup import JupiterApi
from .bot_manager import BotManager
from . import bot