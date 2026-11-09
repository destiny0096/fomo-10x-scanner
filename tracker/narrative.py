"""Evidence-based narrative checks; never infer missing evidence."""
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

MIN_NARRATIVE_WORDS = 8
MIN_NARRATIVE_CHARACTERS = 55
GENERIC_NARRATIVE_PHRASES = (
    "coming soon",
    "website coming soon",
    "lorem ipsum",
    "test token",
    "no description",
    "to be announced",
    "tba",
)


@dataclass(frozen=True)
class Evidence:
    source: str
    url: str
    summary: str
    observed_at: str

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "Evidence":
        return cls(*(str(item.get(k, "")).strip() for k in ("source", "url", "summary", "observed_at")))

    def is_verifiable(self) -> bool:
        parsed = urlparse(self.url)
        return bool(
            self.source
            and parsed.scheme in {"http", "https"}
            and parsed.netloc
            and self.summary
            and self.observed_at
        )


def _is_substantive_narrative(evidence: Evidence) -> bool:
    summary = " ".join(evidence.summary.split())
    lowered = summary.casefold()
    if any(re.search(rf"\\b{re.escape(phrase)}\\b", lowered) for phrase in GENERIC_NARRATIVE_PHRASES):
        return False
    words = summary.split()
    return len(summary) >= MIN_NARRATIVE_CHARACTERS and len(words) >= MIN_NARRATIVE_WORDS


def check_narrative(evidence: list[dict[str, Any]] | None) -> tuple[bool, list[str]]:
    candidates = [Evidence.from_dict(item) for item in (evidence or []) if isinstance(item, dict)]
    valid = [item for item in candidates if item.is_verifiable() and _is_substantive_narrative(item)]
    if valid:
        return True, [f"Narrative evidence: {item.source} — {item.summary}" for item in valid]
    return False, [
        "No verifiable, substantive project narrative found (requires a descriptive explanation, not a placeholder or title alone)."
    ]
