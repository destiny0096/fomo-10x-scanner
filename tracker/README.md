# FOMO 10X Tracker Test 4 — first build

This package is separate from the existing scanner. It provides a qualification engine requiring BOTH link-backed narrative and attention evidence, SQLite storage, duplicate protection, a hard 100-token storage limit, peak-multiple calculations, and a text report.

## Current boundary

This first build does not fetch social data, connect to the scanner, start live tracking, or deploy. A future source-adapter layer must supply evidence with a source, HTTP(S) URL, summary, and observation timestamp. Missing evidence fails closed.

## Tests

Run from the repository root: python -m unittest discover -s tests -v

The SQLite database is created only when TrackerDatabase is instantiated; no live database is committed.
