import asyncio
import aiohttp

TOKEN_CA = "So11111111111111111111111111111111111111112"

RPC_URL = "https://api.mainnet-beta.solana.com"


async def main():
    print("👥 TOP HOLDER CONCENTRATION TEST")
    print("Token:", TOKEN_CA)
    print()

    supply_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenSupply",
        "params": [
            TOKEN_CA,
            {
                "commitment": "finalized"
            }
        ]
    }

    holders_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "getTokenLargestAccounts",
        "params": [
            TOKEN_CA,
            {
                "commitment": "finalized"
            }
        ]
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                RPC_URL,
                json=supply_payload
            ) as response:
                supply_data = await response.json()

            async with session.post(
                RPC_URL,
                json=holders_payload
            ) as response:
                holders_data = await response.json()

        except Exception as e:
            print("❌ RPC CONNECTION ERROR:", e)
            print()
            print("❓ HOLDER CONCENTRATION: UNABLE TO VERIFY")
            return

    if "error" in supply_data:
        print("❌ SUPPLY RPC ERROR:", supply_data["error"])
        print()
        print("❓ HOLDER CONCENTRATION: UNABLE TO VERIFY")
        return

    if "error" in holders_data:
        print("❌ HOLDER RPC ERROR:", holders_data["error"])
        print()
        print("❓ HOLDER CONCENTRATION: UNABLE TO VERIFY")
        return

    supply_info = supply_data.get("result", {}).get("value", {})
    accounts = holders_data.get("result", {}).get("value", [])

    total_supply = int(supply_info.get("amount", "0"))
    decimals = supply_info.get("decimals")

    if total_supply <= 0 or decimals is None:
        print("❌ Invalid token supply data")
        print()
        print("❓ HOLDER CONCENTRATION: UNABLE TO VERIFY")
        return

    if not accounts:
        print("❌ No token holder accounts found")
        print()
        print("❓ HOLDER CONCENTRATION: UNABLE TO VERIFY")
        return

    top_10 = accounts[:10]

    top_10_amount = sum(
        int(account["amount"])
        for account in top_10
    )

    top_10_percentage = (
        top_10_amount / total_supply
    ) * 100

    print("Total supply:", total_supply / (10 ** decimals))
    print("Decimals:", decimals)
    print("Largest accounts found:", len(accounts))
    print()

    print("📊 TOP 10 HOLDER ACCOUNTS")

    for index, account in enumerate(top_10, start=1):
        amount = int(account["amount"]) / (10 ** decimals)

        percentage = (
            int(account["amount"]) / total_supply
        ) * 100

        print(
            f"{index}. {account['address']} "
            f"→ {amount:.2f} tokens "
            f"({percentage:.2f}%)"
        )

    print()
    print(
        f"📊 TOP 10 CONCENTRATION: "
        f"{top_10_percentage:.2f}%"
    )

    if top_10_percentage >= 50:
        print("🚨 HIGH HOLDER CONCENTRATION")
    else:
        print("✅ TOP 10 CONCENTRATION BELOW 50%")

    print()
    print("ℹ️ This measures token-account concentration.")
    print("ℹ️ Multiple token accounts may belong to the same entity.")


if __name__ == "__main__":
    asyncio.run(main())
