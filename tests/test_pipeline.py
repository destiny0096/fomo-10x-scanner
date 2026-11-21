"""Tests for the evidence-free Tracker Test 4 qualification contract."""
import tempfile
import unittest
from pathlib import Path

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_and_record


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_address_and_market_cap_are_recorded_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintPipeline", "name": "Example", "symbol": "EX",
                 "market_cap": 12000},
                database=db,
            )
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(db.count(), 1)
            self.assertEqual(db.list_tokens()[0]["initial_mc"], 12000)

    async def test_evidence_collector_is_never_called(self):
        async def broken_collector(**_kwargs):
            raise AssertionError("evidence collector must be bypassed for Test 4")

        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintNoEvidence", "market_cap": 12000},
                database=db, evidence_collector=broken_collector,
            )
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(db.count(), 1)

    async def test_missing_address_is_rejected(self):
        result = await evaluate_and_record({"market_cap": 12000})
        self.assertEqual(result["status"], "rejected")

    async def test_missing_market_cap_is_rejected_without_using_fdv(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintFdvOnly", "market_cap": None, "fdv": 250000},
                database=db,
            )
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(db.count(), 0)

    async def test_non_finite_and_non_positive_market_caps_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), 0, -1):
            with self.subTest(value=value):
                result = await evaluate_and_record(
                    {"address": "MintInvalidMc", "market_cap": value}
                )
                self.assertEqual(result["status"], "rejected")

    async def test_duplicate_is_not_recorded_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            token = {"address": "MintDuplicate", "market_cap": 12000}
            first = await evaluate_and_record(token, database=db)
            second = await evaluate_and_record(token, database=db)
            self.assertEqual(first["status"], "qualified")
            self.assertEqual(second["status"], "duplicate")
            self.assertEqual(db.count(), 1)


if __name__ == "__main__":
    unittest.main()
