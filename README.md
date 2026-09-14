# Fomo 10X Coin Scanner

Starter Solana new-token alert scanner using Birdeye and Telegram. It discovers fresh meme-platform listings, batches market-data enrichment, applies configurable MC/liquidity/volume filters, scores candidates, and sends Telegram alerts.

Railway environment variables:
BIRDEYE_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_numeric_chat_id

Optional:
MIN_MC=50000
MAX_MC=500000
MIN_LIQUIDITY=20000
MIN_VOLUME=50000
MIN_SCORE=80
POLL_SECONDS=60

Start command: python bot.py

Important: This is an alerting/risk-screening tool, not a prediction engine. A score is not a guarantee of a 10x return.
