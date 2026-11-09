"""Human-readable Test 4 summary generation."""
from .performance import milestone_hits
def build_report(tokens: list[dict]) -> str:
    lines = ["FOMO 10X TRACKER TEST 4", f"Qualified tokens: {len(tokens)}/100", "", "Peak market-cap milestones:"]
    lines.extend(f"- {label}: {count}" for label, count in milestone_hits(tokens).items())
    if tokens:
        top = max(tokens, key=lambda row: row["peak_mc"] / row["initial_mc"])
        lines.extend(["", f"Top performer: {top['symbol'] or top['address']}", f"Peak multiple: {top['peak_mc'] / top['initial_mc']:.2f}x"])
    return "\n".join(lines)
