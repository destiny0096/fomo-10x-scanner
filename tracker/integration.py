"""Failure-isolated bridge from scanner alerts to the durable tracker queue."""
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
_candidate_worker_lock = asyncio.Lock()
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


async def deliver_pending_completion_export(database: TrackerDatabase | None = None) -> bool:
    """Retry the durable final CSV delivery until Telegram confirms receipt."""
    db = database or TrackerDatabase()
    if not db.claim_completion_export():
        return False
    configured_export = os.getenv("TRACKER_EXPORT_PATH", "").strip()
    export_path = (Path(configured_export).expanduser() if configured_export
                   else db.path.parent / "tracker_results.csv")
    sent = False
    try:
        if export_path.resolve() == db.path.resolve():
            raise ValueError("Tracker results export cannot overwrite the live database")
        completed_csv = export_results(db.list_tokens(), export_path)
        sent = await send_completion_export(completed_csv)
        return sent
    except Exception:
        logger.exception("Could not export or deliver completed Tracker Test 4 cohort")
        return False
    finally:
        db.finish_completion_export(sent=sent)


async def _completion_export_retry_worker() -> None:
    """Keep retrying a failed final CSV delivery, including after process restarts."""
    database = TrackerDatabase(timeout_seconds=1.0)
    while database.pending_completion_export_count() > 0:
        await deliver_pending_completion_export(database)
        if database.pending_completion_export_count() > 0:
            await asyncio.sleep(60)


def _start_completion_export_worker() -> bool:
    try:
        task = asyncio.create_task(
            _completion_export_retry_worker(), name="fomo-tracker-completion-export"
        )
    except Exception:
        logger.exception("Could not start tracker completion-export retry worker")
        return False
    _register_task(task)
    return True


async def track_alerted_token(token: dict[str, Any]) -> dict[str, Any]:
    """Qualify a scanner alert, persist it, and notify at cohort milestones."""
    try:
        database = TrackerDatabase()
        result = await evaluate_and_record(token, database=database)
        logger.info("TRACKER %s %s: %s", token.get("symbol") or "",
                    token.get("address") or "", result.get("status", "unknown"))
        if result.get("status") in {"rejected", "evidence_error"}:
            logger.info("TRACKER detail for %s: %s", token.get("address"), result.get("reason", ""))

        if result.get("status") == "qualified":
            await deliver_pending_notifications(database)
            if database.pending_completion_export_count() > 0:
                await deliver_pending_completion_export(database)
                if database.pending_completion_export_count() > 0:
                    _start_completion_export_worker()
        return result
    except Exception:
        logger.exception("Tracker task failed for %s", token.get("address"))
        return {"status": "tracker_error"}


async def process_pending_candidates(*, wait_for_retry: bool = False) -> int:
    """Drain durable scanner-alert work; optionally poll until deferred work is ready."""
    processed = 0
    async with _candidate_worker_lock:
        database = TrackerDatabase(timeout_seconds=1.0)
        while True:
            candidate = database.claim_next_candidate()
            if candidate is None:
                if wait_for_retry and database.pending_candidate_count() > 0:
                    await asyncio.sleep(60)
                    continue
                break
            address = candidate["address"]
            try:
                result = await track_alerted_token(candidate)
            except asyncio.CancelledError:
                try:
                    database.retry_candidate(address, "worker cancelled during evaluation")
                except Exception:
                    logger.exception("Could not release cancelled tracker candidate %s", address)
                raise

            status = result.get("status")
            if status in {"tracker_error", "evidence_error"}:
                # A source/database outage is transient. Leave it queued for the
                # next worker start rather than hot-looping on the same candidate.
                database.retry_candidate(address, result.get("reason", status))
                logger.warning("Tracker candidate %s deferred for retry: %s", address, status)
                if wait_for_retry:
                    await asyncio.sleep(60)
                    continue
                break

            database.complete_candidate(address)
            processed += 1
    return processed


def _register_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)

    def _task_finished(completed: asyncio.Task) -> None:
        _background_tasks.discard(completed)
        if completed.cancelled():
            return
        try:
            error = completed.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            logger.error("Unexpected uncaught tracker task error",
                         exc_info=(type(error), error, error.__traceback__))

    task.add_done_callback(_task_finished)


def _start_candidate_worker() -> bool:
    try:
        task = asyncio.create_task(process_pending_candidates(wait_for_retry=True), name="fomo-tracker-candidate-queue")
    except Exception:
        logger.exception("Could not start durable tracker candidate worker")
        return False
    _register_task(task)
    return True


def resume_pending_tracking() -> bool:
    """Start processing candidates left pending by a previous process."""
    try:
        database = TrackerDatabase(timeout_seconds=1.0)
        candidate_started = (
            True if database.pending_candidate_count() == 0 else _start_candidate_worker()
        )
        export_started = (
            True if database.pending_completion_export_count() == 0
            else _start_completion_export_worker()
        )
        return candidate_started and export_started
    except Exception:
        logger.exception("Could not inspect durable tracker candidate queue at startup")
        return False


def schedule_tracking(token: dict[str, Any]) -> bool:
    """Persist first, then wake the worker; scanner alerts remain failure-isolated."""
    try:
        database = TrackerDatabase(timeout_seconds=0.5)
        queued = database.enqueue_candidate(dict(token))
        if queued == "invalid":
            logger.warning("Tracker candidate has no address; not queued")
            return False
        if queued == "duplicate":
            logger.info("Tracker candidate %s already exists in durable queue", token.get("address"))
        return _start_candidate_worker()
    except Exception:
        # The scanner alert has already been sent. A queue/database outage must
        # never undo it; attempt a best-effort in-memory evaluation as fallback.
        logger.exception("Could not persist tracker candidate %s; using volatile fallback",
                         token.get("address"))
        fallback_coroutine = track_alerted_token(dict(token))
        try:
            task = asyncio.create_task(fallback_coroutine)
        except Exception:
            # If there is no running loop, close the coroutine we just created
            # so Python does not emit an unawaited-coroutine warning.
            fallback_coroutine.close()
            logger.exception("Could not schedule volatile tracker fallback")
            return False
        _register_task(task)
        return True


async def drain_tracking_tasks(timeout_seconds: float = 20.0) -> None:
    """Give scheduled tracker work a bounded chance to finish during shutdown."""
    tasks = {task for task in _background_tasks if not task.done()}
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=max(0.0, timeout_seconds))
    for task in pending:
        logger.warning("Cancelling unfinished tracker task during shutdown")
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
