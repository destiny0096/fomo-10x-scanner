"""Create timestamped, integrity-checked SQLite backups with bounded retention."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .database import TrackerDatabase, configured_database_path

log = logging.getLogger(__name__)


def create_backup() -> Path:
    database_path = configured_database_path()
    if not database_path.is_file():
        raise FileNotFoundError(f"Tracker database does not exist: {database_path}")
    configured_backup_dir = os.getenv("TRACKER_BACKUP_DIR", "").strip()
    backup_dir = (
        Path(configured_backup_dir).expanduser()
        if configured_backup_dir
        else database_path.parent / "tracker_backups"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"tracker-{stamp}.db"
    database = TrackerDatabase(database_path)
    if not database.integrity_check():
        raise RuntimeError("Live tracker database failed SQLite integrity_check; backup stopped")
    backup = database.backup_to(destination)

    # Keep recent recovery points without allowing the backup folder to grow forever.
    try:
        keep_last = max(1, int(os.getenv("TRACKER_BACKUP_KEEP", "28")))
    except (TypeError, ValueError):
        keep_last = 28
    backups = sorted(backup_dir.glob("tracker-*.db"), key=lambda item: item.name)
    for old_backup in backups[:-keep_last]:
        try:
            old_backup.unlink()
        except OSError:
            log.warning("Could not prune old tracker backup: %s", old_backup, exc_info=True)
    return backup


if __name__ == "__main__":
    print(f"Tracker backup created: {create_backup()}")
