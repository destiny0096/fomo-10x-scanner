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
    """Narrative and attention are disabled for this test; address is the sole gate."""
    address = str(token.get("address", "")).strip()
    passed = bool(address)
    reasons = [] if passed else ["Missing token address."]
    reasons.append("QUALIFIED: narrative and attention checks disabled for Test 4." if passed
                  else "REJECTED: missing token address.")
    # Pass flags remain True for compatibility with older diagnostic consumers;
    # these checks are intentionally not evaluated or required in this test.
    return QualificationResult(passed, True, True, tuple(reasons))
