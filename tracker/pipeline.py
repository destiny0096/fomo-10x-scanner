"""Orchestrate address/market-cap qualification and durable cohort recording.
Narrative and Reddit attention collection are intentionally bypassed for Tracker Test 4.
Scanner alerts already pass scanner-side qualification; this component records them
when address and valid starting market-cap data are present.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .database import TrackerDatabase
from .tracker import QualificationResult, qualify_token


def _utc_now() -> str:
    return datetime.now(timezone.utc)


async def evaluate_and_record(
    token: dict[str, Any],
    database: TrackerDatabase | None = None,
    evidence_collector: Any = None,  # retained for backwards-compatible call sites; deliberately unused
) -> dict[str, Any]:
    """Record candidates with an address and positive finite starting market cap.

    No narrative, attention, Reddit, or website checks are performed.
    """
    address = str(token.get("address") or "").strip()
    try:
        market_cap = float(token.get("market_cap") or 0)
    except (TypeError, ValueError, OverflowError):
        market_cap = 0.0

    if not address:
        return {"status": "rejected", "reason": "Missing token address.", "qualification": None}
    if not math.isfinite(market_cap) or market_cap <= 0:
        return {"status": "rejected", "reason": "Missing or invalid starting market cap.", "qualification": None}

    candidate = {
        **token,
        "address": address,
        "market_cap": market_cap,
        "narrative_evidence": [],
        "attention_evidence": [],
    }
    qualification: QualificationResult = qualify_token(candidate)
    if not qualification.qualified:
        return {
            "status": "rejected",
            "reason": " ".join(qualification.reasons),
            "qualification": qualification,
        }

    db = database or TrackerDatabase()
    result = db.add_qualified(candidate, _utc_now().isoformat())
    status_map = {
        "added": "qualified",
        "duplicate": "duplicate",
        "full": "tracker_full",
        "invalid": "rejected",
    }
    return {
        "status": status_map.get(result, "storage_error"),
        "reason": " ".join(qualification.reasons),
        "qualification": qualification,
    }
