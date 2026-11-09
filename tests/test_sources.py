import asyncio
import socket
import unittest
from unittest.mock import patch

from tracker.sources import (
    PublicOnlyResolver, _MetaParser, _identity_match, _clean, is_safe_project_url,
)


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

    def test_project_site_url_must_be_safe_https(self):
        self.assertTrue(is_safe_project_url("https://example.org/about"))
        self.assertFalse(is_safe_project_url("http://example.org"))
        self.assertFalse(is_safe_project_url("https://localhost/admin"))
        self.assertFalse(is_safe_project_url("https://127.0.0.1/admin"))
        self.assertFalse(is_safe_project_url("https://[::1]/admin"))
        self.assertFalse(is_safe_project_url("https://service.internal"))
        self.assertFalse(is_safe_project_url("https://user:pass@example.org"))
        self.assertFalse(is_safe_project_url("javascript:alert(1)"))


class PublicResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolver_returns_only_public_ip_addresses(self):
        class FakeLoop:
            async def getaddrinfo(self, host, port, family, type):
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port)),
                    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port)),
                ]

        with patch("tracker.sources.asyncio.get_running_loop", return_value=FakeLoop()):
            records = await PublicOnlyResolver().resolve("example.org", 443, socket.AF_UNSPEC)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["host"], "8.8.8.8")

    async def test_resolver_rejects_hosts_that_only_resolve_private(self):
        class FakeLoop:
            async def getaddrinfo(self, host, port, family, type):
                return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.5", port))]

        with patch("tracker.sources.asyncio.get_running_loop", return_value=FakeLoop()):
            with self.assertRaises(OSError):
                await PublicOnlyResolver().resolve("internal.example", 443, socket.AF_UNSPEC)


if __name__ == "__main__":
    unittest.main()
