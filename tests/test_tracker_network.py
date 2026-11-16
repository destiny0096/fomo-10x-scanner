"""Regression tests for transient evidence-source failures and queue diagnostics."""
import asyncio
import tempfile
import unittest
from pathlib import Path

import aiohttp

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_and_record
from tracker.sources import EvidenceSourceUnavailable, _get_json


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

    async def test_permanent_not_found_is_a_no_result_not_a_network_retry(self):
        result = await _get_json(_Session(status=404), "https://api.example.test/data")
        self.assertIsNone(result)

    async def test_pipeline_returns_retryable_evidence_error_on_source_outage(self):
        async def unavailable_collector(**_kwargs):
            raise EvidenceSourceUnavailable("temporary DNS failure")

        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            result = await evaluate_and_record(
                {"address": "RetryMint", "market_cap": 12000},
                database=db,
                evidence_collector=unavailable_collector,
            )
            self.assertEqual(result["status"], "evidence_error")
            self.assertIn("Evidence collection failed", result["reason"])
            self.assertEqual(db.count(), 0)

    async def test_empty_successful_evidence_remains_a_real_qualification_rejection(self):
        async def no_public_evidence(**_kwargs):
            return {"narrative_evidence": [], "attention_evidence": []}

        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            result = await evaluate_and_record(
                {"address": "NoEvidenceMint", "market_cap": 12000},
                database=db,
                evidence_collector=no_public_evidence,
            )
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(db.count(), 0)

    async def test_queue_diagnostics_distinguish_pending_from_completed_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "tracker.db")
            db.enqueue_candidate({"address": "PendingMint", "market_cap": 10000})
            db.enqueue_candidate({"address": "RejectedMint", "market_cap": 10000})
            claimed = db.claim_next_candidate()
            self.assertEqual(claimed["address"], "PendingMint")
            db.complete_candidate("PendingMint", "rejected", "No qualifying public evidence")
            report = db.queue_diagnostics()
            self.assertEqual(report["tracked_tokens"], 0)
            self.assertEqual(report["queue_counts"]["pending"], 1)
            self.assertEqual(report["queue_counts"]["completed"], 1)
            completed = next(row for row in report["recent_candidates"]
                             if row["address"] == "PendingMint")
            self.assertEqual(completed["result_status"], "rejected")
            self.assertEqual(completed["result_reason"], "No qualifying public evidence")
            self.assertTrue(report["database_path"].endswith("tracker.db"))


if __name__ == "__main__":
    unittest.main()
