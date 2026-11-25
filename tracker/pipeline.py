"""Address-and-market-cap qualification for the separate 100-token tracker."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .database import TrackerDatabase
from .tracker import qualify_token


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def evaluate_candidate(
    token: dict[str, Any], evidence_collector: Any = None
) -> dict[str, Any]:
    """Qualify scanner-alerted tokens without external social/evidence dependencies.

    The scanner has already applied its configured market, momentum, security,
    LP and sell-route filters before handing an alert to this tracker.
    """
    address = str(token.get("address") or "").strip()
    try:
        market_cap = float(token.get("market_cap") or 0)
    except (TypeError, ValueError, OverflowError):
        market_cap = 0.0

    if not address:
        return {"status": "rejected", "reason": "Missing token address.", "qualification": None}
    if not math.isfinite(market_cap) or market_cap <= 0:
        return {"status": "rejected", "reason": "Missing or invalid reported starting market cap.", "qualification": None}

    candidate = {
        **token,
        "address": address,
        "market_cap": market_cap,
        "narrative_evidence": [],
        "attention_evidence": [],
    }
    qualification = qualify_token(candidate)
    return {
        "status": "qualified" if qualification.qualified else "rejected",
        "reason": " ".join(qualification.reasons),
        "candidate": candidate,
        "narrative_pass": True,
        "attention_pass": True,
    }


async def evaluate_and_record(
    token: dict[str, Any], database: TrackerDatabase | None = None,
    evidence_collector: Any = None,
) -> dict[str, Any]:
    """Persist a valid scanner alert into the active 100-token cohort."""
    evaluated = await evaluate_candidate(token)
    if evaluated.get("status") != "qualified":
        return evaluated
    candidate = evaluated["candidate"]
    db = database or TrackerDatabase()
    result = db.add_qualified(candidate, _utc_now())
    status_map = {
        "added": "qualified",
        "duplicate": "duplicate",
        "full": "tracker_full",
        "invalid": "rejected",
    }
    return {
        "status": status_map.get(result, "storage_error"),
        "reason": evaluated["reason"],
        "qualification": qualify_token(candidate),
        "candidate": candidate,
        "narrative_pass": True,
        "attention_pass": True,
    }
