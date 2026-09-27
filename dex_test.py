import asyncio
import aiohttp

BASE = "https://api.dexscreener.com"


async def main():
    token_address = input("Paste a Solana token CA: ").strip()

    url = f"{BASE}/tokens/v1/solana/{token_address}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as response:

            print(f"\nHTTP status: {response.status}")

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
