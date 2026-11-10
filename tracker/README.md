# FOMO 10X Tracker Test 4

A separate tracker component with evidence-gated qualification, SQLite persistence, duplicate protection, a 100-token cap, market-cap monitoring, performance calculations, reporting, and progress notifications through the scanner's existing Telegram bot.

## Public evidence adapters (v1)

- DexScreener's public token endpoint resolves Solana pair metadata and discovers project websites.
- Public project-site descriptions must contain at least 8 words and 55 characters; generic placeholders and title-only snippets are rejected. This is a deterministic quality screen, not a human-level judgement of narrative quality. Project-site fetches use HTTPS only, resolve only to globally routable IP addresses, and do not follow redirects.
- Reddit public search checks recent posts. Attention requires at least 2 distinct authors, at least 2 matching posts, and at least 5 combined post scores/comments. Duplicate post IDs are counted once. Posts must match by mint address or by both token name and symbol.
- Requests are read-only, time-limited, and fail closed if a source is unavailable or malformed. No paid X API or private account access is used.

## Pipeline and scanner integration

After the existing scanner successfully sends its normal Telegram alert, it first attempts to persist the alert in a SQLite candidate queue using a short 0.5-second database timeout, then wakes a background worker. The worker claims candidates transactionally, evaluates them, and marks them complete. A transient evidence-source or tracker-database error returns the candidate to pending for a later worker start. A processing claim abandoned by a process crash is eligible for recovery after its 10-minute lease expires. The background worker polls every 60 seconds while queued work remains, so an expired claim or a temporarily unavailable evidence source can be retried without waiting for another scanner alert. On application startup, pending candidates are resumed automatically. Duplicate alert addresses are not queued twice. The queue uses the same tracker database and persistent-volume requirements as the cohort records. Tracker queue writes use a short timeout so a locked/unavailable database does not hold up the scanner; if queue persistence fails, the scanner alert remains successful and the tracker makes a best-effort volatile evaluation, which is not crash recoverable. The pipeline requires BOTH narrative and attention evidence, then inserts a unique record if the 100-entry cap has not been reached.

Only newly qualified records count toward the 100-token cohort. The tracker sends progress notifications at 1, 25, 50, 75, and 100 records using the existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables; no second Telegram bot is needed. Each milestone is placed in a SQLite notification outbox in the same transaction as the token insert, so concurrent qualifying tasks cannot skip a milestone. Failed Telegram deliveries remain queued and are retried on the next qualifying token or at scanner startup; claims abandoned by a process crash become retryable after five minutes. Delivery is at-least-once: if Telegram accepts a message but the process crashes before marking it sent, that milestone may be delivered again after the lease expires. The outbox is included in SQLite backups. The 100th-record notification includes the final report. At completion, the tracker also creates `tracker_results.csv` (override with `TRACKER_EXPORT_PATH`) containing all 100 tokens, starting/current/peak market caps, current and peak multiples, qualification timestamps, and saved narrative/attention evidence. The CSV is sent to the same Telegram chat as a document using the existing bot credentials.

### Shutdown and recovery limits

On a normal shutdown, the scanner gives background tracker work up to 20 seconds to finish, then cancels remaining tasks. A candidate already committed to the queue remains recoverable; cancellation attempts to release its claim immediately, and an unclean crash is recovered when the 10-minute claim lease expires. SQLite transactions protect cohort and queue writes, and milestone notifications already committed to the outbox can be retried after restart. There remains a narrow unavoidable gap between Telegram confirming the scanner alert and the subsequent queue insert: a process crash or database outage in that interval can leave a sent alert without a durable tracker queue entry. If queue persistence fails, the scanner still operates and performs only a best-effort in-memory tracker attempt. Therefore this queue substantially improves restart recovery but is not a guarantee that every Telegram alert is captured under all crash/database-failure conditions.

## Market-cap monitoring

The monitor polls DexScreener every five minutes by default, checks only Solana pairs for each recorded mint, and updates current and peak market cap. It uses the reported `marketCap` field only; FDV is not substituted when market cap is missing. The scanner's existing alert filter may still use its historical FDV fallback, but the tracker receives only the reported `marketCap`; FDV-only candidates are rejected rather than recorded as market cap. The monitor continues observing the cohort after all 100 entries are recorded. Reported peak values are the highest samples captured by the five-minute polling cycle, not guaranteed intraminute/all-time highs; brief price spikes between polls can be missed.

The runtime database uses `/data/tracker_data.db` automatically only when `/data` exists and is writable. Otherwise it uses `tracker_data.db` in the repository root. You can explicitly override either choice with `TRACKER_DB_PATH`. Do not assume a host provides a persistent `/data` mount: verify the actual mount and write permissions in the app settings before enabling the tracker. On other hosts, set `TRACKER_DB_PATH` to a directory on that host's persistent disk. The database creates its parent directory automatically, uses SQLite WAL mode and a 30-second busy timeout, and enforces the 100-record cap transactionally.

### Database protection

- Run `python -m tracker.backup` to create a timestamped SQLite backup.
- Set `TRACKER_BACKUP_DIR` to a separate persistent volume/directory. If it is not set, backups go into `tracker_backups` beside the database; that is convenient but does not protect against loss of the whole disk.
- Backups use SQLite's online backup API and are integrity-checked before the backup file is published.
- `TrackerDatabase.integrity_check()` checks the live database; `backup_to(path)` creates a validated backup programmatically.
- To restore while the bot is stopped, run `python -m tracker.restore /path/to/tracker-backup.db`. The command validates SQLite integrity and required tracker tables, refuses to overwrite an existing live database by default, and refuses replacement when `-wal` or `-shm` sidecars are present. For an intentional replacement, use `python -m tracker.restore /path/to/backup.db --force`; it first creates a validated `.pre-restore-<timestamp>.db` safety copy of the current database. Never run restore while the scanner is active. If sidecars remain after shutdown, do not delete them blindly; investigate/resolve them before retrying.
- When the bot is running, the market-cap monitor creates a validated backup at startup and every 6 hours by default. Set `TRACKER_BACKUP_INTERVAL_SECONDS=0` to disable scheduled backups, `TRACKER_BACKUP_KEEP` to change retention (default 28 files), and `TRACKER_BACKUP_DIR` to choose the destination. Backup failures are logged and do not stop the scanner. Do not treat a backup stored only on the same volume as independent disaster-recovery protection.

Do not use an ephemeral GitHub Actions runner as the long-term live tracker host. Before deployment, verify the persistent-volume mount and write permissions. A backup stored elsewhere on the same volume is useful for accidental file-level recovery but is not an independent disaster-recovery backup; periodically copy backups outside the app volume.

## Tests and deployment preflight

Run from the repository root: `python -m unittest discover -s tests -v`.

After configuring real hosting secrets and persistent mounts, run `python -m tracker.preflight` inside the deployment container. It checks explicit storage paths, separate backup filesystem, SQLite integrity/backup write, Telegram read-only authentication/chat access, DexScreener, and Reddit. It sends no Telegram messages and never prints credentials. Any failed check blocks go-live. See the repository `DEPLOYMENT.md` for provider setup and rollback steps.

The tracker is developed on `feature/fomo-tracker-test-4`. Merge to `main` and deploy only after explicit approval.
