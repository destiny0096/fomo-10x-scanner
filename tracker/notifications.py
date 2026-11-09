"""Progress notifications sent through the scanner's existing Telegram bot."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import aiohttp

from .report import build_report

logger = logging.getLogger(__name__)
PROGRESS_MILESTONES = {1, 25, 50, 75, 100}


def progress_message(count: int, tokens: list[dict]) -> str | None:
    """Build one notification only at the agreed cohort milestones."""
    if count not in PROGRESS_MILESTONES:
        return None
    if count >= 100:
        return "🏁 FOMO TRACKER TEST 4 COMPLETE\n\n" + build_report(tokens)
    return (
        "📊 FOMO TRACKER TEST 4 UPDATE\n"
        f"Qualified tokens recorded: {count}/100\n"
        f"Next milestone: {min(100, ((count // 25) + 1) * 25)}/100"
    )


def _telegram_credentials() -> tuple[str, str] | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Tracker Telegram notification skipped: scanner Telegram credentials are missing")
        return None
    return token, chat_id


async def send_progress_notification(message: str) -> bool:
    """Send using the same Telegram credentials as the scanner; never raise."""
    credentials = _telegram_credentials()
    if not credentials:
        return False
    token, chat_id = credentials
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            ) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400 or not payload.get("ok"):
                    logger.warning("Tracker Telegram notification failed: HTTP %s", response.status)
                    return False
                return True
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logger.exception("Tracker Telegram notification request failed")
        return False


async def send_completion_export(csv_path: str | Path) -> bool:
    """Deliver the full cohort CSV to the existing Telegram chat as a document."""
    path = Path(csv_path)
    if not path.is_file():
        logger.error("Tracker completion CSV does not exist: %s", path)
        return False
    credentials = _telegram_credentials()
    if not credentials:
        return False
    token, chat_id = credentials
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    timeout = aiohttp.ClientTimeout(total=30, connect=5)
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", chat_id)
        with path.open("rb") as handle:
            form.add_field(
                "document", handle, filename=path.name,
                content_type="text/csv",
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=form) as response:
                    payload = await response.json(content_type=None)
                    if response.status >= 400 or not payload.get("ok"):
                        logger.warning("Tracker CSV delivery failed: HTTP %s", response.status)
                        return False
                    return True
    except (OSError, aiohttp.ClientError, TimeoutError, ValueError):
        logger.exception("Tracker CSV delivery failed")
        return False
