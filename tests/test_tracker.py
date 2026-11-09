import tempfile, unittest
from pathlib import Path
from tracker.database import TrackerDatabase
from tracker.performance import milestone_hits, multiple
from tracker.report import build_report
from tracker.tracker import qualify_token
NARRATIVE = [{"source":"Project website","url":"https://example.org/about","summary":"Documented project theme and purpose","observed_at":"2026-11-09T10:00:00Z"}]
ATTENTION = [{"source":"Public community post","url":"https://example.org/community","summary":"Public discussion with observable engagement","observed_at":"2026-11-09T10:01:00Z"}]
class QualificationTests(unittest.TestCase):
    def test_both_checks_required(self):
        r=qualify_token({"address":"Mint111","narrative_evidence":NARRATIVE,"attention_evidence":[]}); self.assertFalse(r.qualified); self.assertTrue(r.narrative_pass); self.assertFalse(r.attention_pass)
    def test_both_evidence_categories_pass(self):
        self.assertTrue(qualify_token({"address":"Mint111","narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}).qualified)
    def test_unlinked_evidence_fails(self):
        bad=[{"source":"unknown","url":"","summary":"Trust me","observed_at":"now"}]
        self.assertFalse(qualify_token({"address":"Mint111","narrative_evidence":bad,"attention_evidence":ATTENTION}).qualified)
    def test_address_required(self):
        self.assertFalse(qualify_token({"narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}).qualified)
class PersistenceTests(unittest.TestCase):
    def test_insert_duplicate_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            db=TrackerDatabase(Path(d)/"test.db"); t={"address":"Mint111","symbol":"TEST","market_cap":10000,"narrative_evidence":NARRATIVE,"attention_evidence":ATTENTION}
            self.assertEqual(db.add_qualified(t,"2026-11-09T10:00:00Z"),"added"); self.assertEqual(db.add_qualified(t,"2026-11-09T10:01:00Z"),"duplicate")
            self.assertTrue(db.record_market_cap("Mint111",25000,"2026-11-09T11:00:00Z")); self.assertEqual(db.list_tokens()[0]["peak_mc"],25000); self.assertEqual(db.count(),1)
    def test_performance_report(self):
        rows=[{"symbol":"A","address":"MintA","initial_mc":100,"peak_mc":1200}]
        self.assertEqual(multiple(100,1200),12); self.assertEqual(milestone_hits(rows)["10x"],1); self.assertIn("12.00x",build_report(rows))
if __name__=="__main__": unittest.main()
