"""Free public evidence adapters for DexScreener and Reddit.

Project-site URLs are untrusted input. Website requests use HTTPS only, reject
private/local DNS destinations, and do not follow redirects.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp

DEX_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"
REDDIT_SEARCH_URL = "https://www.reddit.com/search.json?q={query}&sort=new&t=week&limit=100"
USER_AGENT = "FOMO10XTracker/1.0 (public evidence research)"


class EvidenceSourceUnavailable(RuntimeError):
    """A temporary public-source/network failure; candidate evaluation must retry."""



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_safe_project_url(url: str) -> bool:
    """Allow only HTTPS URLs with a hostname and no embedded credentials."""
    try:
        parsed = urlsplit(str(url))
        host = parsed.hostname
        # Reject userinfo, non-HTTPS schemes, missing hosts, and malformed ports.
        _ = parsed.port
        if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
            return False
        host = host.rstrip(".").lower()
        if host in {"localhost", "metadata.google.internal"} or host.endswith(
            (".localhost", ".local", ".internal", ".test", ".invalid")
        ):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            # DNS names are checked and pinned by PublicOnlyResolver below.
            return True
    except (TypeError, ValueError, OverflowError):
        return False


class PublicOnlyResolver(aiohttp.abc.AbstractResolver):
    """Resolve hostnames only to globally routable addresses."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            host, port, family=family, type=socket.SOCK_STREAM
        )
        safe = []
        for resolved_family, _socktype, proto, _canonname, sockaddr in records:
            try:
                address = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if not address.is_global:
                continue
            safe.append({
                "hostname": host,
                "host": str(address),
                "port": port,
                "family": resolved_family,
                "proto": proto,
                "flags": socket.AI_NUMERICHOST,
            })
        if not safe:
            raise OSError(f"Host {host!r} did not resolve to a public IP address")
        return safe

    async def close(self):
        return None


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: list[str] = []
        self.description = ""
        self.body_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in {"description", "og:description", "twitter:description"} and not self.description:
                self.description = _clean(attrs.get("content", ""))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if not self._skip_depth:
            cleaned = _clean(data)
            if cleaned:
                self.body_parts.append(cleaned)


async def _get_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any] | None:
    """Return no-result for permanent HTTP misses, but raise on transient outages.

    DNS/connectivity failures, timeouts, rate limits and server errors are not
    evidence that a token lacks narrative or attention. They must reach the
    pipeline as EvidenceSourceUnavailable so its durable queue retries later.
    """
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}) as response:
            if response.status in {408, 425, 429} or response.status >= 500:
                raise EvidenceSourceUnavailable(f"Evidence source returned HTTP {response.status}")
            if response.status != 200:
                return None
            try:
                data = await response.json(content_type=None)
            except (ValueError, aiohttp.ClientError) as exc:
                raise EvidenceSourceUnavailable(f"Evidence source returned invalid JSON: {type(exc).__name__}") from exc
            return data if isinstance(data, dict) else None
    except EvidenceSourceUnavailable:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        raise EvidenceSourceUnavailable(f"Evidence source request failed: {type(exc).__name__}") from exc


async def _get_text(session: aiohttp.ClientSession, url: str) -> str | None:
    if not is_safe_project_url(url):
        return None
    try:
        # Redirects are disabled so a public page cannot redirect into a private host.
        async with session.get(url, headers={"User-Agent": USER_AGENT}, allow_redirects=False) as response:
            if response.status in {408, 425, 429} or response.status >= 500:
                raise EvidenceSourceUnavailable(f"Project website returned HTTP {response.status}")
            if response.status != 200:
                return None
            if "text/html" not in response.headers.get("Content-Type", "").lower():
                return None
            chunks = []
            total_bytes = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 500_000:
                    return None
                chunks.append(chunk)
            encoding = response.charset or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        raise EvidenceSourceUnavailable(f"Project website request failed: {type(exc).__name__}") from exc


async def collect_narrative_evidence(
    session: aiohttp.ClientSession, address: str, token_name: str = "", symbol: str = ""
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Read DexScreener metadata and public project-site description, if available."""
    payload = await _get_json(session, DEX_TOKEN_URL.format(address=quote(address, safe="")))
    if not payload:
        return [], None
    pairs = payload.get("pairs") or []
    sol_pairs = [p for p in pairs if isinstance(p, dict) and p.get("chainId") == "solana"]
    if not sol_pairs:
        return [], None
    def liquidity(pair):
        try:
            return float((pair.get("liquidity") or {}).get("usd") or 0)
        except (TypeError, ValueError, OverflowError):
            return 0.0
    pair = max(sol_pairs, key=liquidity)
    base = pair.get("baseToken") or {}
    info = pair.get("info") or {}
    token_name = token_name or str(base.get("name") or "")
    symbol = symbol or str(base.get("symbol") or "")
    evidence: list[dict[str, str]] = []
    # DexScreener's public token metadata can contain an actual project
    # description even when the project has no reachable website. Treat only
    # that descriptive field as narrative evidence; never promote the token
    # name, symbol, pair title, or social link into a narrative.
    dex_description = _clean(str(info.get("description") or ""))
    dex_url = str(pair.get("url") or f"https://dexscreener.com/solana/{address}")
    if dex_description and dex_url.startswith("https://"):
        evidence.append({
            "source": "DexScreener project description",
            "url": dex_url,
            "summary": dex_description[:500],
            "observed_at": utc_now(),
        })
    websites = info.get("websites") or []
    for site in websites[:2]:
        url = str(site.get("url") or "") if isinstance(site, dict) else ""
        if not is_safe_project_url(url):
            continue
        html = await _get_text(session, url)
        if not html:
            continue
        parser = _MetaParser()
        try:
            parser.feed(html)
        except Exception:
            continue
        title = _clean(" ".join(parser.title_parts))
        description = parser.description
        # Fall back to visible page copy when metadata is absent. Ignore script,
        # style, SVG and noscript contents in the parser; cap the evidence text.
        visible_text = _clean(" ".join(parser.body_parts))
        summary = description or visible_text
        if summary:
            evidence.append({
                "source": "Public project website metadata",
                "url": url,
                "summary": summary[:500],
                "observed_at": utc_now(),
            })
    return evidence, pair


def _identity_match(text: str, address: str, name: str, symbol: str) -> bool:
    haystack = text.lower()
    if address and address.lower() in haystack:
        return True
    name = name.strip().lower()
    symbol = symbol.strip().lower()
    name_match = bool(name and len(name) >= 4 and name in haystack)
    symbol_match = bool(symbol and re.search(rf"(?<![a-z0-9]){re.escape(symbol)}(?![a-z0-9])", haystack))
    # Reddit results may refer to a token by its full name OR its ticker.
    # Address matches remain the strongest identity match.
    return name_match or symbol_match


async def collect_attention_evidence(
    session: aiohttp.ClientSession,
    address: str,
    name: str,
    symbol: str,
    min_posts: int = 1,
    min_total_engagement: int = 1,
) -> list[dict[str, str]]:
    """Collect relevant recent Reddit discussion without numeric engagement gates."""
    query_terms = [term for term in (symbol.strip(), name.strip()) if term]
    query_text = " OR ".join(f'"{term}"' for term in dict.fromkeys(query_terms))
    query = quote(query_text or f'"{symbol}"')
    payload = await _get_json(session, REDDIT_SEARCH_URL.format(query=query))
    if not payload:
        return []
    children = (payload.get("data") or {}).get("children") or []
    matches = []
    authors = set()
    engagement = 0
    seen_posts = set()
    for child in children:
        post = (child or {}).get("data") or {}
        text = _clean(f"{post.get('title', '')} {post.get('selftext', '')}")
        author = str(post.get("author") or "")
        if not author or author == "[deleted]" or not _identity_match(text, address, name, symbol):
            continue
        try:
            score = max(0, int(post.get("score") or 0))
            comments = max(0, int(post.get("num_comments") or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        permalink = str(post.get("permalink") or "")
        if not permalink.startswith("/") or permalink.startswith("//"):
            continue
        post_id = str(post.get("id") or permalink)
        if post_id in seen_posts:
            continue
        seen_posts.add(post_id)
        authors.add(author.lower())
        engagement += score + comments
        matches.append((f"https://www.reddit.com{permalink}", score, comments))
    if not matches:
        return []
    sample = matches[:3]
    links = ", ".join(url for url, _, _ in sample)
    return [{
        "source": "Reddit public search",
        "url": sample[0][0],
        "distinct_authors": len(authors),
        "post_count": len(matches),
        "engagement": engagement,
        "summary": (
            f"Recent public discussion matching this token was found. "
            f"Sample posts: {links}"
        )[:1000],
        "observed_at": utc_now(),
    }]


async def collect_token_evidence(
    address: str, token_name: str = "", symbol: str = "", timeout_seconds: int = 12
) -> dict[str, Any]:
    """Collect both evidence categories; temporary outages propagate for queue retry."""
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    connector = aiohttp.TCPConnector(resolver=PublicOnlyResolver())
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        narrative, pair = await collect_narrative_evidence(session, address, token_name, symbol)
        resolved_name = token_name or str(((pair or {}).get("baseToken") or {}).get("name") or "")
        resolved_symbol = symbol or str(((pair or {}).get("baseToken") or {}).get("symbol") or "")
        attention = await collect_attention_evidence(session, address, resolved_name, resolved_symbol)
    return {"narrative_evidence": narrative, "attention_evidence": attention, "pair": pair}
