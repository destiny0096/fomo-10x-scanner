"""Attention checks backed by observable public engagement measurements."""
from typing import Any

from .narrative import Evidence

MIN_DISTINCT_AUTHORS = 2
MIN_ENGAGEMENT = 5
MIN_MATCHING_POSTS = 2


def _metric(item: dict[str, Any], key: str) -> int:
    try:
        value = int(item.get(key, 0))
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, value)


def check_attention(evidence: list[dict[str, Any]] | None) -> tuple[bool, list[str]]:
    """Require verifiable Reddit evidence with distinct authors and engagement."""
    valid = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        record = Evidence.from_dict(item)
        if not record.is_verifiable():
            continue
        if "reddit" not in record.source.casefold():
            continue
        authors = _metric(item, "distinct_authors")
        engagement = _metric(item, "engagement")
        posts = _metric(item, "post_count")
        if (
            authors >= MIN_DISTINCT_AUTHORS
            and engagement >= MIN_ENGAGEMENT
            and posts >= MIN_MATCHING_POSTS
        ):
            valid.append((record, authors, engagement, posts))

    if valid:
        return True, [
            f"Attention evidence: {record.source} — {authors} distinct authors, "
            f"{posts} matching posts, {engagement} combined score/comments."
            for record, authors, engagement, posts in valid
        ]
    return False, [
        "No verifiable attention threshold met (requires at least 2 distinct authors, "
        "2 matching posts, and 5 combined score/comments)."
    ]
