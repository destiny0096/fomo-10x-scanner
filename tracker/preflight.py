"""Production preflight for FOMO scanner + Tracker Test 4.

Run inside the deployment container with the real environment configured:
    python -m tracker.preflight

This performs read-only Telegram/DexScreener/Reddit API checks and a temporary
SQLite backup write test. It never sends a Telegram message and never prints
secrets.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

import aiohttp

from .database import TrackerDatabase

DEX_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
REDDIT_URL = "https://www.reddit.com/search.json"
TELEGRAM_API = "https://api.telegram.org"


def check_storage(env: Mapping[str, str] | None = None) -> list[tuple[str, bool, str]]:
    values = os.environ if env is None else env
    results: list[tuple[str, bool, str]] = []
    # Deplexo mounts its persistent app volume at /data. Use that
    # automatically when available so deployment needs no extra path variables.
    db_value = values.get("TRACKER_DB_PATH", "").strip()
    backup_value = values.get("TRACKER_BACKUP_DIR", "").strip()
    data_mount = Path("/data")
    if not db_value:
        if data_mount.is_dir() and os.access(data_mount, os.W_OK):
            db_value = str(data_mount / "tracker_data.db")
        else:
            results.append(("TRACKER_DB_PATH", False,
                            "Set TRACKER_DB_PATH or provide a writable persistent /data mount."))
    if not backup_value:
        if db_value:
            backup_value = str(Path(db_value).expanduser().parent / "tracker_backups")
        else:
            results.append(("TRACKER_BACKUP_DIR", False,
                            "Set TRACKER_BACKUP_DIR or provide a writable persistent /data mount."))
    if not db_value or not backup_value:
        return results

    db_path = Path(db_value).expanduser()
    backup_dir = Path(backup_value).expanduser()
    if not db_path.is_absolute() or not backup_dir.is_absolute():
        return [("storage paths", False, "Both TRACKER_DB_PATH and TRACKER_BACKUP_DIR must be absolute paths.")]

    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".fomo-preflight-", dir=db_path.parent, delete=True):
            pass
        with tempfile.NamedTemporaryFile(prefix=".fomo-preflight-", dir=backup_dir, delete=True):
            pass
        results.append(("storage writable", True, "Database and backup directories accept temporary writes."))

        same_device = db_path.parent.stat().st_dev == backup_dir.stat().st_dev
        require_separate = values.get("TRACKER_REQUIRE_SEPARATE_BACKUP_VOLUME", "0").strip().lower() not in {"0", "false", "no"}
        if same_device and require_separate:
            results.append(("backup independence", False,
                            "A separate backup filesystem was explicitly required but is not mounted."))
        elif same_device:
            results.append(("local backup", True,
                            "Backup directory is writable on the app volume. WARNING: this protects against some database errors, not loss of the entire app volume."))
        else:
            results.append(("backup independence", True, "Backup directory is on a different filesystem."))

        usage = shutil.disk_usage(db_path.parent)
        if usage.free < 100 * 1024 * 1024:
            results.append(("database free space", False, f"Less than 100 MB free ({usage.free // (1024 * 1024)} MB)."))
        else:
            results.append(("database free space", True, f"{usage.free // (1024 * 1024)} MB available."))

        database = TrackerDatabase(db_path)
        if not database.integrity_check():
            results.append(("SQLite integrity", False, "Live tracker database integrity_check failed."))
        else:
            results.append(("SQLite integrity", True, "Database opens and passes integrity_check."))

        descriptor, temporary_name = tempfile.mkstemp(prefix=".fomo-backup-test-", suffix=".db", dir=backup_dir)
        os.close(descriptor)
        temporary_backup = Path(temporary_name)
        try:
            database.backup_to(temporary_backup)
            results.append(("backup write and validation", True, "Temporary online backup succeeded and passed SQLite integrity_check."))
        finally:
            temporary_backup.unlink(missing_ok=True)
    except Exception as exc:
        results.append(("storage validation", False, f"{type(exc).__name__}: {exc}"))
    return results


async def check_services(env: Mapping[str, str] | None = None) -> list[tuple[str, bool, str]]:
    values = os.environ if env is None else env
    token = values.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = values.get("TELEGRAM_CHAT_ID", "").strip()
    results: list[tuple[str, bool, str]] = []
    if not token or not chat_id:
        return [("Telegram configuration", False, "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be configured.")]

    timeout = aiohttp.ClientTimeout(total=15, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for label, url, params in (
            ("Telegram bot authentication", f"{TELEGRAM_API}/bot{token}/getMe", None),
            ("Telegram destination access", f"{TELEGRAM_API}/bot{token}/getChat", {"chat_id": chat_id}),
            ("DexScreener API", DEX_URL, None),
            ("Reddit public attention source", REDDIT_URL, {"q": "solana", "sort": "new", "t": "week", "limit": "1"}),
        ):
            try:
                headers = {"User-Agent": "FOMO10XTracker/1.0 (deployment preflight)"}
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        results.append((label, False, f"HTTP {response.status}."))
                        continue
                    payload = await response.json(content_type=None)
                    if label.startswith("Telegram") and not payload.get("ok"):
                        results.append((label, False, "Telegram API rejected the read-only check."))
                    elif label == "DexScreener API" and not isinstance(payload, (list, dict)):
                        results.append((label, False, "Unexpected response format."))
                    elif label == "Reddit public attention source" and not isinstance(payload, dict):
                        results.append((label, False, "Unexpected response format."))
                    else:
                        results.append((label, True, "Read-only API check succeeded."))
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                results.append((label, False, f"{type(exc).__name__}: {exc}"))
    return results


async def run_preflight() -> int:
    results = check_storage()
    try:
        results.extend(await check_services())
    except Exception as exc:
        results.append(("external service checks", False, f"{type(exc).__name__}: {exc}"))

    failed = False
    print("FOMO production preflight (no Telegram messages are sent)")
    for name, passed, detail in results:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")
        if not passed:
            failed = True
    print("RESULT: " + ("NOT READY" if failed else "PREFLIGHT PASSED"))
    return 1 if failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(run_preflight()))


if __name__ == "__main__":
    main()
