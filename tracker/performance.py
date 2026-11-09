"""Performance calculations for qualified tracker entries."""
def multiple(initial_mc: float, observed_mc: float) -> float | None:
    if initial_mc <= 0 or observed_mc <= 0: return None
    return observed_mc / initial_mc

def milestone_hits(tokens: list[dict], milestones=(1, 2, 3, 5, 10, 20)) -> dict[str, int]:
    return {f"{m}x": sum(1 for t in tokens if (multiple(float(t["initial_mc"]), float(t["peak_mc"])) or 0) >= m) for m in milestones}
