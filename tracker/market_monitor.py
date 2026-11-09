"""Periodic DexScreener market-cap snapshots for qualified tracker entries."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .database import TrackerDatabase, MAX_TRADES

logger = logging.getLogger(__name__)
DEX_BATCH_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
BATCH_SIZE = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_cap(pair: dict[str, Any]) -> float:
    raw = pair.get("marketCap") or pair.get("fdv") or 0
    try:
        value = float(raw)
        return value if value > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


async def fetch_market_caps(
    session: aiohttp.ClientSession, addresses: list[str]
) -> dict[str, float]:
    """Fetch current market caps in DexScreener batches; omit missing/invalid tokens."""
    found: dict[str, tuple[float, float]] = {}
    for start in range(0, len(addresses), BATCH_SIZE):
        batch = addresses[start:start + BATCH_SIZE]
        url = DEX_BATCH_URL.format(",".join(batch))
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning("Tracker market-cap request returned HTTP %s", response.status)
                    continue
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            logger.exception("Tracker market-cap request failed")
            continue
        for pair in payload.get("pairs") or []:
            if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                continue
            base = pair.get("baseToken") or {}
            address = str(base.get("address") or "")
            mc = _market_cap(pair)
            if not address or address not in batch or mc <= 0:
                continue
            try:
                liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
            except (TypeError, ValueError):
                liquidity = 0.0
            previous = found.get(address)
            if previous is None or liquidity > previous[0]:
                found[address] = (liquidity, mc)
    return {address: item[1] for address, item in found.items()}


async def update_once(
    database: TrackerDatabase,
    session: aiohttp.ClientSession,
) -> dict[str, int]:
    tokens = database.list_tokens()
    if not tokens:
        return {"tracked": 0, "updated": 0, "missing": 0}
    addresses = [str(token["address"]) for token in tokens]
    values = await fetch_market_caps(session, addresses)
    updated = 0
    observed_at = _now()
    for address, market_cap in values.items():
        if database.record_market_cap(address, market_cap, observed_at):
            updated += 1
    return {"tracked": len(addresses), "updated": updated, "missing": len(addresses) - updated}


async def market_cap_monitor(
    database: TrackerDatabase | None = None,
    interval_seconds: int = 300,
) -> None:
    """Run continuously; missing market data never overwrites a valid snapshot."""
    db = database or TrackerDatabase()
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                count = db.count()
                if count >= MAX_TRADES:
                    logger.info("TRACKER has reached %s/%s qualified tokens.", count, MAX_TRADES)
                result = await update_once(db, session)
                logger.info(
                    "TRACKER market-cap update: %s tracked, %s updated, %s temporarily missing",
                    result["tracked"], result["updated"], result["missing"],
                )
            except Exception:
                logger.exception("Tracker market-cap cycle failed; will retry.")
            await asyncio.sleep(max(60, int(interval_seconds)))
