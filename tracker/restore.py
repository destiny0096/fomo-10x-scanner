"""Safely restore a tracker SQLite database from a validated backup.

Stop the scanner process before running this command. The utility refuses to
replace a database when SQLite WAL/SHM sidecar files are present.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .database import TrackerDatabase, configured_database_path

REQUIRED_TABLES = {"tracked_tokens", "mc_snapshots"}


def _validate_database(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Database file does not exist: {path}")
    with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError(f"SQLite integrity check failed: {path}")
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not REQUIRED_TABLES.issubset(tables):
            raise sqlite3.DatabaseError(
                f"Backup is missing tracker tables: {sorted(REQUIRED_TABLES - tables)}"
            )


def restore_backup(
    backup_path: str | Path,
    target_path: str | Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Restore a validated backup; overwrite requires force and creates a safety copy."""
    source = Path(backup_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve() if target_path else configured_database_path().resolve()
    if source == target:
        raise ValueError("Backup source and live database destination must differ")
    _validate_database(source)

    if target.exists() and not force:
        raise FileExistsError(
            f"Live database already exists: {target}. Use --force to replace it."
        )
    if target.exists():
        sidecars = [Path(str(target) + suffix) for suffix in ("-wal", "-shm")]
        present = [str(path) for path in sidecars if path.exists()]
        if present:
            raise RuntimeError(
                "Refusing restore because SQLite sidecar files exist: "
                + ", ".join(present)
                + ". Stop the bot and resolve the active/stale SQLite sidecars first."
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=target.name + ".restore-", suffix=".tmp", dir=str(target.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(str(temporary))) as destination_db:
                source_db.backup(destination_db)
        _validate_database(temporary)

        safety_copy = None
        if target.exists():
            # Preserve the current valid database before replacing it.
            _validate_database(target)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            safety_copy = target.with_name(f"{target.name}.pre-restore-{stamp}.db")
            TrackerDatabase(target).backup_to(safety_copy)

        os.replace(temporary, target)
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore the FOMO tracker database from a validated SQLite backup."
    )
    parser.add_argument("backup", help="Path to a tracker backup .db file")
    parser.add_argument(
        "--target", help="Live database destination (defaults to TRACKER_DB_PATH/runtime path)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Replace an existing database after creating a validated pre-restore safety backup"
    )
    args = parser.parse_args()
    restored = restore_backup(args.backup, args.target, force=args.force)
    print(f"Tracker database restored successfully: {restored}")


if __name__ == "__main__":
    main()
