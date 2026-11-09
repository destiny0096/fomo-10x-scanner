"""Evidence-based narrative checks; never infer missing evidence."""
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

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
        return bool(self.source and parsed.scheme in {"http", "https"} and parsed.netloc and self.summary and self.observed_at)

def check_narrative(evidence: list[dict[str, Any]] | None) -> tuple[bool, list[str]]:
    valid = [Evidence.from_dict(x) for x in (evidence or []) if isinstance(x, dict)]
    valid = [x for x in valid if x.is_verifiable()]
    if valid:
        return True, [f"Narrative evidence: {x.source} — {x.summary}" for x in valid]
    return False, ["No verifiable narrative evidence supplied."]
