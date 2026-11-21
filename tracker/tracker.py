"""Address-only qualification for the FOMO 10X Tracker Test 4 cohort."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    narrative_pass: bool
    attention_pass: bool
    reasons: tuple[str, ...]


def qualify_token(token: dict[str, Any]) -> QualificationResult:
    """Accept any candidate with a non-empty mint address; no other gates."""
    address = str(token.get("address", "")).strip()
    passed = bool(address)
    reasons = ("Accepted: mint address present.",) if passed else ("Rejected: missing mint address.",)
    # Legacy fields retained for compatibility. These are not checks.
    return QualificationResult(passed, True, True, reasons)
