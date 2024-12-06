import json
from pprint import pprint
from jup import JupiterApi
import asyncio
#import json
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
import base58
import base64
from solders import message

from solana.rpc.types import TxOpts
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed

from solders.message import Message
from solana.rpc.core import RPCException


ENDPOINT = "https://powerful-tiniest-reel.solana-mainnet.quiknode.pro/5ce9e04fcb735d966713deb127ba8355c5df52e4"

async def run_test():
    j = JupiterApi()
    # resp = await j.get_tokens_by_tag()
    # file_name = 'token.json'
    # with open(file_name, 'w') as file:
    #     json.dump(resp, file, indent=2)
    # print(f"Token dumped to {file_name}")
    quoteResponse = await j.quote(
        #inputMint="So11111111111111111111111111111111111111112",
        inputMint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        outputMint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        amount=2500
    )

    payer_sk = Keypair()
    payer_pk = Pubkey.from_string("AsTySyN7EHM3RLpxeq5fgt9QLWRPsJ8W6mPAYCTmFZua")
    resp = await j.swap(
        quoteResponse,
        str(payer_pk),
    )

    lastValidBlockHeight = resp.get("lastValidBlockHeight")
    swapTransaction = resp.get("swapTransaction")
    client = AsyncClient(ENDPOINT)
    latestBlockHash = await client.get_latest_blockhash()
    raw_txn = VersionedTransaction.from_bytes(base64.b64decode(swapTransaction))
    signature = payer_pk.sign_message(message.to_bytes_versioned(raw_txn.message))
    signed_txn = VersionedTransaction.populate(raw_txn.message, [signature])
    
    
    """ print(signed_txn.verify_and_hash_message()) """
    opts = TxOpts(skip_preflight=False, preflight_commitment=Processed)
    result = await client.simulate_transaction(txn=raw_txn)
    #result = await client.send_raw_transaction(txn=bytes(signed_txn), opts=opts)
    print(result)
    #transaction_id = json.loads(result.to_json())['result']
    #print(f"Transaction sent: https://explorer.solana.com/tx/{transaction_id}")
    

async def run():
    async with AsyncClient(ENDPOINT) as client:
        payer_pk = Pubkey.from_string("AsTySyN7EHM3RLpxeq5fgt9QLWRPsJ8W6mPAYCTmFZua")
        payer_sk = Keypair()
        payMint = "So11111111111111111111111111111111111111112"
        memeMint = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
        usdcMint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        resp = await JupiterApi.get_token_price(
            memeMint,
            #vsToken=usdcMint
        )
        print("PRICE =>", resp["data"][memeMint])
        return
        resp = await JupiterApi.swap_tx(
            inputMint=payMint,
            outputMint=memeMint,
            amount=2500,
            payer_pk_sk=payer_pk
        )

        raw_tx = resp["txn"]
        if raw_tx:
            result = await client.simulate_transaction(txn=raw_tx)
            print("Errors => ", result.value.err)
            print("Unit Consumd => ", result.value.units_consumed)
        
        resp = await JupiterApi.swap_tx(
            inputMint=memeMint,
            outputMint=payMint,
            amount=2500,
            payer_pk_sk=payer_sk
        )

        raw_tx = resp["txn"]
        if raw_tx:
            result = await client.simulate_transaction(txn=raw_tx)
            print("Errors => ", result.value.err)
            print("Unit Consumd => ", result.value.units_consumed)
            
            try:
                result = await JupiterApi.sendAndConfirmTransaction(
                    client,
                    raw_tx,
                    opts=JupiterApi.opts(),
                    verbose=True
                )
                pprint(result)
            except RPCException as e:
                print(e.args[0])

            

def main():
    asyncio.run(run())

main()