"""Qualification contract shared by scanner and tracker components."""
from dataclasses import dataclass
from typing import Any

from .narrative import check_narrative
from .attention import check_attention


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    narrative_pass: bool
    attention_pass: bool
    reasons: tuple[str, ...]


def qualify_token(token: dict[str, Any]) -> QualificationResult:
    """Require a mint address plus verifiable narrative and public attention."""
    address = str(token.get("address", "")).strip()
    narrative_pass, narrative_reasons = check_narrative(token.get("narrative_evidence"))
    attention_pass, attention_reasons = check_attention(token.get("attention_evidence"))
    reasons = []
    if not address:
        reasons.append("Rejected: missing mint address.")
    reasons.extend(narrative_reasons)
    reasons.extend(attention_reasons)
    if address and narrative_pass and attention_pass:
        reasons.insert(0, "Accepted: narrative and attention checks passed.")
    return QualificationResult(
        bool(address and narrative_pass and attention_pass),
        narrative_pass,
        attention_pass,
        tuple(reasons),
    )
