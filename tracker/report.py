"""Human-readable Test 4 summary generation."""
from .performance import milestone_hits, multiple


def build_report(tokens: list[dict]) -> str:
    lines = [
        "FOMO 10X TRACKER TEST 4",
        f"Qualified tokens: {len(tokens)}/100",
        "",
        "Peak market-cap milestones:",
    ]
    lines.extend(
        f"- {label}: {count}"
        for label, count in milestone_hits(tokens).items()
    )

    if tokens:
        valid = [
            row for row in tokens
            if multiple(float(row.get("initial_mc") or 0), float(row.get("peak_mc") or 0))
        ]
        current = [
            (row, multiple(float(row.get("initial_mc") or 0), float(row.get("current_mc") or 0)))
            for row in tokens
        ]
        current = [(row, value) for row, value in current if value is not None]

        if valid:
            top = max(
                valid,
                key=lambda row: multiple(float(row["initial_mc"]), float(row["peak_mc"])) or 0,
            )
            peak_multiple = multiple(float(top["initial_mc"]), float(top["peak_mc"]))
            lines.extend([
                "",
                f"Top peak performer: {top.get('symbol') or top['address']}",
                f"Peak multiple: {peak_multiple:.2f}x",
            ])

        if current:
            top_current, current_multiple = max(current, key=lambda item: item[1])
            lines.extend([
                "",
                f"Best current performer: {top_current.get('symbol') or top_current['address']}",
                f"Current multiple: {current_multiple:.2f}x",
            ])

    return "\\n".join(lines)
