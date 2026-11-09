"""Defensive market-cap multiple and cohort milestone calculations."""
from __future__ import annotations


def _positive_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def multiple(initial_mc: float, observed_mc: float) -> float | None:
    initial = _positive_number(initial_mc)
    observed = _positive_number(observed_mc)
    if initial is None or observed is None:
        return None
    return observed / initial


def peak_multiple(token: dict) -> float | None:
    return multiple(token.get("initial_mc"), token.get("peak_mc"))


def current_multiple(token: dict) -> float | None:
    return multiple(token.get("initial_mc"), token.get("current_mc"))


def milestone_hits(tokens: list[dict], milestones=(1, 2, 3, 5, 10, 20)) -> dict[str, int]:
    values = [peak_multiple(token) for token in tokens]
    return {
        f"{milestone}x": sum(1 for value in values if value is not None and value >= milestone)
        for milestone in milestones
    }
