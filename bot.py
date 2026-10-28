import os
import asyncio
import logging
import time
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

from security_test import check_security, security_summary
from lp_test import check_lp_status, lp_status_text
from sell_route_test import check_sell_route, sell_route_text


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MIN_MC = float(os.getenv("MIN_MC", "30000"))
MAX_MC = float(os.getenv("MAX_MC", "500000"))
MIN_LIQ = float(os.getenv("MIN_LIQUIDITY", "6000"))
MIN_VOL = float(os.getenv("MIN_VOLUME", "5000"))
MIN_VOL_5M = float(os.getenv("MIN_VOL_5M", "3000"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "80"))

MIN_BUY_PRESSURE = float(
    os.getenv("MIN_BUY_PRESSURE", "60")
)

MIN_MOMENTUM = float(
    os.getenv("MIN_MOMENTUM", "10")
)

POLL_SECONDS = max(
    30,
    int(os.getenv("POLL_SECONDS", "120"))
)

BASE = "https://api.dexscreener.com"
HEAD = {}

# DexScreener token endpoint supports batches of up to 30 addresses.
BATCH_SIZE = 30

# Keep candidates for up to 30 minutes after their last appearance
# in the latest token-profile feed.
CANDIDATE_TTL_SECONDS = 30 * 60

# Bound memory usage.
MAX_CANDIDATES = 500

# In-memory candidate tracking.
# address -> last time seen in the profile feed
candidates = {}

# Tokens for which a Telegram alert was successfully sent.
alerted = set()

# Round-robin cursor for processing tracked candidates.
candidate_cursor = 0


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


# ============================================================
# HEALTH SERVER
# ============================================================

async def health(request):
    return web.Response(
        text="FOMO 10X Scanner is running",
        status=200,
    )


async def start_health_server():
    port = int(os.getenv("PORT", "3000"))

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logging.info(
        "Health server listening on port %s",
        port,
    )

    return runner


# ============================================================
# HTTP HELPERS
# ============================================================

async def get(session, path, params=None):
    async with session.get(
        BASE + path,
        headers=HEAD,
        params=params,
        timeout=20,
    ) as response:

        data = await response.json()

        if response.status >= 400:
            raise RuntimeError(
                f"{response.status}: {data}"
            )

        return data


async def tg(session, message):
    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    async with session.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    ) as response:

        if response.status >= 400:
            raise RuntimeError(await response.text())

        result = await response.json()

        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram rejected message: {result}"
            )


# ============================================================
# FORMATTING
# ============================================================

def money(value):
    value = float(value or 0)

    if value >= 1_000_000:
        return f"${value / 1e6:.2f}M"

    if value >= 1_000:
        return f"${value / 1e3:.1f}K"

    return f"${value:.0f}"


def token_age(pair):
    created = pair.get("pairCreatedAt")

    if not created:
        return "unknown"

    try:
        created_seconds = float(created) / 1000

        age_minutes = max(
            0,
            (
                datetime.now(timezone.utc).timestamp()
                - created_seconds
            ) / 60,
        )

        return f"{age_minutes:.0f} min"

    except (TypeError, ValueError, OverflowError):
        return "unknown"


# ============================================================
# MARKET SCORING
# ============================================================

def score(pair):
    mc = float(
        pair.get("marketCap")
        or pair.get("fdv")
        or 0
    )

    liquidity_data = pair.get("liquidity") or {}

    liq = float(
        liquidity_data.get("usd") or 0
    )

    volume_data = pair.get("volume") or {}

    vol = float(
        volume_data.get("h24") or 0
    )

    total_score = 0
    reasons = []

    if MIN_MC <= mc <= MAX_MC:
        total_score += 25
        reasons.append("target MC")

    if liq >= MIN_LIQ:
        total_score += 25
        reasons.append("liquidity")

    if vol >= MIN_VOL:
        total_score += 25
        reasons.append("volume")

    txns = pair.get("txns") or {}
    h24 = txns.get("h24") or {}

    buys = int(h24.get("buys") or 0)
    sells = int(h24.get("sells") or 0)

    if buys >= 20:
        total_score += 10
        reasons.append("active trading")

    if buys > sells:
        total_score += 5
        reasons.append("buy pressure")

    return total_score, mc, liq, vol, reasons


def get_momentum_and_buy_pressure(pair):
    price_change = pair.get("priceChange") or {}
    momentum = price_change.get("m5")

    txns = pair.get("txns") or {}
    transactions = txns.get("m5") or {}

    buys = int(transactions.get("buys") or 0)
    sells = int(transactions.get("sells") or 0)

    total_transactions = buys + sells

    if momentum is None:
        return None, None

    if total_transactions <= 0:
        return float(momentum), None

    buy_pressure = (
        buys / total_transactions
    ) * 100

    return float(momentum), buy_pressure


# ============================================================
# ALERT MESSAGE
# ============================================================

def alert(
    pair,
    total_score,
    mc,
    liq,
    vol,
    reasons,
    momentum,
    buy_pressure,
):
    token = pair.get("baseToken") or {}

    address = token.get("address") or ""
    name = token.get("name") or "Unknown"
    symbol = token.get("symbol") or "?"

    dex_url = pair.get(
        "url",
        f"https://dexscreener.com/solana/{address}",
    )

    return (
        "🚨 FOMO 10X WATCH ALERT\n\n"
        f"🪙 {name} (${symbol})\n"
        "⛓️ Solana\n"
        f"⏱️ Pair age: {token_age(pair)}\n"
        f"💰 MC: {money(mc)}\n"
        f"💧 Liquidity: {money(liq)}\n"
        f"📊 24h Volume: {money(vol)}\n"
        f"🟢 Buy Pressure: {buy_pressure:.1f}%\n"
        f"📈 5m Momentum: {momentum:+.2f}%\n"
        f"⭐ Score: {total_score}/100\n"
        f"📌 Signals: {', '.join(reasons)}\n\n"
        "⚠️ Screening only — NOT a 10× guarantee.\n\n"
        f"CA: {address}\n"
        f"🔗 {dex_url}"
    )


# ============================================================
# CANDIDATE TRACKING
# ============================================================

def update_candidates(profiles):
    """
    Remember newly discovered Solana tokens and refresh the
    last-seen time of tokens that appear in the profile feed.
    """

    now = time.time()

    for token in profiles:

        if token.get("chainId") != "solana":
            continue

        address = token.get("tokenAddress")

        if not address:
            continue

        if address in alerted:
            continue

        candidates[address] = now

    # Remove candidates that have not appeared recently.
    expired = [
        address
        for address, last_seen in candidates.items()
        if now - last_seen > CANDIDATE_TTL_SECONDS
    ]

    for address in expired:
        candidates.pop(address, None)

    # Keep memory bounded if the profile feed is unusually busy.
    if len(candidates) > MAX_CANDIDATES:

        oldest_first = sorted(
            candidates.items(),
            key=lambda item: item[1],
        )

        excess = len(candidates) - MAX_CANDIDATES

        for address, _ in oldest_first[:excess]:
            candidates.pop(address, None)

    logging.info(
        "Tracking %s candidates; %s already alerted",
        len(candidates),
        len(alerted),
    )


def next_candidate_batch():
    """
    Select a rotating batch so candidates outside the first
    30 are not permanently starved by newer candidates.
    """

    global candidate_cursor

    addresses = list(candidates.keys())

    if not addresses:
        return []

    count = len(addresses)

    start = candidate_cursor % count

    batch = [
        addresses[(start + offset) % count]
        for offset in range(min(BATCH_SIZE, count))
    ]

    candidate_cursor = (
        start + len(batch)
    ) % count

    return batch


# ============================================================
# PAIR SELECTION
# ============================================================

def best_solana_pairs(pairs):
    """
    Select the most liquid Solana pair returned for each token.
    """

    if not isinstance(pairs, list):
        logging.warning(
            "Unexpected token pair response"
        )
        return {}

    best_pairs = {}

    for pair in pairs:

        if pair.get("chainId") != "solana":
            continue

        token = pair.get("baseToken") or {}
        address = token.get("address")

        if not address:
            continue

        liquidity_data = pair.get("liquidity") or {}

        liquidity = float(
            liquidity_data.get("usd") or 0
        )

        current = best_pairs.get(address)

        if current is None:

            best_pairs[address] = pair

        else:

            current_liquidity = float(
                (current.get("liquidity") or {}).get("usd")
                or 0
            )

            if liquidity > current_liquidity:
                best_pairs[address] = pair

    return best_pairs


# ============================================================
# TOKEN EVALUATION
# ============================================================

async def evaluate_pair(session, pair):
    """
    Evaluate the latest available pair data.

    Return True only after the Telegram alert is sent
    successfully. Rejected tokens remain eligible for rechecks.
    """

    token = pair.get("baseToken") or {}
    address = token.get("address")

    if not address:
        return False

    if address in alerted:
        return False

    total_score, mc, liq, vol, reasons = score(pair)

    # Stage 1: market-cap, liquidity, volume and score.
    if not (MIN_MC <= mc <= MAX_MC):
        return False

    if liq < MIN_LIQ:
        return False

    if vol < MIN_VOL:
        return False

    if total_score < MIN_SCORE:
        return False

    # Stage 2: five-minute volume.
    volume_data = pair.get("volume") or {}
    vol_5m = float(volume_data.get("m5") or 0)

    if vol_5m < MIN_VOL_5M:
        logging.info(
            "REJECT %s: 5m volume $%.0f < $%.0f",
            token.get("symbol"),
            vol_5m,
            MIN_VOL_5M,
        )
        return False

    # Stage 3: momentum and buy pressure.
    momentum, buy_pressure = (
        get_momentum_and_buy_pressure(pair)
    )

    if momentum is None:
        logging.info(
            "REJECT %s: no m5 momentum data",
            token.get("symbol"),
        )
        return False

    if buy_pressure is None:
        logging.info(
            "REJECT %s: no m5 transaction data",
            token.get("symbol"),
        )
        return False

    if momentum < MIN_MOMENTUM:
        logging.info(
            "REJECT %s: momentum %.2f%% < %.2f%%",
            token.get("symbol"),
            momentum,
            MIN_MOMENTUM,
        )
        return False

    if buy_pressure < MIN_BUY_PRESSURE:
        logging.info(
            "REJECT %s: buy pressure %.1f%% < %.1f%%",
            token.get("symbol"),
            buy_pressure,
            MIN_BUY_PRESSURE,
        )
        return False

    # Stage 4: security, LP and sell-route checks.
    # Exceptions are handled by the scan loop; the candidate
    # stays eligible for another evaluation.
    security = await check_security(
        session,
        address,
    )

    lp_status = await check_lp_status(
        session,
        address,
    )

    sell_status = await check_sell_route(
        session,
        address,
    )

    message = (
        alert(
            pair,
            total_score,
            mc,
            liq,
            vol,
            reasons,
            momentum,
            buy_pressure,
        )
        + "\n\n🛡️ SECURITY\n"
        + security_summary(security)
        + "\n\n"
        + lp_status_text(lp_status)
        + "\n\n"
        + sell_route_text(sell_status)
    )

    # Only mark the token alerted after Telegram confirms success.
    await tg(session, message)

    alerted.add(address)
    candidates.pop(address, None)

    logging.info(
        "ALERT %s %s score=%s "
        "BUY_PRESSURE=%.1f%% "
        "MOMENTUM=%+.2f%% "
        "LP=%s SELL=%s",
        token.get("symbol"),
        address,
        total_score,
        buy_pressure,
        momentum,
        lp_status,
        sell_status,
    )

    return True


# ============================================================
# MAIN SCAN
# ============================================================

async def scan(session):
    profiles = await get(
        session,
        "/token-profiles/latest/v1",
    )

    if not isinstance(profiles, list):
        logging.warning(
            "Unexpected token profile response"
        )
        return

    update_candidates(profiles)

    batch = next_candidate_batch()

    if not batch:
        logging.info(
            "No Solana candidates to evaluate"
        )
        return

    # Process the selected batch. If the API request fails,
    # candidates remain stored for a later scan.
    address_list = ",".join(batch)

    pairs = await get(
        session,
        f"/tokens/v1/solana/{address_list}",
    )

    best_pairs = best_solana_pairs(pairs)

    # Evaluate only addresses in this batch.
    for address in batch:

        pair = best_pairs.get(address)

        if pair is None:
            continue

        try:
            await evaluate_pair(
                session,
                pair,
            )

        except Exception:
            logging.exception(
                "Evaluation failed for token %s; "
                "it will remain eligible for rechecking",
                address,
            )


# ============================================================
# APPLICATION LOOP
# ============================================================

async def main():
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        timeout=timeout,
    ) as session:

        while True:

            try:
                await scan(session)

            except Exception:
                logging.exception(
                    "Scan failed; will retry next cycle"
                )

            await asyncio.sleep(
                POLL_SECONDS
            )


async def run():
    runner = await start_health_server()

    try:
        await main()

    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(run())
