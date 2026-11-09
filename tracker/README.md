# FOMO 10X Tracker Test 4

A separate tracker component with evidence-gated qualification, SQLite persistence, duplicate protection, a 100-token cap, market-cap performance calculations, and reporting.

## Public evidence adapters (v1)

- DexScreener's public token endpoint resolves Solana pair metadata and discovers project websites.
- Public website title/description metadata is captured as a candidate narrative source. It is not a sophisticated narrative-quality judgement; the current v1 gate verifies that documented source evidence exists.
- Reddit public search checks recent posts. Attention requires at least two distinct matching authors and five combined post scores/comments. Posts must match by mint address or by both token name and symbol.
- Requests are read-only, time-limited, and fail closed if a source is unavailable or malformed. No paid X API or private account access is used.

## Pipeline

Call `await evaluate_and_record(token, database=...)` from `tracker.pipeline`. The token must include `address` and a positive `market_cap`; `name` and `symbol` improve source matching. The pipeline collects evidence, requires BOTH narrative and attention checks, then inserts a unique record if the 100-entry cap has not been reached. It returns a status such as `qualified`, `rejected`, `duplicate`, `tracker_full`, or `evidence_error`.

This pipeline is callable independently, but it is NOT connected to `bot.py` yet. Scanner integration is deliberately held for a separate review so this branch cannot alter existing alert behavior.

## Tests

Run from the repository root: `python -m unittest discover -s tests -v`

The SQLite database is created at runtime only; no live database is committed. The scanner and its deployment are not changed.
