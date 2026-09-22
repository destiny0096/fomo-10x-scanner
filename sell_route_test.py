import asyncio
import aiohttp

TOKEN_CA = "8TSUhXRhpEFtUVfDFAQdYCwgp2mEbs2jQk7tAYc1pump"

SOL_MINT = "So11111111111111111111111111111111111111112"

RPC_URL = "https://api.mainnet-beta.solana.com"
JUPITER_URL = "https://lite-api.jup.ag/swap/v1/quote"


async def check_sell_route(session, token_ca):
    """
    Check whether Jupiter currently has a route
    to sell the token back to SOL.

    Returns:
        "NOT BLOCKED"
        "BLOCKED"
        "UNABLE TO VERIFY"
    """

    rpc_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenSupply",
        "params": [token_ca]
    }

    try:
        async with session.post(
            RPC_URL,
            json=rpc_payload,
            timeout=20
        ) as response:
            rpc_data = await response.json()

    except Exception:
        return "UNABLE TO VERIFY"

    if "error" in rpc_data:
        return "UNABLE TO VERIFY"

    supply = rpc_data.get("result", {}).get("value", {})
    decimals = supply.get("decimals")

    if decimals is None:
        return "UNABLE TO VERIFY"

    test_amount = 10 ** decimals

    params = {
        "inputMint": token_ca,
        "outputMint": SOL_MINT,
        "amount": test_amount,
        "slippageBps": 500
    }

    try:
        async with session.get(
            JUPITER_URL,
            params=params,
            timeout=20
        ) as response:
            data = await response.json()
            status = response.status

    except Exception:
        return "UNABLE TO VERIFY"

    if status != 200:
        return "UNABLE TO VERIFY"

    if "error" in data:
        return "BLOCKED"

    route = data.get("routePlan")

    if not route:
        return "BLOCKED"

    return "NOT BLOCKED"


def sell_route_text(status):
    """
    Convert sell-route status into Telegram text.
    """

    if status == "NOT BLOCKED":
        return "🔒 SELL BLOCK: NOT DETECTED"

    if status == "BLOCKED":
        return "🚨 SELL BLOCK: DETECTED"

    return "❓ SELL ROUTE: UNABLE TO VERIFY"


async def main():
    print("🔍 SELL ROUTE DETECTION")
    print("Token:", TOKEN_CA)
    print()

    async with aiohttp.ClientSession() as session:

        status = await check_sell_route(
            session,
            TOKEN_CA
        )

    if status == "NOT BLOCKED":
        print("✅ SELL ROUTE FOUND")
        print()
        print("🔒 SELL BLOCK: NOT DETECTED")
        print("ℹ️ A live Jupiter sell route currently exists.")

    elif status == "BLOCKED":
        print("🚨 NO SELL ROUTE FOUND")
        print()
        print("🚨 SELL BLOCK: DETECTED")

    else:
        print("❓ SELL ROUTE: UNABLE TO VERIFY")


if __name__ == "__main__":
    asyncio.run(main())
            
