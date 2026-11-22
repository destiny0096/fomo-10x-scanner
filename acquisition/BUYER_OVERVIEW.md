# FOMO 10X Scanner — Acquisition Opportunity

## Take ownership of an existing Solana token-discovery platform

FOMO 10X Scanner is a Python-based Solana token-discovery and Telegram-alert application built to help users identify and monitor emerging token opportunities through configurable market filters and automated evaluation checks.

The project brings together market data, token activity analysis, security checks, liquidity assessment, sell-route evaluation and Telegram notifications. It also includes a separate tracker component that provides a foundation for recording token cohorts and monitoring their market-cap performance.

**Asking price: USD 2,000**  
**Serious offers are welcome.**

## Why this project is interesting

- An existing codebase and working application structure to take ownership of.
- Automated Solana token discovery using DexScreener public market data.
- Configurable market filters for market cap, liquidity, volume, buy pressure and momentum.
- Separate modules for security, liquidity-pool and sell-route checks.
- Telegram alert delivery.
- A separate SQLite-backed tracking component with monitoring and reporting utilities.
- A clear foundation for further customization, new features and future development.

## Core scanner settings

The repository's documented default settings are:

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

These values can be adjusted through environment variables, allowing the new owner to tune the scanner to their preferred strategy and operating requirements.

## Included capabilities

- Solana token candidate discovery using DexScreener public data.
- Pair selection that prefers the most liquid Solana pair returned for a token.
- Market-cap, liquidity, volume, transaction-activity, buy-pressure and momentum scoring/filtering.
- Token security checks through a dedicated module.
- Liquidity-pool status checks through a dedicated module.
- Sell-route checks through a dedicated module.
- Telegram watch-alert delivery.
- Application health endpoint.
- Separate SQLite-backed tracker component with cohort limits, market-cap monitoring, reporting, backup and restore utilities.

## Technology

- Python
- aiohttp
- DexScreener public data
- Telegram Bot API
- SQLite
- Environment-based configuration

## Your project, your direction

The buyer receives an existing technology foundation that can be developed in whichever direction best matches their goals.

**You are free to edit, customize, extend or reorganize the code to suit your own requirements.** You can adjust scanner filters, refine evaluation logic, add data sources, change alert formats, improve the tracker, introduce new features or build a larger product around the existing foundation.

Whether you want to operate it as a personal token-discovery tool, develop it into a more advanced trading assistant or use the codebase as the starting point for a broader Solana product, the next development direction is yours.

## Deployment starting point

The repository includes deployment guidance with the following starting configuration:

- Start command: `python bot.py`
- Root directory: repository root
- Health port: `3000` (or the host-provided `PORT`)
- Telegram configuration: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

The new owner can connect their preferred hosting account, Telegram bot credentials and persistent storage, then configure the application for their own setup.

## Acquisition and handover

The acquisition is intended to transfer the agreed project code and assets to the buyer. The handover can cover repository access, project structure, configuration guidance and a walkthrough of the application.

The final agreement will specify the exact assets being transferred, any third-party components and their licences, deployment assistance, support period, and the treatment of hosting accounts, domains, credentials and existing tracker data. Personal hosting accounts and private credentials are not transferred by default.

## Build on what already exists

FOMO 10X Scanner offers a buyer the opportunity to take over an established project foundation and shape its next chapter. Explore the code, make it your own, and develop the features and workflow that fit your vision.
