# FOMO 10X Scanner — Buyer Overview

## Acquisition opportunity

FOMO 10X Scanner is an existing Solana token-discovery and Telegram-alert application. It combines DexScreener market data with configurable market filters, token/security checks, liquidity assessment, and sell-route evaluation. The repository also contains a separate performance-tracking component.

**Proposed asking price: USD 2,000**  
**Negotiation:** Open to serious, qualified buyers.

This is the seller's asking price, not an independently appraised market value.

## What the application is designed to do

The scanner monitors Solana token/pair discovery data, evaluates candidates against configurable market conditions, and sends Telegram watch alerts when the configured checks pass.

The current documented default filters are:

| Setting | Default |
|---|---:|
| Minimum market cap | $30,000 |
| Maximum market cap | $500,000 |
| Minimum liquidity | $6,000 |
| Minimum 24-hour volume | $5,000 |
| Minimum 5-minute volume | $3,000 |
| Minimum score | 80 |
| Minimum buy pressure | 60% |
| Minimum 5-minute momentum | 10% |
| Poll interval | 120 seconds |

Values are configurable through environment variables. These are repository defaults; a buyer should confirm the deployed configuration before operation.

## Included capabilities documented in the codebase

- Solana token candidate discovery using DexScreener public data.
- Pair selection that prefers the most liquid Solana pair returned for a token.
- Market-cap, liquidity, volume, transaction-activity, buy-pressure and momentum scoring/filtering.
- Security checks through the separate security-check module.
- Liquidity-pool status checks through the LP-check module.
- Sell-route checks through the sell-route module.
- Telegram watch-alert delivery.
- Health endpoint on the configured application port.
- A separate SQLite-backed tracker component with cohort limits, market-cap monitoring, reporting, backup and restore utilities.

## Technical foundation

- Python application.
- aiohttp HTTP client and health server.
- DexScreener as the documented market-data source.
- Telegram Bot API for alerts.
- SQLite for tracker persistence.
- Environment-based configuration; credentials are not intended to be committed to source control.

## Deployment starting point

The repository documents the following host configuration:

- Start command: `python bot.py`
- Root directory: repository root
- Health port: `3000` (or the host-provided `PORT`)
- Required secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

Production deployment requires the buyer's own hosting account, Telegram bot credentials, and persistent storage if tracker records are to survive restarts.

## What a buyer can do next

A buyer can review the source, configure their own Telegram destination and hosting, tune the filters, extend the evaluation modules, and continue development of the tracker.

## Acquisition scope

The final purchase agreement should explicitly identify the repository/code and other assets being transferred, any third-party components and their licences, deployment assistance, support period, and the treatment of existing hosting accounts, domains, credentials, and stored tracker data. Personal hosting accounts and secrets are not included by default.

## Verification status

This overview describes capabilities documented in the repository. It is not a claim that the production Deplexo deployment is currently running or that every external integration has passed a live production check. The deployment preflight and release checklist must be completed before the product is advertised as production-verified.
