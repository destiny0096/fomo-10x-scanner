"""SQLite persistence for qualified tokens and market-cap observations."""
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "tracker_data.db"
MAX_TRADES = 100


def configured_database_path() -> Path:
    """Resolve the runtime DB path, allowing hosts to point at a persistent disk."""
    configured = os.getenv("TRACKER_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    persistent_mount = Path("/data")
    if persistent_mount.is_dir() and os.access(persistent_mount, os.W_OK):
        return persistent_mount / "tracker_data.db"
    return DEFAULT_DB


class TrackerDatabase:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path is not None else configured_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize(self):
        with self._connect() as db:
            # WAL improves safety when the scanner writes while the monitor reads.
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS tracked_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
                initial_mc REAL NOT NULL, peak_mc REAL NOT NULL, current_mc REAL NOT NULL,
                qualified_at TEXT NOT NULL, evidence_json TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS mc_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL,
                market_cap REAL NOT NULL, observed_at TEXT NOT NULL)""")

    def integrity_check(self) -> bool:
        """Return True only when SQLite reports a clean database."""
        with self._connect() as db:
            rows = db.execute("PRAGMA integrity_check").fetchall()
        return len(rows) == 1 and rows[0][0] == "ok"

    def backup_to(self, destination: str | Path) -> Path:
        """Create a consistent SQLite backup, validating it before publishing."""
        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == self.path.resolve():
            raise ValueError("Backup destination must differ from the live database")
        temporary = target.with_name(target.name + ".tmp")
        try:
            with self._connect() as source:
                with closing(sqlite3.connect(str(temporary), timeout=30)) as backup:
                    source.backup(backup)
            with closing(sqlite3.connect(str(temporary))) as check:
                result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("Backup integrity check failed")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM tracked_tokens").fetchone()[0])

    def add_qualified(self, token: dict[str, Any], qualified_at: str) -> str:
        address = str(token.get("address", "")).strip()
        try:
            mc = float(token.get("market_cap") or 0)
        except (TypeError, ValueError):
            return "invalid"
        if not address or mc <= 0:
            return "invalid"
        evidence = json.dumps(
            {"narrative": token.get("narrative_evidence", []),
             "attention": token.get("attention_evidence", [])},
            sort_keys=True,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tracked_tokens WHERE address=?", (address,)).fetchone():
                return "duplicate"
            if db.execute("SELECT COUNT(*) FROM tracked_tokens").fetchone()[0] >= MAX_TRADES:
                return "full"
            db.execute(
                """INSERT INTO tracked_tokens
                (address,symbol,name,initial_mc,peak_mc,current_mc,qualified_at,evidence_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                (address, str(token.get("symbol", "")), str(token.get("name", "")),
                 mc, mc, mc, qualified_at, evidence),
            )
            db.execute(
                "INSERT INTO mc_snapshots(address,market_cap,observed_at) VALUES (?,?,?)",
                (address, mc, qualified_at),
            )
        return "added"

    def record_market_cap(self, address: str, market_cap: float, observed_at: str) -> bool:
        try:
            value = float(market_cap)
        except (TypeError, ValueError):
            return False
        if value <= 0:
            return False
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE tracked_tokens SET current_mc=?, peak_mc=MAX(peak_mc,?) WHERE address=?",
                (value, value, address),
            )
            if cursor.rowcount != 1:
                return False
            db.execute(
                "INSERT INTO mc_snapshots(address,market_cap,observed_at) VALUES (?,?,?)",
                (address, value, observed_at),
            )
        return True

    def list_tokens(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM tracked_tokens ORDER BY id").fetchall()
        return [dict(row) for row in rows]
