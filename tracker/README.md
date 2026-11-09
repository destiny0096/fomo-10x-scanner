# FOMO 10X Tracker Test 4

A separate tracker component with evidence-gated qualification, SQLite persistence, duplicate protection, a 100-token cap, market-cap monitoring, performance calculations, reporting, and progress notifications through the scanner's existing Telegram bot.

## Public evidence adapters (v1)

- DexScreener's public token endpoint resolves Solana pair metadata and discovers project websites.
- Public project-site descriptions must contain at least 8 words and 55 characters; generic placeholders and title-only snippets are rejected. This is a deterministic quality screen, not a human-level judgement of narrative quality. Project-site fetches use HTTPS only, resolve only to globally routable IP addresses, and do not follow redirects.
- Reddit public search checks recent posts. Attention requires at least 2 distinct authors, at least 2 matching posts, and at least 5 combined post scores/comments. Duplicate post IDs are counted once. Posts must match by mint address or by both token name and symbol.
- Requests are read-only, time-limited, and fail closed if a source is unavailable or malformed. No paid X API or private account access is used.

## Pipeline and scanner integration

After the existing scanner successfully sends its normal Telegram alert, it schedules tracker qualification in the background. Tracker failures do not block the scanner. The pipeline requires BOTH narrative and attention evidence, then inserts a unique record if the 100-entry cap has not been reached.

Only newly qualified records count toward the 100-token cohort. The tracker sends progress notifications at 1, 25, 50, 75, and 100 records using the existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables; no second Telegram bot is needed. The 100th-record notification includes the final report. At completion, the tracker also creates `tracker_results.csv` (override with `TRACKER_EXPORT_PATH`) containing all 100 tokens, starting/current/peak market caps, current and peak multiples, qualification timestamps, and saved narrative/attention evidence. The CSV is sent to the same Telegram chat as a document using the existing bot credentials.

## Market-cap monitoring

The monitor polls DexScreener every five minutes by default, checks only Solana pairs for each recorded mint, and updates current and peak market cap. It uses the reported `marketCap` field only; FDV is not substituted when market cap is missing. The monitor continues observing the cohort after all 100 entries are recorded.

The runtime database uses `/data/tracker_data.db` automatically when `/data` exists and is writable (Deplexo's persistent volume is mounted there by default). Otherwise it uses `tracker_data.db` in the repository root. You can explicitly override either choice with `TRACKER_DB_PATH`. Deplexo's volume survives container restarts and replacements on the same worker, but it is removed if the app itself is deleted. Verify the actual mount and write permissions in the app settings before enabling the tracker. On other hosts, set `TRACKER_DB_PATH` to a directory on that host's persistent disk. The database creates its parent directory automatically, uses SQLite WAL mode and a 30-second busy timeout, and enforces the 100-record cap transactionally.

### Database protection

- Run `python -m tracker.backup` to create a timestamped SQLite backup.
- Set `TRACKER_BACKUP_DIR` to a separate persistent volume/directory. If it is not set, backups go into `tracker_backups` beside the database; that is convenient but does not protect against loss of the whole disk.
- Backups use SQLite's online backup API and are integrity-checked before the backup file is published.
- `TrackerDatabase.integrity_check()` checks the live database; `backup_to(path)` creates a validated backup programmatically.
- When the bot is running, the market-cap monitor creates a validated backup at startup and every 6 hours by default. Set `TRACKER_BACKUP_INTERVAL_SECONDS=0` to disable scheduled backups, `TRACKER_BACKUP_KEEP` to change retention (default 28 files), and `TRACKER_BACKUP_DIR` to choose the destination. Backup failures are logged and do not stop the scanner. Do not treat a backup stored only on the same volume as independent disaster-recovery protection.

Do not use an ephemeral GitHub Actions runner as the long-term live tracker host. Before deployment, verify the `/data` mount and write permissions. A backup stored elsewhere on the same `/data` volume is useful for accidental file-level recovery but is not an independent disaster-recovery backup; periodically copy backups outside the app volume.

## Tests

Run from the repository root: `python -m unittest discover -s tests -v`

The tracker is developed on `feature/fomo-tracker-test-4`. Merge to `main` and deploy only after explicit approval.
