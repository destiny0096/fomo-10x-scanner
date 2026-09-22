import asyncio
import aiohttp

TOKEN_CA = "8TSUhXRhpEFtUVfDFAQdYCwgp2mEbs2jQk7tAYc1pump"

SOL_MINT = "So11111111111111111111111111111111111111112"

RPC_URL = "https://api.mainnet-beta.solana.com"

JUPITER_URL = "https://lite-api.jup.ag/swap/v1/quote"


async def main():
    print("🔍 SELL ROUTE DETECTION")
    print("Token:", TOKEN_CA)
    print()

    async with aiohttp.ClientSession() as session:

        # Get token decimals
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenSupply",
            "params": [TOKEN_CA]
        }

        try:
            async with session.post(
                RPC_URL,
                json=rpc_payload
            ) as response:
                rpc_data = await response.json()
        except Exception as e:
            print("❌ RPC CONNECTION ERROR:", e)
            print()
            print("❓ SELL ROUTE: UNABLE TO VERIFY")
            return

        if "error" in rpc_data:
            print("❌ RPC ERROR:", rpc_data["error"])
            print()
            print("❓ SELL ROUTE: UNABLE TO VERIFY")
            return

        supply = rpc_data.get("result", {}).get("value", {})
        decimals = supply.get("decimals")

        if decimals is None:
            print("❌ Could not determine token decimals")
            print()
            print("❓ SELL ROUTE: UNABLE TO VERIFY")
            return

        # Ask Jupiter whether the token can currently be routed
        # back to SOL.
        test_amount = 10 ** decimals

        params = {
            "inputMint": TOKEN_CA,
            "outputMint": SOL_MINT,
            "amount": test_amount,
            "slippageBps": 500
        }

        try:
            async with session.get(
                JUPITER_URL,
                params=params
            ) as response:
                data = await response.json()
                status = response.status
        except Exception as e:
            print("❌ JUPITER CONNECTION ERROR:", e)
            print()
            print("❓ SELL ROUTE: UNABLE TO VERIFY")
            return

    if status != 200:
        print("❌ JUPITER ERROR")
        print("HTTP status:", status)
        print("Response:", data)
        print()
        print("❓ SELL ROUTE: UNABLE TO VERIFY")
        return

    if "error" in data:
        print("🚨 NO SELL ROUTE FOUND")
        print("Reason:", data.get("error"))
        print()
        print("🚨 SELL BLOCK: DETECTED")
        return

    route = data.get("routePlan")

    if not route:
        print("🚨 NO SELL ROUTE FOUND")
        print()
        print("🚨 SELL BLOCK: DETECTED")
        return

    print("✅ SELL ROUTE FOUND")
    print("Token decimals:", decimals)
    print("Test amount: 1 token")
    print("Route steps:", len(route))
    print("Expected SOL output:", data.get("outAmount"))
    print()
    print("🔒 SELL BLOCK: NOT DETECTED")
    print("ℹ️ A live Jupiter sell route currently exists.")


if __name__ == "__main__":
    asyncio.run(main())
