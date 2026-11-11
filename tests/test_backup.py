import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tracker.backup import create_backup
from tracker.database import TrackerDatabase


class BackupTests(unittest.TestCase):
    def test_creates_integrity_checked_backup_in_configured_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "data" / "tracker.db"
            backup_dir = root / "backups"
            TrackerDatabase(database_path)

            with patch.dict("os.environ", {
                "TRACKER_DB_PATH": str(database_path),
                "TRACKER_BACKUP_DIR": str(backup_dir),
            }, clear=False):
                backup = create_backup()

            self.assertTrue(backup.is_file())
            self.assertEqual(backup.parent, backup_dir)
            check = TrackerDatabase(backup)
            self.assertTrue(check.integrity_check())

    def test_retention_keeps_only_the_newest_configured_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "data" / "tracker.db"
            backup_dir = root / "backups"
            TrackerDatabase(database_path)
            backup_dir.mkdir(parents=True)
            old_one = backup_dir / "tracker-20200101T000000000000Z.db"
            old_two = backup_dir / "tracker-20200102T000000000000Z.db"
            old_one.write_bytes(b"old")
            old_two.write_bytes(b"old")

            with patch.dict("os.environ", {
                "TRACKER_DB_PATH": str(database_path),
                "TRACKER_BACKUP_DIR": str(backup_dir),
                "TRACKER_BACKUP_KEEP": "2",
            }, clear=False):
                create_backup()

            backups = sorted(backup_dir.glob("tracker-*.db"))
            self.assertEqual(len(backups), 2)
            self.assertFalse(old_one.exists())
            self.assertTrue(old_two.exists())


if __name__ == "__main__":
    unittest.main()
