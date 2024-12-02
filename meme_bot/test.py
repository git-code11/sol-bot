import asyncio

from . import helper

#bank
account1_key = "8e41ad5b7a6c5e9a7cee9d3b46a9c34bf2ac5efeb1fcfc9b62522c0d862ceb24"
account1_addr = "2op4MqPt22Q1kfwU6PjKEZx95jxPYA74T2aJsst2Pr7Q"
mint_addr = "7WjqfEHWGExm1Gz3F3EUQz1pCSTjgCzJ83YVeE57hQBp"
#target
account2_key = "c55d63dde19980053c75ff7dadeb586767d73f964f90ca8b266a47bca91e463b"
account2_addr = "3Yo3UrP7pAEmWFzHQmt9exXwRsP5cwW5d9AetBucY1aM"

async def test():
    print("Target is purchasing token")
    await helper.token.transfer_token(
        account1_key,
        account2_addr,
        mint_addr,
        2,
        True
    )

    print("Target is waiting 30 seconds for market price to rise")
    await asyncio.sleep(30) #sleep 30 seconds

    print("Target is selling token")
    await helper.token.transfer_token(
        account2_key,
        account1_addr,
        mint_addr,
        2,
        True
    ) 
    

def start():
    asyncio.run(test())
