import json
import tempfile
import unittest
from pathlib import Path

from tracker.database import TrackerDatabase
from tracker.export import export_results


class CompletedCohortRecoveryTests(unittest.TestCase):
    def test_matching_delivered_csv_recovers_cohort_after_interrupted_finalize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "tracker.db"
            export_path = root / "tracker_results.csv"
            database = TrackerDatabase(database_path)

            for index in range(100):
                result = database.add_qualified(
                    {
                        "address": f"RecoveryMint{index}",
                        "symbol": f"R{index}",
                        "market_cap": 1000 + index,
                    },
                    "2026-11-25T07:00:00+00:00",
                )
                self.assertEqual(result, "added")

            # Simulate Telegram accepting the file, followed by a process crash
            # before finish_completion_export() committed the database changes.
            export_results(database.list_tokens(), export_path)
            with database._connect() as connection:
                connection.execute(
                    "UPDATE completion_export_queue SET status='sending', "
                    "claimed_at='2026-11-25T07:00:00+00:00' WHERE id=1"
                )

            restarted = TrackerDatabase(database_path)
            self.assertTrue(
                restarted.recover_completed_cohort_from_export(export_path)
            )
            self.assertEqual(restarted.current_test_number(), 5)
            self.assertEqual(restarted.count(), 0)
            self.assertEqual(restarted.pending_completion_export_count(), 0)
            cohorts = restarted.list_completed_cohorts()
            self.assertEqual(len(cohorts), 1)
            self.assertEqual(len(json.loads(cohorts[0]["tokens_json"])), 100)

    def test_csv_with_different_addresses_never_advances_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = TrackerDatabase(root / "tracker.db")
            for index in range(100):
                database.add_qualified(
                    {"address": f"LiveMint{index}", "market_cap": 1000},
                    "2026-11-25T07:00:00+00:00",
                )

            wrong_csv = root / "tracker_results.csv"
            wrong_csv.write_text(
                "test_number,address\n" +
                "".join(f"4,OtherMint{index}\n" for index in range(100)),
                encoding="utf-8",
            )
            self.assertFalse(
                database.recover_completed_cohort_from_export(wrong_csv)
            )
            self.assertEqual(database.current_test_number(), 4)
            self.assertEqual(database.count(), 100)


if __name__ == "__main__":
    unittest.main()
