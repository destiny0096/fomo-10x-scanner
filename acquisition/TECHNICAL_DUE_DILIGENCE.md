# FOMO 10X Scanner — Technical Due Diligence

This checklist separates repository evidence from checks that require the live hosting environment or seller records.

## Repository-backed facts

- Main application entry point: bot.py.
- Start command documented in README: python bot.py.
- Market-data base URL in source: DexScreener API.
- Telegram alert delivery uses the Telegram Bot API.
- Required runtime secrets are TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
- Python dependencies listed in requirements.txt: aiohttp>=3.9,<4 and solders>=0.21,<1.
- Scanner checks are imported from security_test.py, lp_test.py, and sell_route_test.py.
- Tracker code is maintained as a separate component under tracker/.
- README documents compile and unit-test commands.
- Deployment documentation explicitly requires host-side preflight and owner approval before production deployment.

## Required checks before public listing

- [ ] Run python -m compileall -q bot.py tracker tests.
- [ ] Run python -m unittest discover -s tests -v and retain the complete output.
- [ ] Review the current GitHub Actions run history and resolve any failed/cancelled release checks.
- [ ] Reconcile tracker qualification behavior across README, tracker documentation, and executable code; do not describe narrative/attention gates as active until verified in code and tests.
- [ ] Confirm whether the tracker feature branch is present and identify the exact commit intended for handover.
- [ ] Review third-party dependency licences and any external service terms.
- [ ] Scan repository history and current files for accidentally committed credentials.
- [ ] Create and verify an independent source archive/backup.
- [ ] Export and integrity-check tracker data if the seller intends to include it.
- [ ] Confirm whether the live host has a persistent /data mount and whether the database actually resides there.
- [ ] Run python -m tracker.preflight inside the configured host after the owner's secrets and storage are present.
- [ ] Complete a controlled live smoke test only with explicit owner approval.

## Known operational limitations documented by the project

- The HTTP health endpoint confirms process liveness; it does not prove Telegram, DexScreener, Reddit, or storage health.
- The tracker requires persistent storage to preserve its SQLite records across host restarts.
- Local backups on the same host volume do not protect against loss of the entire volume.
- Tracker market-cap peaks are sampled on a polling interval; brief moves between samples can be missed.
- The tracker documentation describes a narrow failure window between successful Telegram alert delivery and durable queue insertion.
- The deployment checklist says production readiness cannot be established from GitHub alone; host-side configuration and preflight are required.

## Handover boundaries

Do not transfer personal GitHub, Deplexo, Telegram, or other service-account credentials. A buyer should receive agreed source assets and deployment instructions, then configure their own accounts and secrets. If a hosting application or domain is to be transferred, confirm that the provider supports it and document the exact assets separately.

## Release decision

Do not label the application production-verified or advertise a completed 100-token tracker report until the checks above have evidence attached. The seller should approve the final handover scope and acquisition agreement before any ownership transfer.
