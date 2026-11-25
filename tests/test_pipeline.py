"""Tests for evidence-first narrative and attention qualification."""
import tempfile
import unittest
from pathlib import Path

from tracker.database import TrackerDatabase
from tracker.pipeline import evaluate_candidate, evaluate_and_record

NARRATIVE = [{
    "source": "Project website",
    "url": "https://example.org/about",
    "summary": "A community project building open tools for independent digital creators.",
    "observed_at": "2026-11-25T10:00:00Z",
}]
ATTENTION = [{
    "source": "Reddit public search",
    "url": "https://www.reddit.com/r/example/comments/abc/post",
    "summary": "A recent public discussion directly references this token and its project.",
    "observed_at": "2026-11-25T10:01:00Z",
}]


async def passing_collector(_address, _name, _symbol):
    return {"narrative_evidence": NARRATIVE, "attention_evidence": ATTENTION}


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_evidence_checks_must_pass_before_qualification(self):
        result = await evaluate_candidate(
            {"address": "MintBoth", "name": "Example", "symbol": "EX", "market_cap": 12000},
            evidence_collector=passing_collector,
        )
        self.assertEqual(result["status"], "qualified")
        self.assertTrue(result["narrative_pass"])
        self.assertTrue(result["attention_pass"])

    async def test_missing_narrative_rejects_candidate(self):
        async def no_narrative(*_args):
            return {"narrative_evidence": [], "attention_evidence": ATTENTION}
        result = await evaluate_candidate(
            {"address": "MintNoNarrative", "market_cap": 12000},
            evidence_collector=no_narrative,
        )
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["narrative_pass"])

    async def test_missing_attention_rejects_candidate(self):
        async def no_attention(*_args):
            return {"narrative_evidence": NARRATIVE, "attention_evidence": []}
        result = await evaluate_candidate(
            {"address": "MintNoAttention", "market_cap": 12000},
            evidence_collector=no_attention,
        )
        self.assertEqual(result["status"], "rejected")
        self.assertFalse(result["attention_pass"])

    async def test_attention_requires_no_numeric_engagement_threshold(self):
        from tracker.attention import check_attention
        evidence = [{
            "source": "Reddit public search",
            "url": "https://www.reddit.com/r/example/comments/abc/post",
            "summary": "Relevant public discussion was found for this token.",
            "observed_at": "2026-11-25T10:01:00Z",
            "distinct_authors": 0, "post_count": 0, "engagement": 0,
        }]
        passed, _ = check_attention(evidence)
        self.assertTrue(passed)

    async def test_temporary_evidence_source_failure_defers_candidate(self):
        async def unavailable(*_args):
            from tracker.sources import EvidenceSourceUnavailable
            raise EvidenceSourceUnavailable("Reddit temporarily unavailable")
        result = await evaluate_candidate(
            {"address": "MintRetry", "market_cap": 12000},
            evidence_collector=unavailable,
        )
        self.assertEqual(result["status"], "evidence_error")

    async def test_qualified_candidate_is_recorded_with_both_evidence_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            db = TrackerDatabase(Path(directory) / "pipeline.db")
            result = await evaluate_and_record(
                {"address": "MintPipeline", "name": "Example", "symbol": "EX",
                 "market_cap": 12000},
                database=db, evidence_collector=passing_collector,
            )
            self.assertEqual(result["status"], "qualified")
            stored = db.list_tokens()[0]
            self.assertIn("Project website", stored["evidence_json"])
            self.assertIn("Reddit public search", stored["evidence_json"])

    async def test_missing_address_and_market_cap_are_rejected(self):
        self.assertEqual((await evaluate_candidate({"market_cap": 12000}))["status"], "rejected")
        self.assertEqual((await evaluate_candidate({
            "address": "MintNoMc", "market_cap": None, "fdv": 250000
        }))["status"], "rejected")

    async def test_prechecked_evidence_is_reused_without_recollection(self):
        token = {
            "address": "MintCached", "market_cap": 12000,
            "narrative_evidence": NARRATIVE, "attention_evidence": ATTENTION,
        }
        async def should_not_run(*_args):
            raise AssertionError("prechecked evidence should be reused")
        result = await evaluate_candidate(token, evidence_collector=should_not_run)
        self.assertEqual(result["status"], "qualified")


if __name__ == "__main__":
    unittest.main()
