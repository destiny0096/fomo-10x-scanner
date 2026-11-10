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
_notification_delivery_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()


async def deliver_pending_notifications(database: TrackerDatabase | None = None) -> int:
    """Deliver durable milestone events in order; failed sends remain queued for retry."""
    db = database or TrackerDatabase()
    delivered = 0
    async with _notification_delivery_lock:
        while True:
            event = db.claim_next_notification()
            if event is None:
                break
            milestone = event["milestone"]
            try:
                message = progress_message(milestone, event["tokens"])
                sent = bool(message) and await send_progress_notification(message)
            except Exception:
                logger.exception("Tracker milestone %s notification failed", milestone)
                sent = False
            db.finish_notification(milestone, sent=sent)
            if not sent:
                break
            delivered += 1
    return delivered


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

        # Milestones are written transactionally with each new token. Drain the
        # durable outbox so concurrent inserts cannot skip a boundary and failed
        # Telegram sends can be retried on the next token or process startup.
        if result.get("status") == "qualified":
            await deliver_pending_notifications(database)
            count = database.count()
            if count == 100:
                configured_export = os.getenv("TRACKER_EXPORT_PATH", "").strip()
                export_path = (
                    Path(configured_export).expanduser()
                    if configured_export
                    else database.path.parent / "tracker_results.csv"
                )
                try:
                    if export_path.resolve() == database.path.resolve():
                        raise ValueError("Tracker results export cannot overwrite the live database")
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


async def drain_tracking_tasks(timeout_seconds: float = 20.0) -> None:
    """Give scheduled tracker work a bounded chance to finish during shutdown."""
    tasks = {task for task in _background_tasks if not task.done()}
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=max(0.0, timeout_seconds))
    for task in pending:
        logger.warning("Cancelling unfinished tracker task during shutdown")
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
