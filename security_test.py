import asyncio
import aiohttp
import base64
import struct


# ============================================================
# STANDALONE TEST TOKEN
# ============================================================

TOKEN_CA = "AeDgbAv64t53GiBPemV2geVB1pZkdBLPumjn25HWXpUo"

RPC_URL = "https://api.mainnet-beta.solana.com"

TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}

TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


# ============================================================
# HELPERS
# ============================================================

async def get_mint_account(session, token_ca):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            token_ca,
            {
                "encoding": "base64",
                "commitment": "finalized"
            }
        ]
    }

    async with session.post(
        RPC_URL,
        json=payload,
        timeout=20
    ) as response:

        data = await response.json()

    if "error" in data:
        raise RuntimeError(f"RPC ERROR: {data['error']}")

    value = data.get("result", {}).get("value")

    if value is None:
        raise RuntimeError("Token account not found")

    owner = value.get("owner")
    raw_data = value.get("data", [None])[0]

    if owner not in TOKEN_PROGRAMS:
        raise RuntimeError(
            f"Account is not owned by a Solana Token Program: {owner}"
        )

    if not raw_data:
        raise RuntimeError("No account data found")

    decoded = base64.b64decode(raw_data)

    return owner, decoded


def parse_basic_authorities(decoded):
    result = {
        "mint_authority": "unknown",
        "freeze_authority": "unknown",
    }

    # Mint authority:
    # 4-byte option + 32-byte public key
    if len(decoded) >= 36:
        authority_option = struct.unpack(
            "<I",
            decoded[0:4]
        )[0]

        if authority_option == 0:
            result["mint_authority"] = "disabled"

        elif authority_option == 1:
            result["mint_authority"] = "active"

    # Freeze authority:
    # Existing test logic uses bytes 46-49.
    if len(decoded) >= 50:
        freeze_authority_option = struct.unpack(
            "<I",
            decoded[46:50]
        )[0]

        if freeze_authority_option == 0:
            result["freeze_authority"] = "disabled"

        elif freeze_authority_option == 1:
            result["freeze_authority"] = "active"

    return result


def parse_token2022_extensions(decoded):
    """
    Preserve the extension parsing behavior from the existing
    standalone security test.

    The existing working test starts scanning at byte 166,
    so the integrated scanner intentionally uses the same
    starting point.
    """

    result = {
        "extensions": [],
        "permanent_delegate": False,
        "non_transferable": False,
        "transfer_fee_config": None,
    }

    if len(decoded) <= 166:
        return result

    offset = 166

    while offset + 4 <= len(decoded):

        extension_type = struct.unpack(
            "<H",
            decoded[offset:offset + 2]
        )[0]

        extension_length = struct.unpack(
            "<H",
            decoded[offset + 2:offset + 4]
        )[0]

        # End of extension data
        if extension_type == 0:
            break

        # Prevent malformed account data from causing
        # the scanner to read outside the account.
        if offset + 4 + extension_length > len(decoded):
            break

        result["extensions"].append({
            "type": extension_type,
            "length": extension_length,
        })

        # Permanent Delegate
        if extension_type == 13:
            result["permanent_delegate"] = True

        # Non-Transferable
        if extension_type == 9:
            result["non_transferable"] = True

        # Transfer Fee Config
        if extension_type == 1:

            extension = decoded[
                offset + 4:
                offset + 4 + extension_length
            ]

            if len(extension) == 108:

                transfer_fee_authority = extension[0:32]
                withdraw_authority = extension[32:64]

                older_max_fee = struct.unpack(
                    "<Q",
                    extension[80:88]
                )[0]

                older_bps = struct.unpack(
                    "<H",
                    extension[88:90]
                )[0]

                newer_max_fee = struct.unpack(
                    "<Q",
                    extension[98:106]
                )[0]

                newer_bps = struct.unpack(
                    "<H",
                    extension[106:108]
                )[0]

                decimals = 0

                # Mint decimals are normally stored at byte 44.
                if len(decoded) > 44:
                    decimals = decoded[44]

                result["transfer_fee_config"] = {
                    "older_bps": older_bps,
                    "older_percent": older_bps / 100,

                    "older_max_fee": older_max_fee,
                    "older_max_fee_ui": (
                        older_max_fee / (10 ** decimals)
                        if decimals >= 0
                        else older_max_fee
                    ),

                    "newer_bps": newer_bps,
                    "newer_percent": newer_bps / 100,

                    "newer_max_fee": newer_max_fee,
                    "newer_max_fee_ui": (
                        newer_max_fee / (10 ** decimals)
                        if decimals >= 0
                        else newer_max_fee
                    ),

                    "transfer_fee_authority": any(
                        transfer_fee_authority
                    ),

                    "withdraw_authority": any(
                        withdraw_authority
                    ),
                }

        offset += 4 + extension_length

    return result


# ============================================================
# MAIN FUNCTION USED BY BOT.PY
# ============================================================

async def check_security(session, token_ca):
    """
    Run the security checks for a token CA.

    This is the function imported by bot.py.
    """

    result = {
        "ok": False,
        "token_ca": token_ca,
        "token_program": None,
        "account_size": 0,

        "mint_authority": "unknown",
        "freeze_authority": "unknown",

        "extensions": [],
        "permanent_delegate": False,
        "non_transferable": False,

        "transfer_fee_config": None,

        "error": None,
    }

    try:
        owner, decoded = await get_mint_account(
            session,
            token_ca
        )

        result["ok"] = True
        result["token_program"] = owner
        result["account_size"] = len(decoded)

        # Basic authorities
        authorities = parse_basic_authorities(decoded)

        result["mint_authority"] = authorities[
            "mint_authority"
        ]

        result["freeze_authority"] = authorities[
            "freeze_authority"
        ]

        # Token-2022 extensions
        if owner == TOKEN_2022_PROGRAM:

            extensions = parse_token2022_extensions(
                decoded
            )

            result["extensions"] = extensions[
                "extensions"
            ]

            result["permanent_delegate"] = extensions[
                "permanent_delegate"
            ]

            result["non_transferable"] = extensions[
                "non_transferable"
            ]

            result["transfer_fee_config"] = extensions[
                "transfer_fee_config"
            ]

        return result

    except Exception as e:

        result["error"] = str(e)

        return result


# ============================================================
# SECURITY SUMMARY USED BY BOT.PY
# ============================================================

def security_summary(security):
    """
    Convert the security result into a short Telegram-friendly
    summary.
    """

    if not security:
        return "❌ Security check returned no data"

    if security.get("error"):
        return (
            f"⚠️ Security check error:\n"
            f"{security['error']}"
        )

    lines = []

    # Mint Authority
    mint = security.get("mint_authority")

    if mint == "disabled":
        lines.append("🔒 Mint Authority: DISABLED")

    elif mint == "active":
        lines.append("⚠️ Mint Authority: ACTIVE")

    else:
        lines.append("❓ Mint Authority: UNKNOWN")

    # Freeze Authority
    freeze = security.get("freeze_authority")

    if freeze == "disabled":
        lines.append("🔒 Freeze Authority: DISABLED")

    elif freeze == "active":
        lines.append("⚠️ Freeze Authority: ACTIVE")

    else:
        lines.append("❓ Freeze Authority: UNKNOWN")

    # Token-2022
    if security.get("token_program") == TOKEN_2022_PROGRAM:

        lines.append("🧩 Token Program: TOKEN-2022")

        # Permanent Delegate
        if security.get("permanent_delegate"):
            lines.append(
                "⚠️ Permanent Delegate: ACTIVE"
            )
        else:
            lines.append(
                "🔒 Permanent Delegate: NOT DETECTED"
            )

        # Non-transferable
        if security.get("non_transferable"):
            lines.append(
                "🚫 Non-Transferable: ACTIVE"
            )
        else:
            lines.append(
                "🔓 Non-Transferable: NOT DETECTED"
            )

        # Transfer fee
        fee = security.get("transfer_fee_config")

        if fee:

            lines.append(
                "💰 Transfer Fee Config: DETECTED"
            )

            lines.append(
                f"• Fee: {fee['older_percent']:.2f}% / "
                f"{fee['newer_percent']:.2f}%"
            )

            if fee["transfer_fee_authority"]:
                lines.append(
                    "⚠️ Transfer Fee Authority: ACTIVE"
                )
            else:
                lines.append(
                    "🔒 Transfer Fee Authority: DISABLED"
                )

            if fee["withdraw_authority"]:
                lines.append(
                    "⚠️ Withdraw Authority: ACTIVE"
                )
            else:
                lines.append(
                    "🔒 Withdraw Authority: DISABLED"
                )

        else:
            lines.append(
                "🔓 Transfer Fee Config: NOT DETECTED"
            )

    else:
        lines.append(
            "🧩 Token Program: STANDARD SPL TOKEN"
        )

    return "\n".join(lines)


# ============================================================
# ORIGINAL STANDALONE SECURITY TEST
# ============================================================

async def main():

    async with aiohttp.ClientSession() as session:

        security = await check_security(
            session,
            TOKEN_CA
        )

    print()
    print("========================================")
    print("       FOMO SECURITY TEST")
    print("========================================")
    print()

    if security.get("error"):
        print("❌ ERROR:", security["error"])
        return

    print("✅ Token Mint confirmed")
    print("CA:", security["token_ca"])
    print("Token Program:", security["token_program"])
    print("Account size:", security["account_size"])
    print()

    # Mint Authority
    if security["mint_authority"] == "disabled":
        print("🔒 MINT AUTHORITY: DISABLED")

    elif security["mint_authority"] == "active":
        print("⚠️ MINT AUTHORITY: ACTIVE")

    else:
        print("❌ MINT AUTHORITY: UNKNOWN")

    # Freeze Authority
    if security["freeze_authority"] == "disabled":
        print("🔒 FREEZE AUTHORITY: DISABLED")

    elif security["freeze_authority"] == "active":
        print("⚠️ FREEZE AUTHORITY: ACTIVE")

    else:
        print("❌ FREEZE AUTHORITY: UNKNOWN")

    # Token-2022 extensions
    if security["token_program"] == TOKEN_2022_PROGRAM:

        print()
        print("🔍 TOKEN-2022 EXTENSIONS:")

        extensions = security.get("extensions") or []

        if not extensions:
            print("None detected")

        else:

            for extension in extensions:
                print(
                    f"⚠️ Extension type "
                    f"{extension['type']} "
                    f"(length {extension['length']})"
                )

        if security.get("permanent_delegate"):
            print(
                "⚠️ PERMANENT DELEGATE: ACTIVE"
            )

        if security.get("non_transferable"):
            print(
                "🚫 NON-TRANSFERABLE: ACTIVE"
            )

        # Transfer Fee Config
        fee = security.get("transfer_fee_config")

        if fee:

            print()
            print("💰 TRANSFER FEE CONFIG:")

            print(
                f"Older fee: "
                f"{fee['older_percent']:.2f}%"
            )

            print(
                f"Older maximum fee: "
                f"{fee['older_max_fee_ui']:.8f}"
            )

            print(
                f"Newer fee: "
                f"{fee['newer_percent']:.2f}%"
            )

            print(
                f"Newer maximum fee: "
                f"{fee['newer_max_fee_ui']:.8f}"
            )

            if fee["transfer_fee_authority"]:
                print(
                    "⚠️ Transfer Fee Authority: ACTIVE"
                )
            else:
                print(
                    "🔒 Transfer Fee Authority: DISABLED"
                )

            if fee["withdraw_authority"]:
                print(
                    "⚠️ Withdraw Authority: ACTIVE"
                )
            else:
                print(
                    "🔒 Withdraw Authority: DISABLED"
                )

    print()
    print("========================================")
    print("         SECURITY SUMMARY")
    print("========================================")
    print()
    print(security_summary(security))
    print()


if __name__ == "__main__":
    asyncio.run(main())    

                
