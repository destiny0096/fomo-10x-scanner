# Deployment and Go-Live Checklist

This document is intentionally strict. A green unit-test run does not prove that a hosting provider has durable storage or valid secrets.

## 1. Keep the production scanner safe

- Keep Deplexo OFF while preparing this release.
- Do not run the new branch against the production Telegram chat during preflight.
- Do not merge `feature/fomo-tracker-test-4` into `main` until the owner reviews and approves the release.
- Do not change scanner thresholds as part of tracker deployment.
- Keep the current production deployment/configuration available for rollback.

## 2. Configure the hosting provider

In the existing Deplexo application (do not create a replacement app):

- Repository: `destiny0096/fomo-10x-scanner`.
- Branch to deploy only after approval: `main` after the feature branch is reviewed and merged.
- Root directory: `./`.
- Start command: `python bot.py`.
- Health port: `3000` (or the provider's injected `PORT`).
- Install dependencies from `requirements.txt`.

Required secret variables (set through the provider UI, never in GitHub files):

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Required storage configuration (simple Deplexo setup):

- Use the existing persistent app volume mounted at `/data`.
- The app automatically uses `/data/tracker_data.db` when the persistent `/data` mount is available.
- Backups automatically go to `/data/tracker_backups` beside the database.
- No additional tracker storage environment variables are required for this setup. You may set `TRACKER_DB_PATH` and `TRACKER_BACKUP_DIR` explicitly, but leave `TRACKER_REQUIRE_SEPARATE_BACKUP_VOLUME` unset.
- The tracker creates a verified SQLite backup every six hours and keeps the latest 28 local backup files.
- Important limitation: local backups help with some database-level problems, but they cannot recover data if the entire Deplexo volume is deleted or lost. An off-site backup can be added later; it is not required to complete this tracker build.

Recommended variables:

```text
TRACKER_MC_POLL_SECONDS=300
TRACKER_BACKUP_INTERVAL_SECONDS=21600
TRACKER_BACKUP_KEEP=28
TRACKER_EXPORT_PATH=/data/tracker_results.csv
```

## 3. Run host-side preflight

After the existing persistent volume and real Telegram secrets are configured, run this command in the app/container shell:

```bash
python -m tracker.preflight
```

Expected checks:

- Deplexo's `/data` mount (or explicitly configured paths) is present and writable;
- local database and backup paths are writable; a same-volume warning is expected with the simple setup;
- at least 100 MB is free on the database filesystem;
- SQLite opens and passes `PRAGMA integrity_check`;
- a temporary SQLite online backup can be written and validated;
- Telegram bot authentication succeeds;
- Telegram can resolve/access the configured destination chat;
- DexScreener public API responds;
- Reddit public search responds.

The command uses Telegram read-only endpoints only. It does not send a message or expose the bot token. Any FAIL is a go-live blocker. A Reddit outage may be transient; retry later rather than weakening the attention qualification gate.

## 4. Controlled live smoke test (requires explicit owner approval)

After preflight passes and a deployment is explicitly approved:

1. Deploy during a period when the owner can monitor the service.
2. Confirm startup logs show the health server, pending queue recovery, and market-cap monitor.
3. Confirm `/health` returns HTTP 200. This proves liveness only.
4. Send a separately approved test message to the intended Telegram destination using the existing bot, or verify an ordinary scanner alert when one naturally occurs. Do not manufacture a token alert or relax scanner filters just to force a test.
5. Confirm one real scanner alert is followed by a durable candidate-queue row and tracker evidence evaluation in logs/database.
6. Confirm a qualified candidate is inserted only when both narrative and attention evidence pass. A rejected token should remain out of the 100-token cohort.
7. Confirm market-cap updates use reported `marketCap`, not FDV.
8. Confirm a timestamped backup appears under `/data/tracker_backups` and passes SQLite integrity validation.
9. Confirm no unexpected repeated Telegram alerts, restart loops, or database errors.

Do not insert fake tokens into the production 100-token cohort. Use a separate staging database/chat for destructive or synthetic end-to-end tests.

## 5. Backup and restore drill

Before relying on the tracker:

- Create a backup with `python -m tracker.backup`.
- Verify the backup exists under `/data/tracker_backups`.
- Verify it opens and passes `PRAGMA integrity_check`.
- Practice restore against a separate test database path, never the live production database.
- For a real restore, stop the bot first and follow `python -m tracker.restore` instructions. Never restore over an active SQLite database.

Backups kept only on the same app volume are not disaster recovery; off-site backup can be added later.

## 6. Rollback

If the new release causes scanner or tracker instability:

1. Stop the new deployment.
2. Keep the persistent database and local backups untouched.
3. Revert the app to the previously working scanner commit/configuration.
4. Do not delete SQLite `-wal` or `-shm` files manually.
5. Inspect logs and database integrity before attempting another deployment.
6. Restore tracker data only to a stopped app and only from a validated backup.

## Go-live blockers that require provider/user action

The GitHub-connected development workflow cannot inspect Deplexo's private app settings, create/mount Deplexo volumes, read its secret values, or run commands inside its container. Therefore the following cannot be truthfully completed from GitHub:

- confirm the actual Deplexo persistent mount and filesystem;
- configure off-site backup storage (optional for this initial build);
- confirm the production Telegram secrets are present and valid;
- run the host-side preflight against those real settings;
- verify a real deployment and live Telegram delivery.

Do not mark production ready until these checks have been completed and reviewed.
