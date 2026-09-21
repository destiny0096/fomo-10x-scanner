import asyncio
import aiohttp
import base64
from solders.pubkey import Pubkey

TOKEN_CA = "So11111111111111111111111111111111111111112"

RPC_URL = "https://api.mainnet-beta.solana.com"

PUMPSWAP_PROGRAM = Pubkey.from_string(
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)

PUMP_PROGRAM = Pubkey.from_string(
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
)


async def check_lp_status(session, token_ca):
    """
    Check the LP status for a Solana token.

    Possible results:
        BURNED
        LOCKED
        UNABLE TO VERIFY

    Current verified detection:
        Canonical PumpSwap pool -> BURNED

    LOCKED is reserved for a future verified lock-detection
    method. We do not guess or assume that a pool is locked.
    """

    try:
        token = Pubkey.from_string(token_ca)
    except Exception:
        return "UNABLE TO VERIFY"

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
                            "bytes": token_ca
                        }
                    }
                ]
            }
        ]
    }

    try:
        async with session.post(
            RPC_URL,
            json=payload,
            timeout=20
        ) as response:
            data = await response.json()

    except Exception:
        return "UNABLE TO VERIFY"

    if "error" in data:
        return "UNABLE TO VERIFY"

    accounts = data.get("result", [])

    if not accounts:
        return "UNABLE TO VERIFY"

    for account in accounts:
        try:
            raw_data = account["account"]["data"][0]
            decoded = base64.b64decode(raw_data)

            if len(decoded) < 75:
                continue

            # PumpSwap Pool layout:
            # 8 bytes  = Anchor discriminator
            # 1 byte   = bump
            # 2 bytes  = pool index
            # 32 bytes = creator
            # 32 bytes = base mint

            creator = Pubkey.from_bytes(decoded[11:43])
            base_mint = Pubkey.from_bytes(decoded[43:75])

            if base_mint != token:
                continue

            pump_authority, bump = Pubkey.find_program_address(
                [b"pool-authority", bytes(base_mint)],
                PUMP_PROGRAM
            )

            # Verified canonical PumpSwap pool.
            # Keep the existing working interpretation:
            # canonical PumpSwap pool = LP BURNED.
            if creator == pump_authority:
                return "BURNED"

            # A pool was found, but it was not confirmed as
            # the canonical PumpSwap pool.
            # Do NOT call it locked without a real lock check.
            continue

        except Exception:
            continue

    return "UNABLE TO VERIFY"


def lp_status_text(status):
    """
    Convert the LP status into the Telegram-friendly text.
    """

    if status == "BURNED":
        return "🔥 LP STATUS: BURNED"

    if status == "LOCKED":
        return "🔒 LP STATUS: LOCKED"

    return "❓ LP STATUS: UNABLE TO VERIFY"


async def main():
    print("🔍 Checking PumpSwap pool...")
    print("Token:", TOKEN_CA)

    try:
        token = Pubkey.from_string(TOKEN_CA)
    except Exception:
        print("❌ Invalid token address")
        return

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

        try:
            async with session.post(
                RPC_URL,
                json=payload,
                timeout=20
            ) as response:
                data = await response.json()

        except Exception as e:
            print("❌ RPC ERROR:", e)
            return

    if "error" in data:
        print("❌ RPC ERROR:", data["error"])
        return

    accounts = data.get("result", [])

    if not accounts:
        print("❓ No PumpSwap pool found")
        print("❓ LP STATUS: UNABLE TO VERIFY")
        return

    print(f"✅ PumpSwap pool(s) found: {len(accounts)}")

    found_valid_pool = False

    for account in accounts:

        try:
            pool_address = account["pubkey"]
            raw_data = account["account"]["data"][0]
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

            found_valid_pool = True

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

        except Exception as e:
            print("❓ Could not verify pool:", e)

    if not found_valid_pool:
        print()
        print("❓ LP STATUS: UNABLE TO VERIFY")


if __name__ == "__main__":
    asyncio.run(main())
