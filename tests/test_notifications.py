import unittest

from tracker.notifications import progress_message


class TrackerProgressNotificationTests(unittest.TestCase):
    def test_progress_milestones_only(self):
        token = {"address": "Mint1", "symbol": "ONE", "initial_mc": 100, "peak_mc": 100, "current_mc": 100}
        self.assertIn("1/100", progress_message(1, [token]))
        self.assertIn("25/100", progress_message(25, [token]))
        self.assertIsNone(progress_message(24, [token]))

    def test_hundredth_record_includes_full_final_report(self):
        tokens = [
            {
                "address": f"Mint{i}",
                "symbol": f"T{i}",
                "initial_mc": 100,
                "peak_mc": 1200 if i == 1 else 100,
                "current_mc": 1100 if i == 1 else 100,
            }
            for i in range(100)
        ]
        message = progress_message(100, tokens)
        self.assertIn("TEST 4 COMPLETE", message)
        self.assertIn("Qualified tokens: 100/100", message)
        self.assertIn("12.00x", message)
        self.assertIn("Peak-multiple distribution:", message)
        self.assertIn("Median peak multiple", message)
        self.assertIn("not trading PnL", message)


if __name__ == "__main__":
    unittest.main()
