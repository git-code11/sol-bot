import base64
import enum
from typing import List, Optional
import httpx
from solders.pubkey import Pubkey # type: ignore
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction, Transaction # type: ignore
from solders.message import to_bytes_versioned # type: ignore

from solana.rpc import types
from solana.rpc import commitment
from solana.rpc.async_api import AsyncClient

URL_TOKEN_PRICE = "https://api.jup.ag/price/v2"
URL_TOKEN_LIST = "https://tokens.jup.ag/tokens"
URL_TOKEN_INFO = "https://tokens.jup.ag/token"
URL_QUOTE = "https://quote-api.jup.ag/v6/quote"
URL_SWAP = "https://quote-api.jup.ag/v6/swap"
URL_SWAP_INSTRUCTIONS = "https://quote-api.jup.ag/v6/swap-instructions"

class SwapMode(enum.Enum):
    ExactIn="ExactIn"
    ExactOut="ExactOut"


class JupiterApi:

    @staticmethod
    async def get_tokens_by_tag(
        *tags: str,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            tags_ = ','.join(tags) if tags else 'verified'
            params = dict(tags=tags_)

            res = await client.get(
                URL_TOKEN_LIST,
                params=params
            )
            return res.json()
    
    @staticmethod
    async def get_token_by_mint(
        mint: str,
    ) -> dict:
        async with httpx.AsyncClient() as client:
           
            res = await client.get(
                f"{URL_TOKEN_INFO}/{mint}",
            )
            return res.json()

    @staticmethod
    async def get_token_price(
        *ids:str,
        vsToken:Optional[str]=None,
        showExtraInfo:Optional[bool]=None
    ) -> dict:
        async with httpx.AsyncClient() as client:
            params = dict(ids=','.join(ids))
            if vsToken:
                params['vsToken'] = vsToken
            if showExtraInfo != None:
                params['showExtraInfo'] = showExtraInfo

            res = await client.get(
                URL_TOKEN_PRICE,
                params=params
            )
            return res.json()
    
    @staticmethod
    async def quote(
        inputMint:str,
        outputMint:str,
        amount:int,
        slippageBps=50, #default 50
        swapMode:SwapMode=SwapMode.ExactIn, 
        restrictIntermediateTokens=True,
        **kwargs
    ) -> dict:
        async with httpx.AsyncClient() as client:
            params = dict(
                inputMint=inputMint,
                outputMint=outputMint,
                amount=amount,
                slippageBps=slippageBps,
                swapMode=swapMode.value,
                restrictIntermediateTokens=restrictIntermediateTokens,
            )
            params.update(**kwargs)

            res = await client.get(
                URL_QUOTE,
                params=params
            )
            return res.json()
    
    @staticmethod
    async def swap(
        #quoteResponse from /quote api
        quoteResponse:dict,
        #user public key to be used for the swap
        userPublicKey:str,
        #auto wrap and unwrap SOL. default is true
        wrapAndUnwrapSol: bool=True,
        asLegacyTransaction:bool=False,
        **kwargs
    )->dict:
        async with httpx.AsyncClient() as client:
            data = dict(
                quoteResponse=quoteResponse,
                userPublicKey=userPublicKey,
                wrapAndUnwrapSol=wrapAndUnwrapSol,
                asLegacyTransaction=asLegacyTransaction
            )

            data.update(**kwargs)
            
            res = await client.post(
                URL_SWAP,
                json=data
            )

            return res.json()
        
    @staticmethod
    async def swap_instruction(
        #quoteResponse from /quote api
        quoteResponse:dict,
        #user public key to be used for the swap
        userPublicKey:str,
        #auto wrap and unwrap SOL. default is true
        wrapAndUnwrapSol: bool=True,
        asLegacyTransaction:bool=False,
        **kwargs
    )->dict:
        async with httpx.AsyncClient() as client:
            data = dict(
                quoteResponse=quoteResponse,
                userPublicKey=userPublicKey,
                wrapAndUnwrapSol=wrapAndUnwrapSol,
                asLegacyTransaction=asLegacyTransaction
            )

            data.update(**kwargs)
            
            res = await client.post(
                URL_SWAP_INSTRUCTIONS,
                json=data
            )

            return res.json()
    
    @classmethod
    async def swap_tx(
        cls,
        *,
        inputMint:str,
        outputMint:str,
        amount:int,
        payer_pk_sk:Optional[str | Pubkey | Keypair]=None
    ):
        quoteResponse = await cls.quote(
            inputMint = inputMint,
            outputMint = outputMint,
            amount = amount
        )

        swapResponse = None
        _txn = None
        enableSwap = payer_pk_sk != None
        is_keypair = type(payer_pk_sk) == Keypair
        
        if enableSwap:
            _payer_pk: str | Pubkey = payer_pk_sk.pubkey() if is_keypair else payer_pk_sk
            swapResponse = await cls.swap(
                quoteResponse,
                str(_payer_pk)
            )
            swapTransaction = swapResponse.get("swapTransaction")
            _txn = VersionedTransaction.from_bytes(base64.b64decode(swapTransaction))
            if is_keypair:
                signature = payer_pk_sk.sign_message(to_bytes_versioned(_txn.message))
                _txn = VersionedTransaction.populate(_txn.message, [signature])
                
        response = dict(
                quoteResponse=quoteResponse,
                swapResponse=swapResponse,
                txn=_txn,
                is_signed=is_keypair 
            )
        
        return response
    
    @staticmethod
    def opts():
        """  opts = TxOpts(
                max_retries=5,
                skip_preflight=True, 
                preflight_commitment=commitment.Finalized
            ) """
        opts = types.TxOpts(
                max_retries=5,
                skip_preflight=False, 
                preflight_commitment=commitment.Processed)
        
        return opts
    
    async def sendAndConfirmTransaction(
        client: AsyncClient,
        tx: VersionedTransaction | Transaction,
        opts: Optional[types.TxOpts] = None,
        confirm_commitment:Optional[commitment.Commitment] = commitment.Processed,
        verbose:bool=False,
    ):
        resp = await client.send_transaction(
            tx,
            opts
        )
        
        if verbose:
            print("SIGNATURE: ", resp.value)
        
        confirm_resp = await client.confirm_transaction(
            resp.value,
            confirm_commitment
        )

        return (resp.value, confirm_resp.value)

        