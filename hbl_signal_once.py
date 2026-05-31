import requests, os, pytz
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
SYMBOL    = "HBLENGINE.NS"
QTY       = 500
MOVE      = 5

IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

def is_market_open():
    n = now_ist()
    if n.weekday() >= 5: return False
    mins = n.hour * 60 + n.minute
    return 930 <= mins <= 1520

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print("Telegram:", r.json().get("ok"))
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_data():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?interval=5m&range=2d"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res = r.json()["chart"]["result"][0]
        closes  = [x for x in res["indicators"]["quote"][0]["close"]  if x is not None]
        volumes = [x for x in res["indicators"]["quote"][0]["volume"] if x is not None]
        price   = res["meta"]["regularMarketPrice"]
        return round(price, 2), closes, volumes
    except Exception as e:
        print(f"Fetch error: {e}"); return None, [], []

def calc_ema(data, p):
    if len(data) < p: return None
    k = 2/(p+1); e = sum(data[:p])/p
    for v in data[p:]: e = v*k + e*(1-k)
    return round(e, 2)

def calc_rsi(data, p=14):
    if len(data) < p+1: return None
    g = sum(max(data[i]-data[i-1],0) for i in range(len(data)-p,len(data)))
    l = sum(max(data[i-1]-data[i],0) for i in range(len(data)-p,len(data)))
    ag, al = g/p, l/p
    return round(100 - 100/(1+ag/al), 1) if al else 100.0

if not is_market_open():
    print(f"Market closed at {now_ist().strftime('%H:%M IST')}. Skipping.")
    exit(0)

price, closes, volumes = fetch_data()
if not price or len(closes) < 22:
    print("Not enough data."); exit(0)

ema9, ema21 = calc_ema(closes,9), calc_ema(closes,21)
rsi = calc_rsi(closes,14)
avg_vol = sum(volumes[-6:-1])/5 if len(volumes)>=6 else 0
vol_x = round(volumes[-1]/avg_vol,1) if avg_vol else 0

print(f"Price=Rs{price} EMA9={ema9} EMA21={ema21} RSI={rsi} Vol={vol_x}x")

if None in (ema9, ema21, rsi): exit(0)

buy  = ema9>ema21 and 45<=rsi<=65 and vol_x>=1.3 and price>ema9
sell = ema9<ema21 and 35<=rsi<=55 and vol_x>=1.3 and price<ema9

if not buy and not sell:
    print("Signal: WAIT"); exit(0)

sig = "BUY" if buy else "SELL"
t1  = round(price+(MOVE if buy else -MOVE), 2)
t2  = round(price+(MOVE*2 if buy else -MOVE*2), 2)
sl  = round(price+(-MOVE if buy else MOVE), 2)
emoji = "🟢📈" if buy else "🔴📉"

msg = f"""{emoji} <b>HBLENGINE {sig} SIGNAL!</b>

💰 <b>Price:</b> Rs{price}
📊 <b>EMA9:</b> {ema9} | <b>EMA21:</b> {ema21}
📉 <b>RSI:</b> {rsi} | <b>Vol:</b> {vol_x}x

🎯 <b>Entry:</b>    Rs{price}
✅ <b>Target 1:</b>  Rs{t1}  (+Rs{MOVE} = +Rs{QTY*MOVE:,})
✅ <b>Target 2:</b>  Rs{t2}  (+Rs{MOVE*2} = +Rs{QTY*MOVE*2:,})
🛑 <b>Stop Loss:</b> Rs{sl}  (-Rs{MOVE} = -Rs{QTY*MOVE:,})

Qty: {QTY} | R:R = 1:1 / 1:2
{now_ist().strftime('%d %b %Y  %H:%M IST')}

<i>3 confirmations — Execute trade!</i>"""

send_telegram(msg)
print(f"Alert sent: {sig}")
