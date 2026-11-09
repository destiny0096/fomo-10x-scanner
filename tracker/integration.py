"""Non-blocking, failure-isolated bridge from scanner alerts to Tracker Test 4."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from .database import TrackerDatabase
from .notifications import progress_message, send_completion_export, send_progress_notification
from .export import export_results
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
            if count == 100:
                configured_export = os.getenv("TRACKER_EXPORT_PATH", "").strip()
                export_path = (
                    Path(configured_export).expanduser()
                    if configured_export
                    else database.path.parent / "tracker_results.csv"
                )
                try:
                    completed_csv = export_results(database.list_tokens(), export_path)
                    await send_completion_export(completed_csv)
                except Exception:
                    # Export/Telegram delivery must never interrupt scanner operation.
                    logger.exception("Could not export or deliver completed Tracker Test 4 cohort")
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
