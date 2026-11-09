"""Non-blocking, failure-isolated bridge from scanner alerts to Tracker Test 4."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .pipeline import evaluate_and_record

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


async def track_alerted_token(token: dict[str, Any]) -> dict[str, Any]:
    """Run tracker qualification without allowing errors to escape into scanner code."""
    try:
        result = await evaluate_and_record(token)
        logger.info(
            "TRACKER %s %s: %s",
            token.get("symbol") or "",
            token.get("address") or "",
            result.get("status", "unknown"),
        )
        if result.get("status") in {"rejected", "evidence_error"}:
            logger.info("TRACKER detail for %s: %s", token.get("address"), result.get("reason", ""))
        return result
    except Exception:
        logger.exception("Tracker task failed for %s", token.get("address"))
        return {"status": "tracker_error"}


def schedule_tracking(token: dict[str, Any]) -> bool:
    """Schedule background tracking; return False only if no event loop is running."""
    try:
        task = asyncio.create_task(track_alerted_token(dict(token)))
    except RuntimeError:
        logger.exception("Could not schedule tracker task: no active event loop")
        return False
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True
