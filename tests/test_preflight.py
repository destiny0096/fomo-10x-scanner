import tempfile
import unittest
from pathlib import Path

from tracker.preflight import check_storage


class StoragePreflightTests(unittest.TestCase):
    def test_missing_explicit_storage_paths_fail(self):
        results = check_storage({})
        self.assertTrue(any(name == "TRACKER_DB_PATH" and not passed for name, passed, _ in results))
        self.assertTrue(any(name == "TRACKER_BACKUP_DIR" and not passed for name, passed, _ in results))

    def test_relative_storage_paths_fail(self):
        results = check_storage({
            "TRACKER_DB_PATH": "tracker.db",
            "TRACKER_BACKUP_DIR": "backups",
        })
        self.assertFalse(results[0][1])

    def test_writable_same_volume_is_allowed_with_backup_warning_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = check_storage({
                "TRACKER_DB_PATH": str(root / "data" / "tracker.db"),
                "TRACKER_BACKUP_DIR": str(root / "backups"),
            })
            by_name = {name: (passed, detail) for name, passed, detail in results}
            self.assertTrue(by_name["storage writable"][0])
            self.assertTrue(by_name["local backup"][0])
            self.assertIn("WARNING", by_name["local backup"][1])
            self.assertTrue(by_name["SQLite integrity"][0])
            self.assertTrue(by_name["backup write and validation"][0])

    def test_same_volume_can_be_rejected_when_separate_volume_is_explicitly_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = check_storage({
                "TRACKER_DB_PATH": str(root / "data" / "tracker.db"),
                "TRACKER_BACKUP_DIR": str(root / "backups"),
                "TRACKER_REQUIRE_SEPARATE_BACKUP_VOLUME": "true",
            })
            by_name = {name: (passed, detail) for name, passed, detail in results}
            self.assertFalse(by_name["backup independence"][0])


if __name__ == "__main__":
    unittest.main()
