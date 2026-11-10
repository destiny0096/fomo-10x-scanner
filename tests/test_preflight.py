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

    def test_writable_same_volume_is_flagged_as_not_independent_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = check_storage({
                "TRACKER_DB_PATH": str(root / "data" / "tracker.db"),
                "TRACKER_BACKUP_DIR": str(root / "backups"),
            })
            by_name = {name: (passed, detail) for name, passed, detail in results}
            self.assertTrue(by_name["storage writable"][0])
            self.assertFalse(by_name["independent backup volume"][0])
            self.assertTrue(by_name["SQLite integrity"][0])
            self.assertTrue(by_name["backup write and validation"][0])

    def test_same_volume_can_only_be_allowed_with_explicit_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = check_storage({
                "TRACKER_DB_PATH": str(root / "data" / "tracker.db"),
                "TRACKER_BACKUP_DIR": str(root / "backups"),
                "TRACKER_REQUIRE_SEPARATE_BACKUP_VOLUME": "false",
            })
            by_name = {name: (passed, detail) for name, passed, detail in results}
            self.assertFalse(by_name["independent backup volume"][0])
            self.assertIn("WARNING", by_name["independent backup volume"][1])


if __name__ == "__main__":
    unittest.main()
