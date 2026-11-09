# FOMO 10X Tracker Test 4

A separate tracker component with evidence-gated qualification, SQLite persistence, duplicate protection, a 100-token cap, market-cap monitoring, performance calculations, reporting, and progress notifications through the scanner's existing Telegram bot.

## Public evidence adapters (v1)

- DexScreener's public token endpoint resolves Solana pair metadata and discovers project websites.
- Public website title/description metadata is captured as candidate narrative evidence. This is an initial evidence gate, not a sophisticated judgement of narrative quality.
- Reddit public search checks recent posts. Attention requires at least two distinct matching authors and five combined post scores/comments. Posts must match by mint address or by both token name and symbol.
- Requests are read-only, time-limited, and fail closed if a source is unavailable or malformed. No paid X API or private account access is used.

## Pipeline and scanner integration

After the existing scanner successfully sends its normal Telegram alert, it schedules tracker qualification in the background. Tracker failures do not block the scanner. The pipeline requires BOTH narrative and attention evidence, then inserts a unique record if the 100-entry cap has not been reached.

Only newly qualified records count toward the 100-token cohort. The tracker sends progress notifications at 1, 25, 50, 75, and 100 records using the existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables; no second Telegram bot is needed. The 100th-record notification includes the final report.

## Market-cap monitoring

The monitor polls DexScreener every five minutes by default, checks only Solana pairs for each recorded mint, and updates current and peak market cap. It uses the reported `marketCap` field only; FDV is not substituted when market cap is missing. The monitor continues observing the cohort after all 100 entries are recorded.

The runtime database is `tracker_data.db` in the repository root by default. On Deplexo, configure `TRACKER_DB_PATH=/data/tracker_data.db`; Deplexo mounts a persistent data volume at `/data` by default. The volume survives container restarts and replacements on the same worker, but it is removed if the app itself is deleted. Verify the actual mount and write permissions in the app settings before enabling the tracker. On other hosts, set `TRACKER_DB_PATH` to a directory on that host's persistent disk. The database creates its parent directory automatically, uses SQLite WAL mode and a 30-second busy timeout, and enforces the 100-record cap transactionally.

### Database protection

- Run `python -m tracker.backup` to create a timestamped SQLite backup.
- Set `TRACKER_BACKUP_DIR` to a separate persistent volume/directory. If it is not set, backups go into `tracker_backups` beside the database; that is convenient but does not protect against loss of the whole disk.
- Backups use SQLite's online backup API and are integrity-checked before the backup file is published.
- `TrackerDatabase.integrity_check()` checks the live database; `backup_to(path)` creates a validated backup programmatically.
- Backups are not yet scheduled automatically. The host must provide a scheduled task/cron facility, or an operator must run the command. Do not treat a backup stored only on the same ephemeral disk as durable protection.

Do not use an ephemeral GitHub Actions runner as the long-term live tracker host. Before deployment, verify the `/data` mount and write permissions. A backup stored elsewhere on the same `/data` volume is useful for accidental file-level recovery but is not an independent disaster-recovery backup; periodically copy backups outside the app volume.

## Tests

Run from the repository root: `python -m unittest discover -s tests -v`

The tracker is developed on `feature/fomo-tracker-test-4`. Merge to `main` and deploy only after explicit approval.
