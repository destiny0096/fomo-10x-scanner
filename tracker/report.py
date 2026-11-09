"""Human-readable Test 4 cohort summary generation."""
from statistics import mean, median

from .performance import current_multiple, milestone_hits, peak_multiple


def _label(token: dict) -> str:
    return str(token.get("symbol") or token.get("name") or token.get("address") or "Unknown token")


def build_report(tokens: list[dict]) -> str:
    """Build a compact summary suitable for the final Telegram notification."""
    count = len(tokens)
    peaks = [value for token in tokens if (value := peak_multiple(token)) is not None]
    currents = [
        (token, value)
        for token in tokens
        if (value := current_multiple(token)) is not None
    ]

    lines = [
        "FOMO 10X TRACKER TEST 4",
        f"Qualified tokens: {count}/100",
        "",
        "Peak market-cap performance:",
    ]
    lines.extend(f"- Reached {label}: {number}" for label, number in milestone_hits(tokens).items())

    if peaks:
        bins = (
            ("Below 1x", lambda value: value < 1),
            ("1x to <2x", lambda value: 1 <= value < 2),
            ("2x to <3x", lambda value: 2 <= value < 3),
            ("3x to <5x", lambda value: 3 <= value < 5),
            ("5x to <10x", lambda value: 5 <= value < 10),
            ("10x to <20x", lambda value: 10 <= value < 20),
            ("20x or more", lambda value: value >= 20),
        )
        lines.extend(["", "Peak-multiple distribution:"])
        lines.extend(
            f"- {label}: {sum(1 for value in peaks if condition(value))}"
            for label, condition in bins
        )
        lines.extend([
            "",
            f"Average peak multiple (valid records): {mean(peaks):.2f}x",
            f"Median peak multiple (valid records): {median(peaks):.2f}x",
            f"Records without valid peak data: {count - len(peaks)}",
        ])

        top_peak = sorted(
            ((token, value) for token in tokens if (value := peak_multiple(token)) is not None),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        lines.extend(["", "Top 5 by peak market-cap multiple:"])
        lines.extend(
            f"{index}. {_label(token)} — {value:.2f}x"
            for index, (token, value) in enumerate(top_peak, start=1)
        )

    if currents:
        top_current = sorted(currents, key=lambda item: item[1], reverse=True)[:5]
        lines.extend(["", "Top 5 by current market-cap multiple:"])
        lines.extend(
            f"{index}. {_label(token)} — {value:.2f}x"
            for index, (token, value) in enumerate(top_current, start=1)
        )

    lines.extend([
        "",
        "Multiples compare market cap with the starting market cap; they are not trading PnL.",
    ])
    return "\n".join(lines)
