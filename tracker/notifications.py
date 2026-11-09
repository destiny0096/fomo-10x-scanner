"""Progress notifications sent through the scanner's existing Telegram bot."""
from __future__ import annotations

import logging
import os

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


async def send_progress_notification(message: str) -> bool:
    """Send using the same Telegram credentials as the scanner; never raise."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Tracker Telegram notification skipped: scanner Telegram credentials are missing")
        return False

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
