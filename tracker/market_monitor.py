"""Periodic DexScreener market-cap updates for qualified tracker tokens."""
import asyncio
import logging
import math
import os
import time
from datetime import datetime, timezone

import aiohttp

from .database import TrackerDatabase

log = logging.getLogger(__name__)
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
BATCH_SIZE = 30


def _market_cap(pair: dict) -> float | None:
    """Return reported market cap only; FDV is not interchangeable with market cap."""
    value = pair.get("marketCap")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


async def fetch_market_caps(session: aiohttp.ClientSession, addresses: list[str]) -> dict[str, float]:
    """Fetch Solana token pairs and select the highest-liquidity valid pair per mint."""
    found: dict[str, tuple[float, float]] = {}
    for start in range(0, len(addresses), BATCH_SIZE):
        batch = addresses[start:start + BATCH_SIZE]
        if not batch:
            continue
        url = DEXSCREENER_TOKEN_URL.format(",".join(batch))
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    log.warning("DexScreener market-cap request returned HTTP %s", response.status)
                    continue
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.warning("DexScreener market-cap request failed: %s", exc)
            continue

        requested = set(batch)
        for pair in payload.get("pairs") or []:
            if pair.get("chainId") != "solana":
                continue
            base = pair.get("baseToken") or {}
            address = str(base.get("address") or "")
            if address not in requested:
                continue
            market_cap = _market_cap(pair)
            if market_cap is None:
                continue
            try:
                liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
            except (TypeError, ValueError):
                liquidity = 0.0
            if not math.isfinite(liquidity) or liquidity < 0:
                liquidity = 0.0
            previous = found.get(address)
            if previous is None or liquidity > previous[0]:
                found[address] = (liquidity, market_cap)

    return {address: values[1] for address, values in found.items()}


async def update_once(database: TrackerDatabase, session: aiohttp.ClientSession) -> tuple[int, int]:
    tokens = database.list_tokens()
    addresses = [str(token.get("address") or "") for token in tokens if token.get("address")]
    if not addresses:
        return 0, 0
    market_caps = await fetch_market_caps(session, addresses)
    observed_at = datetime.now(timezone.utc).isoformat()
    updated = sum(
        1 for address, market_cap in market_caps.items()
        if database.record_market_cap(address, market_cap, observed_at)
    )
    return updated, len(addresses) - updated


async def market_cap_monitor(database: TrackerDatabase | None = None, interval_seconds: int = 300) -> None:
    """Keep updating the 100-token cohort; never stop just because it is full.

    Initialization and polling failures are contained so the optional tracker
    monitor can never prevent the primary scanner from running.
    """
    try:
        database = database or TrackerDatabase()
    except Exception:
        log.exception("Tracker database initialization failed; scanner will continue without market-cap monitoring")
        return

    try:
        interval = max(60, int(interval_seconds))
    except (TypeError, ValueError):
        interval = 300
    try:
        backup_interval = int(os.getenv("TRACKER_BACKUP_INTERVAL_SECONDS", "21600"))
        backup_interval = max(60, backup_interval) if backup_interval > 0 else 0
    except (TypeError, ValueError):
        log.warning("Invalid TRACKER_BACKUP_INTERVAL_SECONDS; using 21600 seconds")
        backup_interval = 21600
    last_backup = time.monotonic() - backup_interval if backup_interval else 0.0

    timeout = aiohttp.ClientTimeout(total=20, connect=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                try:
                    total = database.count()
                    updated, missing = await update_once(database, session)
                    log.info("Tracker market-cap monitor: %s/%s tokens recorded; updated=%s missing=%s",
                             total, database.count(), updated, missing)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Tracker market-cap monitor cycle failed")

                if backup_interval and time.monotonic() - last_backup >= backup_interval:
                    try:
                        from .backup import create_backup
                        backup_path = await asyncio.to_thread(create_backup)
                        log.info("Tracker database backup created: %s", backup_path)
                        last_backup = time.monotonic()
                    except Exception:
                        # Leave the timer due so a transient failure is retried next cycle.
                        log.exception("Scheduled tracker database backup failed")

                await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Tracker market-cap monitor could not start; scanner will continue")
