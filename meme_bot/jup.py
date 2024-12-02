from typing import List, Optional
import httpx

URL_PRICE_V2 = "https://api.jup.ag/price/v2"

class JupiterApi:

    @staticmethod
    async def get_token_price(
        ids:List[str],
        *,
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
                URL_PRICE_V2,
                params=params
            )
            return res.json()