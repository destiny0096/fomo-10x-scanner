import unittest
from tracker.sources import _MetaParser, _identity_match

class SourceAdapterTests(unittest.TestCase):
    def test_reads_project_description_metadata(self):
        parser = _MetaParser()
        parser.feed('<html><head><title>Example Token</title><meta name="description" content="A community project about art"></head></html>')
        self.assertEqual(parser.description, "A community project about art")
        self.assertEqual(" ".join(parser.title_parts), "Example Token")

    def test_identity_requires_address_or_name_and_symbol(self):
        self.assertTrue(_identity_match("We are discussing ExampleToken (EXT)", "MintABC", "ExampleToken", "EXT"))
        self.assertTrue(_identity_match("MintABC is trending", "MintABC", "ExampleToken", "EXT"))
        self.assertFalse(_identity_match("EXT is trending", "MintABC", "ExampleToken", "EXT"))
        self.assertFalse(_identity_match("Another project has a similar name", "MintABC", "ExampleToken", "EXT"))

if __name__ == "__main__":
    unittest.main()
