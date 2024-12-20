from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from spl.token.instructions import get_associated_token_address
from spl.token.constants import TOKEN_2022_PROGRAM_ID

from . import get_env_rpc_url

LAMPORT_PER_SOL = 1000000000
    
def lamport_to_sol(value:int) -> int:
    return value / LAMPORT_PER_SOL

def sol_to_lamport(value:float) -> int:
    return int(value * LAMPORT_PER_SOL)

def get_pub_key(acct_pk_sk:str, is_secret:bool=False) -> Pubkey:
    return Keypair.from_seed(bytes.fromhex(acct_pk_sk)).pubkey() if is_secret else Pubkey.from_string(acct_pk_sk)

def get_ata_pub_key(acct_pub_key:Pubkey, mint_pub_key: Pubkey, token_program: Pubkey = TOKEN_2022_PROGRAM_ID) -> Pubkey:
    return get_associated_token_address(
        acct_pub_key,
        mint_pub_key,
        token_program
    )

def to_pubkey(addr:Pubkey|str):
    return Pubkey.from_string(addr) if type(addr)==str else addr