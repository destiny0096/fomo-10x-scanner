"""Tests for address-and-reported-market-cap tracker qualification."""
import tempfile
import unittest
from pathlib import Path

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_candidate, evaluate_and_record


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_qualifies_without_narrative_or_social_evidence(self):
        result = await evaluate_candidate({
            "address": "MintNoSocial", "name": "Example", "symbol": "EX",
            "market_cap": 12000,
        })
        self.assertEqual(result["status"], "qualified")
        self.assertTrue(result["narrative_pass"])
        self.assertTrue(result["attention_pass"])
        self.assertEqual(result["candidate"]["narrative_evidence"], [])
        self.assertEqual(result["candidate"]["attention_evidence"], [])

    async def test_reddit_or_website_outage_cannot_block_tracker(self):
        async def unavailable(*_args):
            raise AssertionError("External evidence must not be requested")
        result = await evaluate_candidate(
            {"address": "MintOffline", "market_cap": 12000},
            evidence_collector=unavailable,
        )
        self.assertEqual(result["status"], "qualified")

    async def test_missing_address_and_market_cap_are_rejected(self):
        self.assertEqual((await evaluate_candidate({"market_cap": 12000}))["status"], "rejected")
        self.assertEqual((await evaluate_candidate({
            "address": "MintNoMc", "market_cap": None, "fdv": 250000
        }))["status"], "rejected")
        self.assertEqual((await evaluate_candidate({
            "address": "MintZeroMc", "market_cap": 0
        }))["status"], "rejected")

    async def test_qualified_scanner_alert_is_recorded_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintPipeline", "name": "Example", "symbol": "EX",
                 "market_cap": 12000},
                database=db,
            )
            self.assertEqual(result["status"], "qualified")
            stored = db.list_tokens()[0]
            self.assertEqual(stored["address"], "MintPipeline")
            self.assertEqual(stored["initial_mc"], 12000)
            self.assertEqual(stored["evidence_json"], '{"attention": [], "narrative": []}')

    async def test_duplicate_and_100_token_cap_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            token = {"address": "Mint0", "market_cap": 12000}
            self.assertEqual((await evaluate_and_record(token, database=db))["status"], "qualified")
            self.assertEqual((await evaluate_and_record(token, database=db))["status"], "duplicate")
            for index in range(1, 100):
                result = await evaluate_and_record(
                    {"address": f"Mint{index}", "market_cap": 12000}, database=db
                )
                self.assertEqual(result["status"], "qualified")
            extra = await evaluate_and_record(
                {"address": "Mint100", "market_cap": 12000}, database=db
            )
            self.assertEqual(extra["status"], "tracker_full")
            self.assertEqual(db.count(), 100)


if __name__ == "__main__":
    unittest.main()
