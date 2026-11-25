"""SQLite persistence for qualified tokens and market-cap observations."""
import csv
import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
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
    def __init__(self, path: str | Path | None = None, *, timeout_seconds: float = 30.0):
        self.path = Path(path).expanduser() if path is not None else configured_database_path()
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=self.timeout_seconds)
        db.row_factory = sqlite3.Row
        db.execute(f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}")
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
                qualified_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
                test_number INTEGER NOT NULL DEFAULT 4)""")
            db.execute("""CREATE TABLE IF NOT EXISTS tracker_state (
                id INTEGER PRIMARY KEY CHECK(id=1), test_number INTEGER NOT NULL DEFAULT 4)
            """)
            db.execute("INSERT OR IGNORE INTO tracker_state(id,test_number) VALUES (1,4)")
            state_columns = {row["name"] for row in db.execute("PRAGMA table_info(tracker_state)").fetchall()}
            if "test5_reset_done" not in state_columns:
                db.execute("ALTER TABLE tracker_state ADD COLUMN test5_reset_done INTEGER NOT NULL DEFAULT 0")
            db.execute("""CREATE TABLE IF NOT EXISTS completed_cohorts (
                test_number INTEGER PRIMARY KEY, completed_at TEXT NOT NULL,
                tokens_json TEXT NOT NULL)
            """)
            db.execute("""CREATE TABLE IF NOT EXISTS notification_outbox (
                milestone INTEGER PRIMARY KEY, payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                claimed_at TEXT, sent_at TEXT)
            """)
            db.execute("""CREATE TABLE IF NOT EXISTS mc_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, address TEXT NOT NULL,
                market_cap REAL NOT NULL, observed_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS completion_export_queue (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                claimed_at TEXT, sent_at TEXT)
            """)
            db.execute("""CREATE TABLE IF NOT EXISTS alert_journal (
                address TEXT PRIMARY KEY, token_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
                sent_at TEXT, last_error TEXT)
            """)
            db.execute("""CREATE TABLE IF NOT EXISTS candidate_queue (
                address TEXT PRIMARY KEY, token_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, claimed_at TEXT, last_error TEXT,
                completed_at TEXT, result_status TEXT, result_reason TEXT)""")
            token_columns = {row["name"] for row in db.execute("PRAGMA table_info(tracked_tokens)").fetchall()}
            if "test_number" not in token_columns:
                db.execute("ALTER TABLE tracked_tokens ADD COLUMN test_number INTEGER NOT NULL DEFAULT 4")
            # Upgrade databases created before durable per-candidate outcomes were added.
            queue_columns = {row["name"] for row in db.execute("PRAGMA table_info(candidate_queue)").fetchall()}
            if "result_status" not in queue_columns:
                db.execute("ALTER TABLE candidate_queue ADD COLUMN result_status TEXT")
            if "result_reason" not in queue_columns:
                db.execute("ALTER TABLE candidate_queue ADD COLUMN result_reason TEXT")

            # Recover an already-full cohort left active by the previous runtime.
            # Archive all 100 rows before advancing; retain tracked rows as a safety copy.
            state = db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()
            cycle = int(state[0]) if state else 4
            rows = db.execute("SELECT * FROM tracked_tokens WHERE test_number=? ORDER BY id", (cycle,)).fetchall()
            export_state = db.execute("SELECT status FROM completion_export_queue WHERE id=1").fetchone()
            # Preserve pending exports; recover legacy full cohorts with no queue row.
            if len(rows) == MAX_TRADES and (export_state is None or export_state["status"] == "sent"):
                now = datetime.now(timezone.utc).isoformat()
                payload = json.dumps([dict(row) for row in rows], sort_keys=True)
                db.execute("INSERT OR IGNORE INTO completed_cohorts (test_number,completed_at,tokens_json) VALUES (?,?,?)", (cycle, now, payload))
                archived = db.execute("SELECT tokens_json FROM completed_cohorts WHERE test_number=?", (cycle,)).fetchone()
                archived_rows = json.loads(archived["tokens_json"]) if archived else []
                if len(archived_rows) != MAX_TRADES:
                    raise sqlite3.DatabaseError(f"Refusing to advance: Test {cycle} archive is incomplete")
                db.execute("UPDATE tracker_state SET test_number=? WHERE id=1", (cycle + 1,))
                db.execute("INSERT OR IGNORE INTO completion_export_queue (id,status,attempts) VALUES (1,'sent',0)")
                db.execute("UPDATE completion_export_queue SET status='sent', claimed_at=NULL WHERE id=1")
                db.execute("DELETE FROM notification_outbox")

    def reset_test4_to_test5(self) -> bool:
        """Back up the live DB, then remove Test 4 data and activate a clean Test 5 once."""
        with self._connect() as db:
            state = db.execute("SELECT test_number, test5_reset_done FROM tracker_state WHERE id=1").fetchone()
            if state is None or int(state["test5_reset_done"] or 0) == 1:
                return False
            cycle = int(state["test_number"])
            if cycle not in {4, 5}:
                return False
            old_rows = db.execute("SELECT address FROM tracked_tokens WHERE test_number=4").fetchall()
            old_archive = db.execute("SELECT 1 FROM completed_cohorts WHERE test_number=4").fetchone()
            if cycle == 5 and not old_rows and not old_archive:
                return False

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = self.path.parent / "tracker_backups" / ("tracker-before-test5-reset-" + stamp + ".db")
        self.backup_to(backup_path)

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute("SELECT test_number, test5_reset_done FROM tracker_state WHERE id=1").fetchone()
            if state is None or int(state["test5_reset_done"] or 0) == 1 or int(state["test_number"]) not in {4, 5}:
                return False
            addresses = [str(row[0]) for row in db.execute("SELECT address FROM tracked_tokens WHERE test_number=4").fetchall()]
            db.execute("DELETE FROM tracked_tokens WHERE test_number=4")
            if addresses:
                marks = ",".join("?" for _ in addresses)
                db.execute("DELETE FROM mc_snapshots WHERE address IN (" + marks + ")", addresses)
            db.execute("DELETE FROM notification_outbox")
            db.execute("DELETE FROM candidate_queue")
            db.execute("DELETE FROM completed_cohorts WHERE test_number=4")
            db.execute("INSERT INTO completion_export_queue (id,status,attempts,claimed_at,sent_at) VALUES (1,'sent',0,NULL,NULL) ON CONFLICT(id) DO UPDATE SET status='sent',claimed_at=NULL")
            db.execute("UPDATE tracker_state SET test_number=5, test5_reset_done=1 WHERE id=1")
        return True

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
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
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

    def current_test_number(self) -> int:
        with self._connect() as db:
            row = db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()
            return int(row[0]) if row else 4

    def count(self) -> int:
        with self._connect() as db:
            cycle = int(db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()[0])
            return int(db.execute("SELECT COUNT(*) FROM tracked_tokens WHERE test_number=?", (cycle,)).fetchone()[0])

    def add_qualified(self, token: dict[str, Any], qualified_at: str) -> str:
        address = str(token.get("address", "")).strip()
        try:
            mc = float(token.get("market_cap") or 0)
        except (TypeError, ValueError, OverflowError):
            return "invalid"
        if not address or not math.isfinite(mc) or mc <= 0:
            return "invalid"
        evidence = json.dumps(
            {"narrative": token.get("narrative_evidence", []),
             "attention": token.get("attention_evidence", [])},
            sort_keys=True,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cycle = int(db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()[0])
            if db.execute("SELECT 1 FROM tracked_tokens WHERE address=?", (address,)).fetchone():
                return "duplicate"
            cycle_count = int(db.execute("SELECT COUNT(*) FROM tracked_tokens WHERE test_number=?", (cycle,)).fetchone()[0])
            if cycle_count >= MAX_TRADES:
                return "full"
            db.execute(
                """INSERT INTO tracked_tokens
                (address,symbol,name,initial_mc,peak_mc,current_mc,qualified_at,evidence_json,test_number)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (address, str(token.get("symbol", "")), str(token.get("name", "")),
                 mc, mc, mc, qualified_at, evidence, cycle),
            )
            db.execute(
                "INSERT INTO mc_snapshots(address,market_cap,observed_at) VALUES (?,?,?)",
                (address, mc, qualified_at),
            )
            # Queue milestone messages in the SAME transaction as the token insert.
            # This prevents concurrent qualifying tasks from skipping a boundary.
            count = cycle_count + 1
            if count == 100:
                db.execute("""INSERT OR IGNORE INTO completion_export_queue(id,status) VALUES (1,'pending')""")
                db.execute("""UPDATE completion_export_queue SET status='pending',attempts=0,
                    claimed_at=NULL,sent_at=NULL WHERE id=1""")
            if count in {1, 25, 50, 75, 100}:
                rows = db.execute("SELECT * FROM tracked_tokens WHERE test_number=? ORDER BY id", (cycle,)).fetchall()
                payload = json.dumps([dict(row) for row in rows], sort_keys=True)
                db.execute(
                    "INSERT OR IGNORE INTO notification_outbox(milestone,payload_json) VALUES (?,?)",
                    (count, payload),
                )
        return "added"

    def claim_next_notification(self) -> dict[str, Any] | None:
        """Claim one pending event; abandoned claims become retryable after five minutes."""
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(minutes=5)).isoformat()
        claimed = now.isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT milestone,payload_json FROM notification_outbox
                WHERE status='pending' OR (status='sending' AND claimed_at < ?)
                ORDER BY milestone LIMIT 1""",
                (stale,),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                """UPDATE notification_outbox SET status='sending', claimed_at=?, attempts=attempts+1
                WHERE milestone=?""",
                (claimed, row["milestone"]),
            )
            return {"milestone": int(row["milestone"]), "tokens": json.loads(row["payload_json"])}

    def finish_notification(self, milestone: int, *, sent: bool) -> None:
        """Mark delivery complete or release the event for a later retry."""
        with self._connect() as db:
            if sent:
                db.execute(
                    "UPDATE notification_outbox SET status='sent', sent_at=?, claimed_at=NULL WHERE milestone=?",
                    (datetime.now(timezone.utc).isoformat(), milestone),
                )
            else:
                db.execute(
                    "UPDATE notification_outbox SET status='pending', claimed_at=NULL WHERE milestone=?",
                    (milestone,),
                )

    def pending_notification_count(self) -> int:
        with self._connect() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM notification_outbox WHERE status!='sent'"
            ).fetchone()[0])

    def claim_completion_export(self, *, lease_minutes: int = 5) -> bool:
        """Claim the one-time cohort CSV delivery; stale claims are recoverable."""
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(minutes=max(1, lease_minutes))).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status, claimed_at FROM completion_export_queue WHERE id=1"
            ).fetchone()
            if row is None or row["status"] == "sent":
                return False
            if row["status"] == "sending" and row["claimed_at"] and row["claimed_at"] >= stale:
                return False
            db.execute(
                """UPDATE completion_export_queue SET status='sending',
                claimed_at=?, attempts=attempts+1 WHERE id=1""",
                (now.isoformat(),),
            )
            return True

    def finish_completion_export(self, *, sent: bool) -> None:
        """Archive a delivered 100-token cohort, then advance the next test number."""
        with self._connect() as db:
            if sent:
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    """UPDATE completion_export_queue SET status='sent', sent_at=?,
                    claimed_at=NULL WHERE id=1""", (now,),
                )
                cycle = int(db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()[0])
                rows = db.execute("SELECT * FROM tracked_tokens WHERE test_number=? ORDER BY id", (cycle,)).fetchall()
                if len(rows) == MAX_TRADES:
                    payload = json.dumps([dict(row) for row in rows], sort_keys=True)
                    db.execute("""INSERT OR IGNORE INTO completed_cohorts
                        (test_number,completed_at,tokens_json) VALUES (?,?,?)""", (cycle, now, payload))
                    db.execute("DELETE FROM tracked_tokens WHERE test_number=?", (cycle,))
                    db.execute("DELETE FROM mc_snapshots WHERE address NOT IN (SELECT address FROM tracked_tokens)")
                    db.execute("DELETE FROM notification_outbox")
                    db.execute("UPDATE tracker_state SET test_number=? WHERE id=1", (cycle + 1,))
            else:
                db.execute("UPDATE completion_export_queue SET status='pending', claimed_at=NULL WHERE id=1")


    def recover_completed_cohort_from_export(self, export_path: str | Path) -> bool:
        """Advance a full cohort only when its existing CSV proves it was exported.

        This repairs the crash window where Telegram accepted the CSV but the
        process stopped before the SQLite completion transaction committed.
        """
        path = Path(export_path).expanduser()
        if not path.is_file():
            return False
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as handle:
                exported = list(csv.DictReader(handle))
        except (OSError, csv.Error, UnicodeError):
            return False
        if len(exported) != MAX_TRADES:
            return False
        exported_addresses = {str(row.get("address") or "").strip() for row in exported}
        if len(exported_addresses) != MAX_TRADES:
            return False

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()
            cycle = int(state[0]) if state else 4
            rows = db.execute(
                "SELECT * FROM tracked_tokens WHERE test_number=? ORDER BY id", (cycle,)
            ).fetchall()
            if len(rows) != MAX_TRADES:
                return False
            live_addresses = {str(row["address"]) for row in rows}
            if live_addresses != exported_addresses:
                return False
            export_state = db.execute(
                "SELECT status FROM completion_export_queue WHERE id=1"
            ).fetchone()
            if export_state is None or export_state["status"] == "sent":
                return False
            exported_tests = {str(row.get("test_number") or "") for row in exported}
            if exported_tests != {str(cycle)}:
                return False

            now = datetime.now(timezone.utc).isoformat()
            payload = json.dumps([dict(row) for row in rows], sort_keys=True)
            db.execute(
                """INSERT OR IGNORE INTO completed_cohorts
                (test_number,completed_at,tokens_json) VALUES (?,?,?)""",
                (cycle, now, payload),
            )
            archived = db.execute(
                "SELECT tokens_json FROM completed_cohorts WHERE test_number=?", (cycle,)
            ).fetchone()
            archived_rows = json.loads(archived["tokens_json"]) if archived else []
            if len(archived_rows) != MAX_TRADES or {
                str(row.get("address") or "") for row in archived_rows
            } != live_addresses:
                raise sqlite3.DatabaseError(
                    f"Refusing to recover Test {cycle}: archive verification failed"
                )
            db.execute(
                """UPDATE completion_export_queue SET status='sent', sent_at=?,
                claimed_at=NULL WHERE id=1""", (now,)
            )
            db.execute("DELETE FROM tracked_tokens WHERE test_number=?", (cycle,))
            db.execute(
                "DELETE FROM mc_snapshots WHERE address NOT IN (SELECT address FROM tracked_tokens)"
            )
            db.execute("DELETE FROM notification_outbox")
            db.execute("UPDATE tracker_state SET test_number=? WHERE id=1", (cycle + 1,))
            return True

    def list_completed_cohorts(self) -> list[dict[str, Any]]:
        """Return immutable historical cohort journals, oldest first."""
        with self._connect() as db:
            rows = db.execute("SELECT test_number,completed_at,tokens_json FROM completed_cohorts ORDER BY test_number").fetchall()
        return [dict(row) for row in rows]

    def pending_completion_export_count(self) -> int:
        with self._connect() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM completion_export_queue WHERE status!='sent'"
            ).fetchone()[0])

    def prepare_alert(self, token: dict[str, Any]) -> str:
        """Durably journal an alert before Telegram delivery; return its prior state."""
        address = str(token.get("address") or "").strip()
        if not address:
            return "invalid"
        payload = json.dumps(token, sort_keys=True, allow_nan=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM alert_journal WHERE address=?", (address,)).fetchone()
            if row and row["status"] == "sent":
                return "sent"
            db.execute("""INSERT INTO alert_journal(address,token_json,status,created_at)
                VALUES(?,?,'pending',?) ON CONFLICT(address) DO UPDATE SET
                token_json=excluded.token_json,status='pending',last_error=NULL""",
                (address, payload, now))
            return "pending"

    def finish_alert(self, address: str, *, sent: bool, error: str = "") -> None:
        """Finalize the durable send journal after Telegram responds."""
        with self._connect() as db:
            if sent:
                db.execute("""UPDATE alert_journal SET status='sent',sent_at=?,last_error=NULL
                    WHERE address=?""", (datetime.now(timezone.utc).isoformat(), address))
            else:
                db.execute("UPDATE alert_journal SET status='failed',last_error=? WHERE address=?",
                           (str(error)[:300], address))

    def list_sent_alerts(self) -> list[dict[str, Any]]:
        """Return the permanent journal of successfully delivered token alerts."""
        with self._connect() as db:
            rows = db.execute("SELECT * FROM alert_journal WHERE status='sent' ORDER BY sent_at").fetchall()
        return [dict(row) for row in rows]

    def enqueue_candidate(self, token: dict[str, Any]) -> str:
        """Durably queue a scanner alert for evidence evaluation."""
        address = str(token.get("address") or "").strip()
        if not address:
            return "invalid"
        payload = {
            "address": address, "name": str(token.get("name") or ""),
            "symbol": str(token.get("symbol") or ""), "market_cap": token.get("market_cap"),
            "narrative_evidence": token.get("narrative_evidence") or [],
            "attention_evidence": token.get("attention_evidence") or [],
        }
        serialized = json.dumps(payload, sort_keys=True, allow_nan=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("""INSERT OR IGNORE INTO candidate_queue
                (address, token_json, status, created_at) VALUES (?, ?, 'pending', ?)""",
                (address, serialized, now))
            return "queued" if cursor.rowcount == 1 else "duplicate"

    def claim_next_candidate(self, *, lease_minutes: int = 10) -> dict[str, Any] | None:
        """Atomically claim pending work; crashed claims expire after a lease."""
        now = datetime.now(timezone.utc)
        stale = (now - timedelta(minutes=max(1, lease_minutes))).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT address, token_json FROM candidate_queue
                WHERE status='pending' OR (status='processing' AND claimed_at < ?)
                ORDER BY created_at LIMIT 1""", (stale,)).fetchone()
            if row is None:
                return None
            db.execute("""UPDATE candidate_queue SET status='processing', claimed_at=?,
                attempts=attempts+1, last_error=NULL WHERE address=?""",
                (now.isoformat(), row["address"]))
            return json.loads(row["token_json"])

    def complete_candidate(self, address: str, result_status: str = "", result_reason: str = "") -> None:
        """Mark work complete while retaining its qualification outcome for diagnostics."""
        with self._connect() as db:
            db.execute("""UPDATE candidate_queue SET status='completed', completed_at=?,
                claimed_at=NULL, last_error=NULL, result_status=?, result_reason=? WHERE address=?""",
                (datetime.now(timezone.utc).isoformat(), str(result_status)[:40],
                 str(result_reason)[:500], address))

    def retry_candidate(self, address: str, error: str = "") -> None:
        with self._connect() as db:
            db.execute("""UPDATE candidate_queue SET status='pending', claimed_at=NULL,
                last_error=?, created_at=? WHERE address=?""",
                (str(error)[:300], datetime.now(timezone.utc).isoformat(), address))

    def pending_candidate_count(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM candidate_queue WHERE status!='completed'").fetchone()[0])
    def queue_diagnostics(self, *, recent_limit: int = 10) -> dict[str, Any]:
        """Return safe operational counts and recent outcomes from this exact DB."""
        limit = max(1, min(int(recent_limit), 50))
        with self._connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS total FROM candidate_queue GROUP BY status"
            ).fetchall()
            recent = db.execute(
                """SELECT address, status, attempts, result_status, result_reason,
                last_error, created_at, completed_at FROM candidate_queue
                ORDER BY COALESCE(completed_at, created_at) DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            tracked = int(db.execute("SELECT COUNT(*) FROM tracked_tokens").fetchone()[0])
            outcomes = db.execute(
                """SELECT COALESCE(result_status, 'not_evaluated') AS outcome,
                COUNT(*) AS total FROM candidate_queue
                WHERE status='completed' GROUP BY COALESCE(result_status, 'not_evaluated')"""
            ).fetchall()
        counts = {"pending": 0, "processing": 0, "completed": 0}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        outcome_counts = {
            str(row["outcome"]): int(row["total"]) for row in outcomes
        }
        return {
            "database_path": str(self.path.resolve()),
            "tracked_tokens": tracked,
            "queue_counts": counts,
            "outcome_counts": outcome_counts,
            "recent_candidates": [dict(row) for row in recent],
        }

    def record_market_cap(self, address: str, market_cap: float, observed_at: str) -> bool:
        try:
            value = float(market_cap)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(value) or value <= 0:
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
            cycle = int(db.execute("SELECT test_number FROM tracker_state WHERE id=1").fetchone()[0])
            rows = db.execute("SELECT * FROM tracked_tokens WHERE test_number=? ORDER BY id", (cycle,)).fetchall()
        return [dict(row) for row in rows]
