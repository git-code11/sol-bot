from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore

def generate_keypair():
    keypair = Keypair()
    print('Random keypair generated')
    print(f'[SECRET-KEY]: {keypair.secret().hex()}')
    print(f'[PUBLIC-KEY]: {keypair.pubkey()}')

def get_address(acct_sk:str):
    keypair = Keypair.from_seed(bytes.fromhex(acct_sk))
    print(f'[PUBLIC-KEY]: {keypair.pubkey()}')

def check_pda(acct_pk:str):
    status = Pubkey.from_string(acct_pk).is_on_curve()
    print(f'[IS PDA]: {not status}')