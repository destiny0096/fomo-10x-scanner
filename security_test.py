import asyncio
import aiohttp
import base64
import struct

TOKEN_CA = "AeDgbAv64t53GiBPemV2geVB1pZkdBLPumjn25HWXpUo"

DEX_URL = f"https://api.dexscreener.com/latest/dex/tokens/{TOKEN_CA}"

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

        async with session.get(DEX_URL) as dex_response:
            dex_data = await dex_response.json()

        print("🔎 DEXSCREENER POOLS FOUND:", len(dex_data.get("pairs", [])))

    if "error" in data:
        print("❌ RPC ERROR:", data["error"])
        return

        

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

    # Mint Authority is stored in the first 36 bytes
    # 4-byte option + 32-byte public key
    if len(decoded) < 36:
        print("❌ Account data is too short to contain Mint Authority")
        print("Account size:", len(decoded))
        return

    authority_option = struct.unpack("<I", decoded[0:4])[0]

    print("✅ Token Mint confirmed")
    print("CA:", TOKEN_CA)
    print("Token Program:", owner)
    print("Account size:", len(decoded))

    if authority_option == 0:
        print("🔒 MINT AUTHORITY: DISABLED")
    elif authority_option == 1:
        print("⚠️ MINT AUTHORITY: ACTIVE")
    else:
        print("❌ Unknown mint authority value:", authority_option)
    # Freeze Authority is stored at bytes 46-49
    if len(decoded) < 50:
        print("❌ Account data is too short to contain Freeze Authority")
        return

    freeze_authority_option = struct.unpack("<I", decoded[46:50])[0]

    if freeze_authority_option == 0:
        print("🔒 FREEZE AUTHORITY: DISABLED")
    elif freeze_authority_option == 1:
        print("⚠️ FREEZE AUTHORITY: ACTIVE")
    else:
        print("❌ Unknown freeze authority value:", freeze_authority_option)
    

         # Check for Token-2022 extensions
    if owner == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb":
        print("🔍 TOKEN-2022 EXTENSIONS:")

        if len(decoded) <= 166:
            print("None detected")
        else:
            offset = 166
            found = False

            while offset + 4 <= len(decoded):
                extension_type = struct.unpack(
                    "<H", decoded[offset:offset + 2]
                )[0]

                extension_length = struct.unpack(
                    "<H", decoded[offset + 2:offset + 4]
                )[0]

                if extension_type == 13:
                    print("⚠️ PERMANENT DELEGATE: ACTIVE")
                    
                if extension_type == 9:
                    print("🚫 NON-TRANSFERABLE: ACTIVE")
  
                if extension_type == 0:
                    break

                if offset + 4 + extension_length > len(decoded):
                    print("❌ Invalid extension data")
                    break

                print(
                    f"⚠️ Extension type {extension_type} "
                    f"(length {extension_length})"
                )

                found = True
                offset += 4 + extension_length

            if not found:
                print("None detected")
            
    # Check Transfer Fee Config
    if owner == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb":
        offset = 166

        while offset + 4 <= len(decoded):
            extension_type = struct.unpack(
                "<H", decoded[offset:offset + 2]
            )[0]

            extension_length = struct.unpack(
                "<H", decoded[offset + 2:offset + 4]
            )[0]

            if extension_type == 0:
                break

            if offset + 4 + extension_length > len(decoded):
                break

            if extension_type == 1:
                extension = decoded[
                    offset + 4:offset + 4 + extension_length
                ]

                if len(extension) != 108:
                    print("❌ Invalid Transfer Fee Config length")
                    break

                transfer_fee_authority = extension[0:32]
                withdraw_authority = extension[32:64]

                older_max_fee = struct.unpack(
                    "<Q", extension[80:88]
                )[0]

                older_bps = struct.unpack(
                    "<H", extension[88:90]
                )[0]

                newer_max_fee = struct.unpack(
                    "<Q", extension[98:106]
                )[0]

                newer_bps = struct.unpack(
                    "<H", extension[106:108]
                )[0]

                decimals = decoded[44]

                print("💰 TRANSFER FEE CONFIG:")
                print(f"Older fee: {older_bps / 100:.2f}%")
                print(
                    f"Older maximum fee: "
                    f"{older_max_fee / (10 ** decimals):.8f}"
                )
                print(f"Newer fee: {newer_bps / 100:.2f}%")
                print(
                    f"Newer maximum fee: "
                    f"{newer_max_fee / (10 ** decimals):.8f}"
                )

                if any(transfer_fee_authority):
                    print("⚠️ Transfer Fee Authority: ACTIVE")
                else:
                    print("🔒 Transfer Fee Authority: DISABLED")

                if any(withdraw_authority):
                    print("⚠️ Withdraw Authority: ACTIVE")
                else:
                    print("🔒 Withdraw Authority: DISABLED")

                break

            offset += 4 + extension_length     
                    
                
if __name__ == "__main__":
    asyncio.run(main())

    
