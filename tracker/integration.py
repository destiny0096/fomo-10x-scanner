"""Non-blocking, failure-isolated bridge from scanner alerts to Tracker Test 4."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .database import TrackerDatabase
from .notifications import progress_message, send_progress_notification
from .pipeline import evaluate_and_record

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


async def track_alerted_token(token: dict[str, Any]) -> dict[str, Any]:
    """Qualify a scanner alert, persist it, and notify at cohort milestones."""
    try:
        database = TrackerDatabase()
        result = await evaluate_and_record(token, database=database)
        logger.info(
            "TRACKER %s %s: %s",
            token.get("symbol") or "",
            token.get("address") or "",
            result.get("status", "unknown"),
        )
        if result.get("status") in {"rejected", "evidence_error"}:
            logger.info("TRACKER detail for %s: %s", token.get("address"), result.get("reason", ""))

        # Only newly inserted records can trigger progress notifications.
        if result.get("status") == "qualified":
            count = database.count()
            message = progress_message(count, database.list_tokens())
            if message:
                await send_progress_notification(message)
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
