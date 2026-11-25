"""Attention checks backed by relevant, observable public discussion."""
from typing import Any

from .narrative import Evidence


def check_attention(evidence: list[dict[str, Any]] | None) -> tuple[bool, list[str]]:
    """Pass when verifiable, token-relevant public discussion exists.

    Deliberately does not impose numeric post, author, score, or engagement
    thresholds. Evidence must still be a real URL with a source, summary and
    observation timestamp, and must identify Reddit/public discussion.
    """
    valid = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        record = Evidence.from_dict(item)
        if not record.is_verifiable():
            continue
        source = record.source.casefold()
        if "reddit" not in source and "public discussion" not in source:
            continue
        if not record.summary.strip():
            continue
        valid.append(record)
    if valid:
        return True, [
            f"Attention evidence: {record.source} — {record.summary}"
            for record in valid
        ]
    return False, [
        "No verifiable, token-relevant public discussion was found."
    ]
