"""Pure qualification engine for FOMO 10X Tracker Test 4."""
from dataclasses import dataclass
from typing import Any
from .attention import check_attention
from .narrative import check_narrative

@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    narrative_pass: bool
    attention_pass: bool
    reasons: tuple[str, ...]

def qualify_token(token: dict[str, Any]) -> QualificationResult:
    narrative_ok, nr = check_narrative(token.get("narrative_evidence"))
    attention_ok, ar = check_attention(token.get("attention_evidence"))
    address = str(token.get("address", "")).strip()
    reasons = list(nr + ar)
    if not address:
        reasons.append("Missing token address.")
    passed = bool(address and narrative_ok and attention_ok)
    reasons.append("QUALIFIED: both mandatory checks passed." if passed else "REJECTED: token did not pass every mandatory check.")
    return QualificationResult(passed, narrative_ok, attention_ok, tuple(reasons))
