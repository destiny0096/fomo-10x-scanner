import asyncio
import aiohttp
import base64
import struct

TOKEN_CA = "AeDgbAv64t53GiBPemV2geVB1pZkdBLPumjn25HWXpUo"

RPC_URL = "https://api.mainnet-beta.solana.com"

TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}


async def main():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            TOKEN_CA,
            {
                "encoding": "base64",
                "commitment": "finalized"
            }
        ]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(RPC_URL, json=payload) as response:
            data = await response.json()

    if "error" in data:
        print("❌ RPC ERROR:", data["error"])
        return

    value = data.get("result", {}).get("value")

    if value is None:
        print("❌ Token account not found")
        return

    owner = value.get("owner")
    raw_data = value.get("data", [None])[0]

    if owner not in TOKEN_PROGRAMS:
        print("❌ Account is not owned by a Solana Token Program")
        print("Owner:", owner)
        return

    if not raw_data:
        print("❌ No account data found")
        return

    decoded = base64.b64decode(raw_data)

    if len(decoded) != 82:
        print("❌ Account is not a standard 82-byte Token Mint")
        print("Account size:", len(decoded))
        return

    authority_option = struct.unpack("<I", decoded[0:4])[0]

    print("✅ Token Mint confirmed")
    print("CA:", TOKEN_CA)

    if authority_option == 0:
        print("🔒 MINT AUTHORITY: DISABLED")
    elif authority_option == 1:
        print("⚠️ MINT AUTHORITY: ACTIVE")
    else:
        print("❌ Unknown mint authority value:", authority_option)


if __name__ == "__main__":
    asyncio.run(main())
