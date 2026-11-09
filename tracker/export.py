"""CSV export for the completed 100-token Test 4 cohort."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from .performance import current_multiple, peak_multiple


CSV_FIELDS = [
    "rank", "symbol", "name", "address", "qualified_at",
    "starting_market_cap", "current_market_cap", "peak_market_cap",
    "current_multiple", "peak_multiple",
    "narrative_evidence", "attention_evidence",
]


def _evidence_columns(token: dict[str, Any]) -> tuple[str, str]:
    raw = token.get("evidence_json") or "{}"
    try:
        evidence = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        evidence = {}
    if not isinstance(evidence, dict):
        evidence = {}
    return (
        json.dumps(evidence.get("narrative", []), ensure_ascii=False, sort_keys=True),
        json.dumps(evidence.get("attention", []), ensure_ascii=False, sort_keys=True),
    )


def export_results(tokens: list[dict[str, Any]], destination: str | Path) -> Path:
    """Write a deterministic, spreadsheet-friendly CSV using an atomic replace."""
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    ranked = sorted(
        tokens,
        key=lambda token: peak_multiple(token) or 0,
        reverse=True,
    )
    try:
        with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for rank, token in enumerate(ranked, start=1):
                narrative, attention = _evidence_columns(token)
                writer.writerow({
                    "rank": rank,
                    "symbol": token.get("symbol", ""),
                    "name": token.get("name", ""),
                    "address": token.get("address", ""),
                    "qualified_at": token.get("qualified_at", ""),
                    "starting_market_cap": token.get("initial_mc", ""),
                    "current_market_cap": token.get("current_mc", ""),
                    "peak_market_cap": token.get("peak_mc", ""),
                    "current_multiple": current_multiple(token) or "",
                    "peak_multiple": peak_multiple(token) or "",
                    "narrative_evidence": narrative,
                    "attention_evidence": attention,
                })
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
