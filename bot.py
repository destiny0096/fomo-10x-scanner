import os, asyncio, logging
from datetime import datetime, timezone
import aiohttp

BIRDEYE_API_KEY=os.environ['BIRDEYE_API_KEY']
TELEGRAM_BOT_TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID=os.environ['TELEGRAM_CHAT_ID']
MIN_MC=float(os.getenv('MIN_MC','50000')); MAX_MC=float(os.getenv('MAX_MC','500000'))
MIN_LIQ=float(os.getenv('MIN_LIQUIDITY','20000')); MIN_VOL=float(os.getenv('MIN_VOLUME','50000'))
MIN_SCORE=int(os.getenv('MIN_SCORE','80')); POLL_SECONDS=int(os.getenv('POLL_SECONDS','120'))
BASE='https://public-api.birdeye.so'; HEAD={'X-API-KEY':BIRDEYE_API_KEY,'x-chain':'solana'}
seen=set(); logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

async def get(session,path,params=None):
    async with session.get(BASE+path,headers=HEAD,params=params,timeout=20) as r:
        data=await r.json()
        if r.status>=400 or not data.get('success',False): raise RuntimeError(f'{r.status}: {data}')
        return data.get('data') or {}

async def tg(session,text):
    url=f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    async with session.post(url,json={'chat_id':TELEGRAM_CHAT_ID,'text':text,'disable_web_page_preview':False},timeout=20) as r:
        if r.status>=400: raise RuntimeError(await r.text())

def money(x):
    x=float(x or 0)
    return f'${x/1e6:.2f}M' if x>=1e6 else f'${x/1e3:.1f}K' if x>=1e3 else f'${x:.0f}'

def get_items(d):
    if isinstance(d,list): return d
    for k in ('items','tokens','data'):
        if isinstance(d.get(k),list): return d[k]
    return []

def score(m):
    mc=float(m.get('market_cap') or m.get('marketCap') or m.get('mc') or 0)
    liq=float(m.get('liquidity') or 0); vol=float(m.get('volume_24h_usd') or m.get('v24hUSD') or m.get('volume24h') or 0)
    s=0; why=[]
    if MIN_MC<=mc<=MAX_MC: s+=25; why.append('target MC')
    if liq>=MIN_LIQ: s+=25; why.append('liquidity')
    if vol>=MIN_VOL: s+=25; why.append('volume')
    holders=m.get('holder') or m.get('holders') or m.get('holders_count')
    if holders is not None and float(holders)>=100: s+=10; why.append('holders')
    ch=m.get('price_change_24h_percent') or m.get('priceChange24hPercent')
    if ch is not None and float(ch)>0: s+=5; why.append('momentum')
    return s,mc,liq,vol,why

def alert(t,m,s,mc,liq,vol,why):
    a=t.get('address') or m.get('address') or ''
    name=t.get('name') or m.get('name') or 'Unknown'; sym=t.get('symbol') or m.get('symbol') or '?'
    age='unknown'
    ts=t.get('liquidityAddedAt') or t.get('liquidity_added_at')
    if ts:
        age=f"{max(0,(datetime.now(timezone.utc).timestamp()-float(ts))/60):.0f} min"
    return (f"🚨 10X WATCH ALERT\n\n🪙 {name} (${sym})\n⛓️ Solana\n⏱️ Age: {age}\n💰 MC: {money(mc)}\n💧 Liquidity: {money(liq)}\n📊 Volume: {money(vol)}\n⭐ Score: {s}/100\n📌 Signals: {', '.join(why) or 'initial screen'}\n\n⚠️ HIGH RISK — this is a screening score, NOT a 10× guarantee.\n\nCA: {a}\n🔗 https://dexscreener.com/solana/{a}")

async def scan(session):
    d=await get(session,'/defi/v2/tokens/new_listing',{'limit':20,'meme_platform_enabled':'true'})
    toks=get_items(d)
    fresh=[t for t in toks if (t.get('address') or t.get('tokenAddress')) and (t.get('address') or t.get('tokenAddress')) not in seen]
    if not fresh: return 
    for t in fresh:
        seen.add(t.get('address') or t.get('tokenAddress'))

    addrs=[t.get('address') or t.get('tokenAddress') for t in fresh][:20]

    markets=[]
    for a in addrs:
        m=await get(session,'/defi/v3/token/market-data',{'address':a,'ui_amount_mode':'scaled'})
        markets.append(m)

    by={m.get('address'):m for m in markets if m.get('address')}

    for t in fresh:
        a=t.get('address') or t.get('tokenAddress')
        m=by.get(a,{**t,'address':a})
        s,mc,liq,vol,why=score(m)
        if MIN_MC<=mc<=MAX_MC and liq>=MIN_LIQ and vol>=MIN_VOL and s>=MIN_SCORE:
            await tg(session,alert(t,m,s,mc,liq,vol,why))
            logging.info('alert %s %s',t.get('symbol'),a)

async def main():
    async with aiohttp.ClientSession() as session:
        while True:
            try: await scan(session)
            except Exception: logging.exception('scan failed')
            await asyncio.sleep(POLL_SECONDS)

if __name__=='__main__': asyncio.run(main())
