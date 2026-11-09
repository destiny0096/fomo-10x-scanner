# FOMO 10X Tracker Test 4

A separate tracker component with evidence-gated qualification, SQLite persistence, duplicate protection, a 100-token cap, market-cap performance calculations, and reporting.

## Public evidence adapters (v1)

- DexScreener's public token endpoint is used to resolve Solana token/pair metadata and discover project websites.
- The adapter reads a public website's HTML title/description as possible narrative evidence. A DexScreener listing or social link alone is NOT narrative proof.
- Reddit's public search JSON is checked for recent posts. Attention passes only when matching posts identify the token by mint address or by BOTH full name and symbol, include distinct authors, and show observable score/comment activity. Defaults are at least two distinct authors and five combined score/comments.
- Requests are read-only, have timeouts, and fail closed when a source is blocked, missing, or malformed. No paid X API or private account access is used.

These are conservative v1 signals, not proof that every account is human or that engagement is organic. Public endpoints can rate-limit or change. The adapters return evidence; they do not yet connect to the live scanner or automatically qualify live alerts.

## Tests

Run from the repository root: `python -m unittest discover -s tests -v`

The SQLite database is created at runtime only; no live database is committed. The scanner and its deployment are not changed by this package.
