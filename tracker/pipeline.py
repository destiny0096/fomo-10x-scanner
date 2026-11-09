"""Orchestrate evidence collection, qualification, and durable recording.

This is intentionally callable independently of bot.py. Scanner integration is a
separate, explicitly reviewed change so this module cannot alter Telegram alerts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Awaitable, Callable

from .database import TrackerDatabase
from .sources import collect_token_evidence
from .tracker import QualificationResult, qualify_token

EvidenceCollector = Callable[..., Awaitable[dict[str, Any]]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def evaluate_and_record(
    token: dict[str, Any],
    database: TrackerDatabase | None = None,
    evidence_collector: EvidenceCollector = collect_token_evidence,
) -> dict[str, Any]:
    """Collect evidence, require both checks, and store no more than 100 entries.

    Required token keys: address and a positive market_cap. Name and symbol are
    helpful for public-source identity matching. A missing/invalid MC is rejected
    because the tracker cannot calculate a meaningful starting multiple.
    """
    address = str(token.get("address") or "").strip()
    try:
        market_cap = float(token.get("market_cap") or 0)
    except (TypeError, ValueError):
        market_cap = 0.0

    if not address:
        return {"status": "rejected", "reason": "Missing token address.", "qualification": None}
    if not math.isfinite(market_cap) or market_cap <= 0:
        return {"status": "rejected", "reason": "Missing or invalid starting market cap.", "qualification": None}

    try:
        evidence = await evidence_collector(
            address=address,
            token_name=str(token.get("name") or ""),
            symbol=str(token.get("symbol") or ""),
        )
    except Exception as exc:
        # A source outage is a fail-closed result, not a scanner-fatal exception.
        return {"status": "evidence_error", "reason": f"Evidence collection failed: {type(exc).__name__}"}

    candidate = {
        **token,
        "address": address,
        "market_cap": market_cap,
        "narrative_evidence": evidence.get("narrative_evidence") or [],
        "attention_evidence": evidence.get("attention_evidence") or [],
    }
    qualification: QualificationResult = qualify_token(candidate)
    if not qualification.qualified:
        return {
            "status": "rejected",
            "reason": " ".join(qualification.reasons),
            "qualification": qualification,
        }

    db = database or TrackerDatabase()
    result = db.add_qualified(candidate, _utc_now())
    status_map = {"added": "qualified", "duplicate": "duplicate", "full": "tracker_full", "invalid": "rejected"}
    return {
        "status": status_map.get(result, "storage_error"),
        "reason": " ".join(qualification.reasons),
        "qualification": qualification,
    }
