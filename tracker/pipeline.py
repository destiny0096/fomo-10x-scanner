"""Evidence-first qualification and durable tracker recording."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .database import TrackerDatabase
from .tracker import QualificationResult, qualify_token
from .sources import collect_token_evidence, EvidenceSourceUnavailable
from .narrative import check_narrative
from .attention import check_attention


def _utc_now() -> str:
    return datetime.now(timezone.utc)


async def evaluate_candidate(
    token: dict[str, Any], evidence_collector: Any = None
) -> dict[str, Any]:
    """Collect and check narrative + attention before a token can be alerted."""
    address = str(token.get("address") or "").strip()
    try:
        market_cap = float(token.get("market_cap") or 0)
    except (TypeError, ValueError, OverflowError):
        market_cap = 0.0

    if not address:
        return {"status": "rejected", "reason": "Missing token address.", "qualification": None}
    if not math.isfinite(market_cap) or market_cap <= 0:
        return {"status": "rejected", "reason": "Missing or invalid starting market cap.", "qualification": None}

    candidate = {**token, "address": address, "market_cap": market_cap}
    try:
        if "narrative_evidence" in token and "attention_evidence" in token:
            evidence = {
                "narrative_evidence": token.get("narrative_evidence") or [],
                "attention_evidence": token.get("attention_evidence") or [],
            }
        else:
            collector = evidence_collector or collect_token_evidence
            evidence = await collector(
                address, str(token.get("name") or ""), str(token.get("symbol") or "")
            )
    except EvidenceSourceUnavailable as exc:
        return {"status": "evidence_error", "reason": str(exc), "candidate": candidate}
    except Exception as exc:
        return {"status": "evidence_error", "reason": f"Evidence collection failed: {type(exc).__name__}", "candidate": candidate}

    candidate["narrative_evidence"] = evidence.get("narrative_evidence") or []
    candidate["attention_evidence"] = evidence.get("attention_evidence") or []
    narrative_pass, narrative_reasons = check_narrative(candidate["narrative_evidence"])
    attention_pass, attention_reasons = check_attention(candidate["attention_evidence"])
    qualification = qualify_token(candidate)
    reasons = narrative_reasons + attention_reasons
    if not (narrative_pass and attention_pass and qualification.qualified):
        return {
            "status": "rejected",
            "reason": " ".join(reasons),
            "candidate": candidate,
            "narrative_pass": narrative_pass,
            "attention_pass": attention_pass,
        }
    candidate["evidence_summary"] = reasons
    return {
        "status": "qualified", "reason": " ".join(reasons),
        "candidate": candidate, "narrative_pass": True, "attention_pass": True,
    }


async def evaluate_and_record(
    token: dict[str, Any], database: TrackerDatabase | None = None,
    evidence_collector: Any = None,
) -> dict[str, Any]:
    """Evaluate evidence, then persist only if both checks pass."""
    evaluated = await evaluate_candidate(token, evidence_collector=evidence_collector)
    if evaluated.get("status") != "qualified":
        return evaluated
    candidate = evaluated["candidate"]
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
        "reason": evaluated["reason"],
        "qualification": qualify_token(candidate),
        "candidate": candidate,
        "narrative_pass": True,
        "attention_pass": True,
    }
