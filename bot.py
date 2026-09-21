import os
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
from security_test import check_security, security_summary

TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

MIN_MC = float(os.getenv('MIN_MC', '50000'))
MAX_MC = float(os.getenv('MAX_MC', '500000'))
MIN_LIQ = float(os.getenv('MIN_LIQUIDITY', '20000'))
MIN_VOL = float(os.getenv('MIN_VOLUME', '50000'))
MIN_SCORE = int(os.getenv('MIN_SCORE', '80'))
POLL_SECONDS = int(os.getenv('POLL_SECONDS', '120'))

BASE = 'https://api.dexscreener.com'
HEAD = {}

seen = set()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)


async def get(session, path, params=None):
    async with session.get(
        BASE + path,
        headers=HEAD,
        params=params,
        timeout=20
    ) as r:
        data = await r.json()

        if r.status >= 400:
            raise RuntimeError(f'{r.status}: {data}')

        return data


async def tg(session, text):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'

    async with session.post(
        url,
        json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'disable_web_page_preview': False
        },
        timeout=20
    ) as r:
        if r.status >= 400:
            raise RuntimeError(await r.text())


def money(x):
    x = float(x or 0)

    if x >= 1_000_000:
        return f'${x / 1e6:.2f}M'

    if x >= 1_000:
        return f'${x / 1e3:.1f}K'

    return f'${x:.0f}'


def score(pair):
    mc = float(pair.get('marketCap') or pair.get('fdv') or 0)

    liquidity_data = pair.get('liquidity') or {}
    liq = float(liquidity_data.get('usd') or 0)

    volume_data = pair.get('volume') or {}
    vol = float(volume_data.get('h24') or 0)

    s = 0
    why = []

    if MIN_MC <= mc <= MAX_MC:
        s += 25
        why.append('target MC')

    if liq >= MIN_LIQ:
        s += 25
        why.append('liquidity')

    if vol >= MIN_VOL:
        s += 25
        why.append('volume')

    txns = pair.get('txns') or {}
    h24 = txns.get('h24') or {}

    buys = int(h24.get('buys') or 0)
    sells = int(h24.get('sells') or 0)

    if buys >= 20:
        s += 10
        why.append('active trading')

    if buys > sells:
        s += 5
        why.append('buy pressure')

    return s, mc, liq, vol, why


def alert(pair, s, mc, liq, vol, why):
    base_token = pair.get('baseToken') or {}

    address = base_token.get('address') or ''
    name = base_token.get('name') or 'Unknown'
    symbol = base_token.get('symbol') or '?'

    created = pair.get('pairCreatedAt')
    age = 'unknown'

    if created:
        created_seconds = float(created) / 1000
        age_minutes = max(
            0,
            (datetime.now(timezone.utc).timestamp() - created_seconds) / 60
        )
        age = f'{age_minutes:.0f} min'

    dex_url = pair.get(
        'url',
        f'https://dexscreener.com/solana/{address}'
    )

    return (
        f'🚨 FOMO 10X WATCH ALERT\n\n'
        f'🪙 {name} (${symbol})\n'
        f'⛓️ Solana\n'
        f'⏱️ Pair age: {age}\n'
        f'💰 MC: {money(mc)}\n'
        f'💧 Liquidity: {money(liq)}\n'
        f'📊 24h Volume: {money(vol)}\n'
        f'⭐ Score: {s}/100\n'
        f'📌 Signals: {", ".join(why) or "initial screen"}\n\n'
        f'⚠️ Screening only — NOT a 10× guarantee.\n\n'
        f'CA: {address}\n'
        f'🔗 {dex_url}'
    )


async def scan(session):
    profiles = await get(
        session,
        '/token-profiles/latest/v1'
    )

    if not isinstance(profiles, list):
        logging.warning('Unexpected token profile response')
        return

    solana_tokens = []

    for token in profiles:
        if token.get('chainId') != 'solana':
            continue

        address = token.get('tokenAddress')

        if not address:
            continue

        if address in seen:
            continue

        solana_tokens.append(address)

    if not solana_tokens:
        logging.info('No new Solana candidates found')
        return

    solana_tokens = solana_tokens[:30]

    for address in solana_tokens:
        seen.add(address)

    address_list = ','.join(solana_tokens)

    pairs = await get(
        session,
        f'/tokens/v1/solana/{address_list}'
    )

    if not isinstance(pairs, list):
        logging.warning('Unexpected token pair response')
        return

    best_pairs = {}

    for pair in pairs:
        if pair.get('chainId') != 'solana':
            continue

        token = pair.get('baseToken') or {}
        address = token.get('address')

        if not address:
            continue

        liquidity_data = pair.get('liquidity') or {}
        liquidity = float(liquidity_data.get('usd') or 0)

        current = best_pairs.get(address)

        if current is None:
            best_pairs[address] = pair
        else:
            current_liquidity = float(
                (current.get('liquidity') or {}).get('usd') or 0
            )

            if liquidity > current_liquidity:
                best_pairs[address] = pair

    for pair in best_pairs.values():
        s, mc, liq, vol, why = score(pair)

        if (
            MIN_MC <= mc <= MAX_MC
            and liq >= MIN_LIQ
            and vol >= MIN_VOL
            and s >= MIN_SCORE
        ):
            security = await check_security(session, address)

await tg(
    session,
    alert(
        pair,
        s,
        mc,
        liq,
        vol,
        why
    ) + f'\n\n🛡️ SECURITY\n{security_summary(security)}'
)
            )

            token = pair.get('baseToken') or {}

            logging.info(
                'ALERT %s %s score=%s',
                token.get('symbol'),
                token.get('address'),
                s
            )


async def main():
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await scan(session)

            except Exception:
                logging.exception('scan failed')

            await asyncio.sleep(POLL_SECONDS)


if __name__ == '__main__':
    asyncio.run(main())


    
