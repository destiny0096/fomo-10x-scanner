import asyncio
import aiohttp
from solders.pubkey import Pubkey

TOKEN_CA = "sdyKwWzC8EnriZWBBwm8YX25nKGmtQdZAHBEGLUpump"

RPC_URL = "https://api.mainnet-beta.solana.com"

PUMPSWAP_PROGRAM = Pubkey.from_string(
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)

PUMP_PROGRAM = Pubkey.from_string(
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
)


async def main():
    token = Pubkey.from_string(TOKEN_CA)

    print("🔍 Checking PumpSwap pool...")
    print("Token:", TOKEN_CA)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            str(PUMPSWAP_PROGRAM),
            {
                "encoding": "base64",
                "filters": [
                    {
                        "memcmp": {
                            "offset": 43,
                            "bytes": TOKEN_CA
                        }
                    }
                ]
            }
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(RPC_URL, json=payload) as response:
            data = await response.json()

    if "error" in data:
        print("❌ RPC ERROR:", data["error"])
        return

    accounts = data.get("result", [])

    if not accounts:
        print("❓ No PumpSwap pool found")
        return

    print(f"✅ PumpSwap pool(s) found: {len(accounts)}")

    for account in accounts:
        pool_address = account["pubkey"]
        raw_data = account["account"]["data"][0]

        import base64
        decoded = base64.b64decode(raw_data)

        if len(decoded) < 75:
            print("❓ Pool data is too short to verify")
            continue

        # PumpSwap Pool layout:
        # 8 bytes  = Anchor discriminator
        # 1 byte   = bump
        # 2 bytes  = pool index
        # 32 bytes = creator
        # 32 bytes = base mint

        creator = Pubkey.from_bytes(decoded[11:43])
        base_mint = Pubkey.from_bytes(decoded[43:75])

        print()
        print("Pool:", pool_address)
        print("Base mint:", base_mint)
        print("Creator:", creator)

        if base_mint != token:
            print("❓ Base mint does not match token")
            continue

        pump_authority, bump = Pubkey.find_program_address(
            [b"pool-authority", bytes(base_mint)],
            PUMP_PROGRAM
        )

        print("Pump pool authority:", pump_authority)

        if creator == pump_authority:
            print("🔥 CANONICAL PUMPSWAP POOL")
            print("🔥 LP STATUS: BURNED")
        else:
            print("❓ NOT CONFIRMED AS CANONICAL")
            print("❓ LP STATUS: UNABLE TO VERIFY")


if __name__ == "__main__":
    asyncio.run(main())
