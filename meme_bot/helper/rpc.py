from solders.pubkey import Pubkey # type: ignore
from solana.rpc.async_api import AsyncClient
from solana.exceptions import SolanaRpcException
from solders.system_program import transfer, TransferParams
from solders.message import Message # type: ignore
from solders.transaction import Transaction # type: ignore
from solders.keypair import Keypair # type: ignore

from .. import utils, DEBUG

(ENDPOINT, _) = utils.get_env_rpc_url("dev" if DEBUG else None)

async def connected():
    async with AsyncClient(ENDPOINT) as client:
        res = await client.is_connected()
    print(res)

async def get_balance(acct_pk_sk:str, is_secret:bool, format_sol:bool):
    async with AsyncClient(ENDPOINT) as client:
        try:            
            res = await client.get_balance(
                utils.get_pub_key(acct_pk_sk, is_secret)
            )
            value = utils.lamport_to_sol(res.value) if format_sol else res.value
            print(f'[VALUE]: {value} {'sol' if format_sol else 'lamports'}')
        except SolanaRpcException as e:
            print(e.error_msg)
    

async def airdrop(acct_pk:str, amount:int, format_sol:bool):
    async with AsyncClient(ENDPOINT) as client:
        try:
            account = Pubkey.from_string(acct_pk)
            rent = await client.get_minimum_balance_for_rent_exemption(0)
    
            value = utils.sol_to_lamport(amount) if format_sol else amount
            acct_info = await client.get_account_info(
                account
            )
            if not acct_info.value:
                value += rent.value
            
            res = await client.request_airdrop(
                account,
                value
            )
            print(f'[Signature]: {res.value}')
            res = await client.confirm_transaction(res.value)
            print(f'[Status]: {res.value[0].confirmation_status}')
        except SolanaRpcException as e:
            print(e.with_traceback())
            print(e.error_msg)
    
async def transfer_sol(src_sk:str, dest_pk:str, amount:int, format_sol:bool):
    async with AsyncClient(ENDPOINT) as client:
        try:
            src_key = Keypair.from_seed(bytes.fromhex(src_sk))
            src_acct = src_key.pubkey()
            dest_acct = Pubkey.from_string(dest_pk)
            value =  utils.sol_to_lamport(amount) if format_sol else amount
            ixn = transfer(
                TransferParams(
                    from_pubkey=src_acct,
                    to_pubkey=dest_acct,
                    lamports=value
                )
            )

            msg = Message([ixn], src_acct)
            recent_block_hash = await client.get_latest_blockhash()
            txn = Transaction([src_key], msg, recent_block_hash.value.blockhash)
            res = await client.send_transaction(txn)
            print(f'[Signature]: {res.value}')
            res = await client.confirm_transaction(res.value)
            print(f'[Status]: {res.value[0].confirmation_status}')

        except SolanaRpcException as e:
            print(e.with_traceback())
            print(e.error_msg)