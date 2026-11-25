"""Qualification contract for scanner-alerted tokens in the tracker."""
from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    narrative_pass: bool
    attention_pass: bool
    reasons: tuple[str, ...]


def qualify_token(token: dict[str, Any]) -> QualificationResult:
    """Require only a mint address and valid positive reported market cap.

    Narrative and social attention are deliberately informational only. They
    are not reliable mandatory gates for newly launched Solana meme coins.
    """
    address = str(token.get("address", "")).strip()
    try:
        market_cap = float(token.get("market_cap") or 0)
    except (TypeError, ValueError, OverflowError):
        market_cap = 0.0
    valid_market_cap = math.isfinite(market_cap) and market_cap > 0
    reasons = []
    if not address:
        reasons.append("Rejected: missing mint address.")
    if not valid_market_cap:
        reasons.append("Rejected: missing or invalid reported market cap.")
    if address and valid_market_cap:
        reasons.append("Accepted: mint address and reported market cap are valid.")
    return QualificationResult(
        bool(address and valid_market_cap),
        True,
        True,
        tuple(reasons),
    )
