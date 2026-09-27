import asyncio
import aiohttp

BASE = "https://api.dexscreener.com"

TOKEN_ADDRESS = "6uPEdkU2xPg1iyfLzV1ssUwvve8nndA2sd6nBFrb1n58"


async def main():
    url = f"{BASE}/tokens/v1/solana/{TOKEN_ADDRESS}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as response:

            print(f"HTTP status: {response.status}")

            data = await response.json()

            if response.status >= 400:
                print("❌ DexScreener API error:")
                print(data)
                return

    if not isinstance(data, list) or not data:
        print("❌ No pair data found")
        return

    pair = data[0]

    print("\n===== DEXSCREENER DATA =====")

    print("\n📈 PRICE CHANGE:")
    print(pair.get("priceChange"))

    print("\n📊 VOLUME:")
    print(pair.get("volume"))

    print("\n🟢 TRANSACTIONS:")
    print(pair.get("txns"))

    print("\n💧 LIQUIDITY:")
    print(pair.get("liquidity"))

    print("\n💰 MARKET CAP:")
    print(pair.get("marketCap"))

    print("\n============================")


if __name__ == "__main__":
    asyncio.run(main())
