import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tracker.database import TrackerDatabase, configured_database_path
from tracker.backup import create_backup
from tracker.performance import milestone_hits, multiple
from tracker.report import build_report
from tracker.export import export_results
from tracker.tracker import qualify_token

NARRATIVE = [{"source":"Project website","url":"https://example.org/about","summary":"A community-led project building open tools for creators and digital culture.","observed_at":"2026-11-09T10:00:00Z"}]
ATTENTION = [{"source":"Reddit public search","url":"https://www.reddit.com/r/example/comments/abc/post","summary":"Two independent authors discussed the project with measurable engagement.","distinct_authors":2,"post_count":2,"engagement":7,"observed_at":"2026-11-09T10:01:00Z"}]


class QualificationTests(unittest.TestCase):
    def test_both_checks_required(self):
        r = qualify_token({"address":"Mint111","narrative_evidence":NARRATIVE,"attention_evidence":[]})
        self.assertFalse(r.qualified)
        self.assertTrue(r.narrative_pass)
        self.assertFalse(r.attention_pass)

    def test_both_evidence_categories_pass(self):
        self.assertTrue(qualify_token({"address":"Mint111","narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}).qualified)

    def test_unlinked_evidence_fails(self):
        bad = [{"source":"unknown","url":"","summary":"Trust me","observed_at":"now"}]
        self.assertFalse(qualify_token({"address":"Mint111","narrative_evidence":bad,"attention_evidence":ATTENTION}).qualified)

    def test_narrative_word_and_character_thresholds_apply_to_description(self):
        short_description = [{
            "source": "Project website", "url": "https://example.org",
            "summary": "A serious community project building useful tools for creators",
            "observed_at": "2026-11-09T10:00:00Z",
        }]
        result = qualify_token({
            "address": "MintShortNarrative",
            "narrative_evidence": short_description,
            "attention_evidence": ATTENTION,
        })
        self.assertFalse(result.narrative_pass)

        sufficient_description = [{
            "source": "Project website", "url": "https://example.org",
            "summary": "A community project building open creative tools for independent digital artists",
            "observed_at": "2026-11-09T10:00:00Z",
        }]
        result = qualify_token({
            "address": "MintGoodNarrative",
            "narrative_evidence": sufficient_description,
            "attention_evidence": ATTENTION,
        })
        self.assertTrue(result.narrative_pass)

    def test_short_or_placeholder_narrative_is_rejected(self):
        weak = [{"source": "Project website", "url": "https://example.org",
                 "summary": "Coming soon", "observed_at": "now"}]
        self.assertFalse(qualify_token({
            "address": "MintWeak", "narrative_evidence": weak,
            "attention_evidence": ATTENTION,
        }).qualified)

    def test_attention_requires_measured_public_engagement(self):
        weak = [{"source": "Reddit public search", "url": "https://www.reddit.com/r/example/post",
                 "summary": "A post was found", "observed_at": "now"}]
        result = qualify_token({
            "address": "MintWeakAttention", "narrative_evidence": NARRATIVE,
            "attention_evidence": weak,
        })
        self.assertFalse(result.qualified)
        self.assertTrue(result.narrative_pass)
        self.assertFalse(result.attention_pass)

    def test_address_required(self):
        self.assertFalse(qualify_token({"narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}).qualified)


class PersistenceTests(unittest.TestCase):
    def _token(self):
        return {"address":"Mint111","symbol":"TEST","name":"Test token","market_cap":10000,
                "narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}

    def test_insert_duplicate_snapshot_and_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nested" / "test.db"
            db = TrackerDatabase(path)
            token = self._token()
            self.assertEqual(db.add_qualified(token,"2026-11-09T10:00:00Z"),"added")
            self.assertEqual(db.add_qualified(token,"2026-11-09T10:01:00Z"),"duplicate")
            self.assertTrue(db.record_market_cap("Mint111",25000,"2026-11-09T11:00:00Z"))
            reopened = TrackerDatabase(path)
            self.assertEqual(reopened.list_tokens()[0]["peak_mc"],25000)
            self.assertEqual(reopened.count(),1)
            self.assertTrue(reopened.integrity_check())

    def test_non_finite_market_caps_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            for bad_value in (float("nan"), float("inf"), float("-inf")):
                token = self._token()
                token["address"] = f"Bad{str(bad_value)}"
                token["market_cap"] = bad_value
                self.assertEqual(db.add_qualified(token, "2026-11-09T10:00:00Z"), "invalid")
            self.assertEqual(db.count(), 0)

    def test_non_finite_market_cap_updates_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            self.assertEqual(db.add_qualified(self._token(), "2026-11-09T10:00:00Z"), "added")
            for bad_value in (float("nan"), float("inf"), float("-inf")):
                self.assertFalse(db.record_market_cap("Mint111", bad_value, "2026-11-09T11:00:00Z"))

    def test_writable_data_mount_is_selected_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("tracker.database.Path.is_dir", return_value=True), patch("tracker.database.os.access", return_value=True):
                self.assertEqual(configured_database_path(), Path("/data/tracker_data.db"))

    def test_environment_path_override(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "persistent" / "tracker.db"
            with patch.dict(os.environ, {"TRACKER_DB_PATH": str(path)}):
                db = TrackerDatabase()
                self.assertEqual(db.path, path)
                self.assertTrue(path.exists())

    def test_backup_is_valid_and_restores_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            live_path = Path(d) / "live" / "tracker.db"
            backup_path = Path(d) / "backups" / "tracker-backup.db"
            live = TrackerDatabase(live_path)
            live.add_qualified(self._token(), "2026-11-09T10:00:00Z")
            live.record_market_cap("Mint111", 25000, "2026-11-09T11:00:00Z")
            self.assertEqual(live.backup_to(backup_path), backup_path)
            restored = TrackerDatabase(backup_path)
            self.assertTrue(restored.integrity_check())
            self.assertEqual(restored.count(), 1)
            self.assertEqual(restored.list_tokens()[0]["peak_mc"], 25000)

    def test_backup_command_uses_configured_separate_directory(self):
        with tempfile.TemporaryDirectory() as d:
            live_path = Path(d) / "live" / "tracker.db"
            backup_dir = Path(d) / "backup-volume"
            with patch.dict(os.environ, {
                "TRACKER_DB_PATH": str(live_path),
                "TRACKER_BACKUP_DIR": str(backup_dir),
            }):
                TrackerDatabase().add_qualified(self._token(), "2026-11-09T10:00:00Z")
                backup = create_backup()
            self.assertEqual(backup.parent, backup_dir)
            self.assertTrue(backup.exists())
            self.assertTrue(TrackerDatabase(backup).integrity_check())

    def test_backup_retention_keeps_only_configured_recent_files(self):
        with tempfile.TemporaryDirectory() as d:
            live_path = Path(d) / "live" / "tracker.db"
            backup_dir = Path(d) / "backups"
            backup_dir.mkdir()
            TrackerDatabase(live_path).add_qualified(self._token(), "2026-11-09T10:00:00Z")
            for name in ("tracker-20000101T000000Z.db", "tracker-20010101T000000Z.db"):
                (backup_dir / name).write_text("old backup")
            with patch.dict(os.environ, {
                "TRACKER_DB_PATH": str(live_path),
                "TRACKER_BACKUP_DIR": str(backup_dir),
                "TRACKER_BACKUP_KEEP": "2",
            }):
                created = create_backup()
            remaining = sorted(backup_dir.glob("tracker-*.db"))
            self.assertEqual(len(remaining), 2)
            self.assertIn(created, remaining)
            self.assertFalse((backup_dir / "tracker-20000101T000000Z.db").exists())

    def test_backup_command_refuses_missing_live_database(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ, {"TRACKER_DB_PATH": str(Path(d) / "missing.db")}):
                with self.assertRaises(FileNotFoundError):
                    create_backup()

    def test_hard_cap_is_exactly_100_qualified_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            for index in range(100):
                token = self._token()
                token["address"] = f"Mint{index}"
                self.assertEqual(db.add_qualified(token, f"2026-11-09T10:{index:02d}:00Z"), "added")
            extra = self._token()
            extra["address"] = "Mint101"
            self.assertEqual(db.add_qualified(extra, "2026-11-09T12:00:00Z"), "full")
            self.assertEqual(db.count(), 100)

    def test_backup_cannot_overwrite_live_database(self):
        with tempfile.TemporaryDirectory() as d:
            db = TrackerDatabase(Path(d) / "tracker.db")
            with self.assertRaises(ValueError):
                db.backup_to(db.path)


class ReportTests(unittest.TestCase):
    def test_performance_report(self):
        rows = [{"symbol":"A","address":"MintA","initial_mc":100,"peak_mc":1200}]
        self.assertEqual(multiple(100,1200),12)
        self.assertIsNone(multiple(100, float("nan")))
        self.assertIsNone(multiple(100, float("inf")))
        self.assertEqual(milestone_hits(rows)["10x"],1)
        report = build_report(rows)
        self.assertIn("12.00x", report)
        self.assertIn("Peak-multiple distribution:", report)
        self.assertIn("10x to <20x: 1", report)
        self.assertNotIn("\\n", report)

    def test_report_handles_missing_and_invalid_market_caps(self):
        rows = [
            {"symbol": "GOOD", "initial_mc": 100, "peak_mc": 200, "current_mc": 150},
            {"symbol": "BAD", "initial_mc": 0, "peak_mc": 500, "current_mc": 0},
            {"symbol": "MISSING", "address": "MintMissing"},
        ]
        report = build_report(rows)
        self.assertIn("Qualified tokens: 3/100", report)
        self.assertIn("Records without valid peak data: 2", report)
        self.assertIn("Median peak multiple (valid records): 2.00x", report)

    def test_csv_export_contains_all_cohort_rows_and_evidence(self):
        import csv
        import json

        with tempfile.TemporaryDirectory() as d:
            rows = [
                {"symbol": "ONE", "name": "Token One", "address": "MintOne",
                 "qualified_at": "2026-11-09T10:00:00Z", "initial_mc": 100,
                 "current_mc": 150, "peak_mc": 1200,
                 "evidence_json": json.dumps({"narrative": NARRATIVE, "attention": ATTENTION})},
                {"symbol": "=2+2", "name": "Token Two", "address": "MintTwo",
                 "qualified_at": "2026-11-09T10:01:00Z", "initial_mc": 200,
                 "current_mc": 100, "peak_mc": 400, "evidence_json": "{}"},
            ]
            path = export_results(rows, Path(d) / "exports" / "results.csv")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                exported = list(csv.DictReader(handle))
            self.assertEqual(len(exported), 2)
            self.assertEqual(exported[0]["symbol"], "ONE")
            self.assertEqual(exported[0]["peak_multiple"], "12.0")
            self.assertIn("Project website", exported[0]["narrative_evidence"])
            self.assertEqual(exported[1]["symbol"], "'=2+2")

    def test_csv_export_rejects_database_extension(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                export_results([], Path(d) / "tracker.db")


if __name__ == "__main__":
    unittest.main()
