"""Create a timestamped, integrity-checked SQLite backup."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .database import TrackerDatabase, configured_database_path


def create_backup() -> Path:
    database_path = configured_database_path()
    configured_backup_dir = os.getenv("TRACKER_BACKUP_DIR", "").strip()
    backup_dir = (Path(configured_backup_dir).expanduser() if configured_backup_dir
                  else database_path.parent / "tracker_backups")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"tracker-{stamp}.db"
    database = TrackerDatabase(database_path)
    if not database.integrity_check():
        raise RuntimeError("Live tracker database failed SQLite integrity_check; backup stopped")
    return database.backup_to(destination)


if __name__ == "__main__":
    print(f"Tracker backup created: {create_backup()}")
