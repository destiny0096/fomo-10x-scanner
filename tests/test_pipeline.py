import tempfile
import unittest
from pathlib import Path

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_and_record

NARRATIVE = [{"source": "Project website", "url": "https://example.org/about",
              "summary": "A community-led project building open tools for creators and digital culture.", "observed_at": "2026-11-09T10:00:00Z"}]
ATTENTION = [{"source": "Reddit public search", "url": "https://reddit.com/r/example/post",
              "summary": "Two independent authors discussed the project with measurable engagement",
              "distinct_authors": 2, "post_count": 2, "engagement": 7,
              "observed_at": "2026-11-09T10:01:00Z"}]

async def passing_collector(**kwargs):
    return {"narrative_evidence": NARRATIVE, "attention_evidence": ATTENTION}

async def narrative_only_collector(**kwargs):
    return {"narrative_evidence": NARRATIVE, "attention_evidence": []}

async def broken_collector(**kwargs):
    raise TimeoutError("source timeout")

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_evidence_categories_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintPipeline", "name": "Example", "symbol": "EX",
                 "market_cap": 12000},
                database=db, evidence_collector=passing_collector)
            self.assertEqual(result["status"], "qualified")
            self.assertEqual(db.count(), 1)
            self.assertEqual(db.list_tokens()[0]["initial_mc"], 12000)

    async def test_missing_attention_is_rejected_and_not_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintNoAttention", "market_cap": 12000},
                database=db, evidence_collector=narrative_only_collector)
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(db.count(), 0)

    async def test_evidence_source_failure_fails_closed(self):
        result = await evaluate_and_record(
            {"address": "MintTimeout", "market_cap": 12000},
            evidence_collector=broken_collector)
        self.assertEqual(result["status"], "evidence_error")

    async def test_starting_market_cap_is_required(self):
        result = await evaluate_and_record(
            {"address": "MintNoMc"}, evidence_collector=passing_collector)
        self.assertEqual(result["status"], "rejected")

    async def test_duplicate_is_not_recorded_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            token = {"address": "MintDuplicate", "market_cap": 12000}
            first = await evaluate_and_record(token, database=db, evidence_collector=passing_collector)
            second = await evaluate_and_record(token, database=db, evidence_collector=passing_collector)
            self.assertEqual(first["status"], "qualified")
            self.assertEqual(second["status"], "duplicate")
            self.assertEqual(db.count(), 1)

if __name__ == "__main__":
    unittest.main()
