import math
from typing import  cast
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair # type: ignore
from solders.pubkey import Pubkey # type: ignore
from solana.exceptions import SolanaRpcException
from spl.token.async_client import AsyncToken
from solders.rpc.responses import SendTransactionResp # type: ignore
from spl.token.instructions import create_associated_token_account, mint_to_checked, MintToCheckedParams, transfer_checked, TransferCheckedParams
from solders.message import MessageV0 # type: ignore
from solders.transaction import VersionedTransaction # type: ignore
from solana.rpc.types import DataSliceOpts
from solders.token.state import Mint # type: ignore
from .. import utils

ENDPOINT = utils.get_env_rpc_url()

async def new_mint(payer_sk:str, decimals:int, supply:int=0):
    async with AsyncClient(ENDPOINT) as client:
        try:
            payer = Keypair.from_seed(bytes.fromhex(payer_sk))
            blockhash = (await client.get_latest_blockhash()).value.blockhash
            _token = await AsyncToken.create_mint(
                client,
                payer,
                payer.pubkey(),
                decimals,
                utils.TOKEN_2022_PROGRAM_ID,
                blockhash)
            print(f'[MINT]: {_token.pubkey}')
            
            if supply > 0:
                ix_create_ata = create_associated_token_account(
                    payer.pubkey(),
                    payer.pubkey(),
                    _token.pubkey,
                    utils.TOKEN_2022_PROGRAM_ID
                )

                ix_mint_to = mint_to_checked(
                    MintToCheckedParams(
                       program_id=utils.TOKEN_2022_PROGRAM_ID,
                       mint=_token.pubkey,
                       dest=utils.get_ata_pub_key(
                           payer.pubkey(),
                           _token.pubkey
                       ),
                       mint_authority=payer.pubkey(),
                       amount=int(supply * math.pow(10, decimals)),
                       decimals=decimals,
                       signers=[payer.pubkey()]
                    )
                )

                recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
                msg = MessageV0.try_compile(
                    payer=payer.pubkey(),
                    instructions=[ix_create_ata, ix_mint_to],
                    address_lookup_table_accounts=[],
                    recent_blockhash=recent_blockhash,
                )
                tx = VersionedTransaction(msg, [payer])

                res = await client.send_transaction(tx)

                print(f'[Signature]: {res.value}')
                res = await client.confirm_transaction(res.value)
                print(f'[Status]: {res.value[0].confirmation_status}')
        except SolanaRpcException as e:
            print(e.error_msg)

def get_token_account(user_pk:str, mint_pk:str):
    t_acct = utils.get_ata_pub_key(
        Pubkey.from_string(user_pk),
        Pubkey.from_string(mint_pk)
    )
    print(f'[Token Account]: {t_acct}')

async def get_token_account_balance(user_ata:str, format:bool):
    async with AsyncClient(ENDPOINT) as client:
        user_ata_pk = Pubkey.from_string(user_ata)
        res = await client.get_token_account_balance(user_ata_pk)
        print(res.value.ui_amount_string if format else res.value.amount)
    
async def transfer_token(src_sk:str, dest_pk:str, mint_pk:str, amount: int, format:bool):
    async with AsyncClient(ENDPOINT) as client:

        _mint_pk = Pubkey.from_string(mint_pk)
        tk_acct_info = await client.get_account_info(Pubkey.from_string(mint_pk))
        tk_info = Mint.from_bytes(tk_acct_info.value.data)
           
        _amount = amount      
        if(format):
            _amount = _amount * 10**tk_info.decimals
        
        payer = Keypair.from_seed(bytes.fromhex(src_sk))
        _src_pk =  payer.pubkey()
        src_ata = utils.get_ata_pub_key(
                    _src_pk,
                    Pubkey.from_string(mint_pk)
                )

        ixs = []

        _dest_pk = dest_ata = Pubkey.from_string(dest_pk)
        
        if dest_ata.is_on_curve():
            dest_ata = utils.get_ata_pub_key(
                _dest_pk,
                _mint_pk
            )

            dest_ata_info = await client.get_account_info(
                dest_ata, 
                data_slice=DataSliceOpts(
                    length=0,
                    offset=0
                )
            )
            if not dest_ata_info.value:
                #create an account for dest_ata in not existing
                ix_create_ata = create_associated_token_account(
                    _src_pk,
                    _dest_pk,
                    _mint_pk,
                    utils.TOKEN_2022_PROGRAM_ID
                )

                ixs.append(ix_create_ata)

        ix_transfer = transfer_checked(
            TransferCheckedParams(
               program_id=utils.TOKEN_2022_PROGRAM_ID,
                source=src_ata,
                mint=_mint_pk,
                dest=dest_ata,
                owner=_src_pk,
                amount=_amount,
                decimals=tk_info.decimals,
                signers=[_src_pk]
            )
        )
        ixs.append(ix_transfer)

        recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(
            payer=_src_pk,
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )
        tx = VersionedTransaction(msg, [payer])
        
        res = await client.send_transaction(tx)

        print(f'[Signature]: {res.value}')
        res = await client.confirm_transaction(res.value)
        print(f'[Status]: {res.value[0].confirmation_status}')

  
async def mint_drop(src_sk:str,  mint_pk:str, amount: int, format:bool):
    async with AsyncClient(ENDPOINT) as client:
        
        _mint_pk = Pubkey.from_string(mint_pk)
        tk_acct_info = await client.get_account_info(Pubkey.from_string(mint_pk))
        tk_info = Mint.from_bytes(tk_acct_info.value.data)

        _amount = amount
        if format:
            _amount = _amount * 10**tk_info.decimals
        
        payer = Keypair.from_seed(bytes.fromhex(src_sk))
        _src_pk =  payer.pubkey()
        src_ata = utils.get_ata_pub_key(
                _src_pk,
                Pubkey.from_string(mint_pk)
            )
        
        if tk_info.mint_authority != _src_pk:
            print("Account is not mint authority")
            return

        src_ata_info = await client.get_account_info(
            src_ata,
            data_slice=DataSliceOpts(
                length=0,
                offset=0
            )
        )

        ixs = []

        if not src_ata_info.value:
            ix_create_ata = create_associated_token_account(
                _src_pk,
                _src_pk,
                _mint_pk,
                utils.TOKEN_2022_PROGRAM_ID
            )

            ixs.append(ix_create_ata)

        ix_mint_to = mint_to_checked(
            MintToCheckedParams(
                program_id=utils.TOKEN_2022_PROGRAM_ID,
                mint=_mint_pk,
                dest=utils.get_ata_pub_key(
                    _src_pk,
                    _mint_pk
                ),
                mint_authority=_src_pk,
                amount=_amount,
                decimals=tk_info.decimals,
                signers=[_src_pk]
            )
        )
        ixs.append(ix_mint_to)

        recent_blockhash = (await client.get_latest_blockhash()).value.blockhash
        msg = MessageV0.try_compile(
            payer=payer.pubkey(),
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )
        tx = VersionedTransaction(msg, [payer])

        res = await client.send_transaction(tx)

        print(f'[Signature]: {res.value}')
        res = await client.confirm_transaction(res.value)
        print(f'[Status]: {res.value[0].confirmation_status}')