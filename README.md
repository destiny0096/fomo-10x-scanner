# FOMO 10X Scanner + Tracker Test 4

Solana token-discovery and Telegram alert scanner, with a separate evidence-gated 100-token performance tracker.

## Current development status

- Tracker development branch: `feature/fomo-tracker-test-4`.
- The existing scanner remains the discovery and alert system; the tracker is a separate component.
- The tracker records a token only when BOTH narrative and public-attention evidence pass.
- Tracker cohort cap: exactly 100 qualified tokens.
- Scanner filters and alert behavior are not replaced by the tracker.
- Do not merge or deploy until the release checks in [DEPLOYMENT.md](DEPLOYMENT.md) are complete and explicitly approved.

## Runtime

Start command:

```bash
python bot.py
```

The health server listens on `PORT` (default `3000`) and responds at `/` and `/health`. This is a process-liveness check, not proof that Telegram, DexScreener, Reddit, or persistent storage is healthy.

## Required environment variables

Configure these in the hosting provider's secret/environment settings. Never commit real values to GitHub.

- `TELEGRAM_BOT_TOKEN` — existing scanner bot token.
- `TELEGRAM_CHAT_ID` — existing destination chat ID.
- On Deplexo, the tracker automatically uses `/data/tracker_data.db` and stores local backups in `/data/tracker_backups` when the persistent `/data` mount is available.
- `TRACKER_DB_PATH` and `TRACKER_BACKUP_DIR` are optional overrides for other hosting setups.

Recommended tracker settings:

- `TRACKER_MC_POLL_SECONDS=300` — market-cap polling interval (minimum 60 seconds).
- `TRACKER_BACKUP_INTERVAL_SECONDS=21600` — backup every six hours.
- `TRACKER_BACKUP_KEEP=28` — retain the latest 28 timestamped backups.
- `TRACKER_EXPORT_PATH=/data/tracker_results.csv` — optional persistent CSV output path.

Existing scanner filter variables (defaults shown):

- `MIN_MC=30000`
- `MAX_MC=500000`
- `MIN_LIQUIDITY=6000`
- `MIN_VOLUME=5000`
- `MIN_VOL_5M=3000`
- `MIN_SCORE=80`
- `MIN_BUY_PRESSURE=60`
- `MIN_MOMENTUM=10`
- `POLL_SECONDS=120`

Do not add a Birdeye key for this version; the scanner's current market-data source is DexScreener.

## Data and evidence limitations

- DexScreener supplies market data and token metadata.
- Public project-site descriptions and Reddit public search are the free v1 narrative/attention evidence adapters. No paid X API is used.
- These are heuristic public signals, not proof of organic engagement or a guarantee of token quality.
- Tracker records reported DexScreener `marketCap` only; it never substitutes FDV for tracker market cap.
- Market-cap peaks are sampled at the configured interval; brief moves between polls can be missed.
- The tracker queue substantially improves restart recovery, but there is a narrow gap between Telegram confirming an alert and the subsequent durable queue write. Database failure in that interval can leave an alert uncaptured by the tracker.
- Milestone notifications use an at-least-once outbox, so a rare duplicate is possible if the process crashes after Telegram accepts a message but before the database records delivery.

## Tests

```bash
python -m compileall -q bot.py tracker tests
python -m unittest discover -s tests -v
```

## Production preflight

After the host's real secrets and persistent mounts are configured, run inside the deployment container:

```bash
python -m tracker.preflight
```

It checks Deplexo's persistent `/data` mount (or explicitly configured storage paths), write access, SQLite integrity, a temporary online-backup write, Telegram bot authentication and chat access, DexScreener, and Reddit. It sends no Telegram messages and does not print credentials. A passing GitHub Actions test run is not a substitute for this host-side check.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the go-live checklist and rollback procedure.
