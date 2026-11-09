"""Evidence-based attention checks; source adapters will supply observations."""
from typing import Any
from .narrative import Evidence

def check_attention(evidence: list[dict[str, Any]] | None) -> tuple[bool, list[str]]:
    valid = [Evidence.from_dict(x) for x in (evidence or []) if isinstance(x, dict)]
    valid = [x for x in valid if x.is_verifiable()]
    if valid:
        return True, [f"Attention evidence: {x.source} — {x.summary}" for x in valid]
    return False, ["No verifiable attention evidence supplied."]
