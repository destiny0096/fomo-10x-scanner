"""Regression tests for unused public-source adapters and queue diagnostics."""
import asyncio
import tempfile
import unittest
from pathlib import Path

import aiohttp

from tracker.database import TrackerDatabase
from tracker.sources import EvidenceSourceUnavailable, _get_json, _get_text


class _Response:
    def __init__(self, status, payload=None):
        self.status = status
        self.payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self, content_type=None):
        return self.payload


class _Session:
    def __init__(self, *, status=200, payload=None, error=None):
        self.response = _Response(status, payload)
        self.error = error

    def get(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.response


class EvidenceSourceRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dns_or_connection_error_is_transient_not_empty_evidence(self):
        session = _Session(error=aiohttp.ClientError("temporary DNS resolution failure"))
        with self.assertRaises(EvidenceSourceUnavailable):
            await _get_json(session, "https://api.example.test/data")

    async def test_timeout_is_transient_not_empty_evidence(self):
        session = _Session(error=asyncio.TimeoutError())
        with self.assertRaises(EvidenceSourceUnavailable):
            await _get_json(session, "https://api.example.test/data")

    async def test_server_error_and_rate_limit_are_transient(self):
        for status in (429, 500, 502, 503):
            with self.subTest(status=status):
                with self.assertRaises(EvidenceSourceUnavailable):
                    await _get_json(_Session(status=status), "https://api.example.test/data")

    async def test_project_website_server_error_is_transient(self):
        with self.assertRaises(EvidenceSourceUnavailable):
            await _get_text(_Session(status=503), "https://example.com/about")

    async def test_permanent_not_found_is_a_no_result_not_a_network_retry(self):
        result = await _get_json(_Session(status=404), "https://api.example.test/data")
        self.assertIsNone(result)

    async def test_existing_database_queue_schema_is_upgraded_in_place(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing-tracker.db"
            with sqlite3.connect(path) as connection:
                connection.execute("""CREATE TABLE candidate_queue (
                    address TEXT PRIMARY KEY, token_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, claimed_at TEXT, last_error TEXT,
                    completed_at TEXT)""")
            db = TrackerDatabase(path)
            with db._connect() as connection:
                columns = {row["name"] for row in connection.execute(
                    "PRAGMA table_info(candidate_queue)"
                ).fetchall()}
            self.assertIn("result_status", columns)
            self.assertIn("result_reason", columns)
            db.enqueue_candidate({"address": "MigratedMint", "market_cap": 100})
            self.assertEqual(db.claim_next_candidate()["address"], "MigratedMint")
            db.complete_candidate("MigratedMint", "rejected", "migration test")
            self.assertEqual(db.queue_diagnostics()["recent_candidates"][0]["result_reason"], "migration test")

    async def test_queue_diagnostics_distinguish_pending_from_completed_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            db.enqueue_candidate({"address": "PendingMint", "market_cap": 10000})
            db.enqueue_candidate({"address": "RejectedMint", "market_cap": 10000})
            claimed = db.claim_next_candidate()
            self.assertEqual(claimed["address"], "PendingMint")
            db.complete_candidate("PendingMint", "rejected", "Missing valid reported market cap")
            report = db.queue_diagnostics()
            self.assertEqual(report["tracked_tokens"], 0)
            self.assertEqual(report["queue_counts"]["pending"], 1)
            self.assertEqual(report["queue_counts"]["completed"], 1)
            completed = next(row for row in report["recent_candidates"]
                             if row["address"] == "PendingMint")
            self.assertEqual(completed["result_status"], "rejected")
            self.assertEqual(completed["result_reason"], "Missing valid reported market cap")
            self.assertTrue(report["database_path"].endswith("tracker.db"))


if __name__ == "__main__":
    unittest.main()
