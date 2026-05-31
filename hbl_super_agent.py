import requests
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = "8874026729:AAEgzZr0UslgaKGdPiUjZMONNuFCKL-pqsY"
CHAT_ID   = "1358803794"
SYMBOL    = "HBLENGINE.NS"

# ક્વોન્ટિટી સેટિંગ્સ
QTY_5M   = 500
QTY_15M  = 300
QTY_30M  = 250
QTY_1H   = 200
ROUTINE_PRE_VOLUME = 5000  # પ્રી-માર્કેટ બેન્ચમાર્ક વોલ્યુમ

IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)

def get_market_session():
    n = now_ist()
    if n.weekday() >= 5: return "CLOSED"
    mins = n.hour * 60 + n.minute
    
    if 540 <= mins < 555:    # 9:00 AM થી 9:15 AM
        return "PRE_MARKET"
    elif 555 <= mins <= 930:  # 9:15 AM થી 3:30 PM
        return "LIVE_MARKET"
    elif 930 < mins <= 960:   # 3:30 PM થી 4:00 PM (Closing matching & data freeze)
        return "AFTER_MARKET"
    return "NIGHT_CLOSED"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=15)
        print("Telegram Sent:", r.json().get("ok"))
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_google_news():
    url = f"https://news.google.com/rss/search?q=HBL+Power&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:1]:
            title = item.find("title").text.split(" - ")[0]
            link = item.find("link").text
            return f"\n\n📰 <b>તાજા સમાચાર:</b> <a href='{link}'>{title}</a>"
    except:
        pass
    return ""

def fetch_yahoo_data(interval, timeframe_range, include_prepost=False):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?interval={interval}&range={timeframe_range}&includePrePost={'true' if include_prepost else 'false'}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        res = r.json()["chart"]["result"][0]
        closes = [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
        highs  = [x for x in res["indicators"]["quote"][0]["high"] if x is not None]
        lows   = [x for x in res["indicators"]["quote"][0]["low"] if x is not None]
        volumes = [x for x in res["indicators"]["quote"][0]["volume"] if x is not None]
        price = res["meta"]["regularMarketPrice"]
        prev_close = res["meta"].get("previousClose", price)
        pre_price = res["meta"].get("preMarketPrice", price)
        return round(price, 2), closes, highs, lows, volumes, round(prev_close, 2), round(pre_price, 2)
    except:
        return None, [], [], [], [], None, None

def calc_ema(data, p):
    if len(data) < p: return None
    k = 2/(p+1); e = sum(data[:p])/p
    for v in data[p:]: e = v*k + e*(1-k)
    return round(e, 2)

def calc_rsi(data, p=14):
    if len(data) < p+1: return "N/A"
    g = sum(max(data[i]-data[i-1],0) for i in range(len(data)-p,len(data)))
    l = sum(max(data[i-1]-data[i],0) for i in range(len(data)-p,len(data)))
    ag, al = g/p, l/p
    return round(100 - 100/(1+ag/al), 1) if al else 100.0

# SESSION CHECKER
session = get_market_session()
if session in ["CLOSED", "NIGHT_CLOSED"]:
    print("માર્કેટ બંધ છે. સ્કેનિંગ સ્કીપ કર્યું.")
    exit(0)

news_update = fetch_google_news()

# =========================================================
# ૧. ☀️ PRE-MARKET SESSION (સવારે ૯:૦૫ થી ૯:૧૦)
# =========================================================
if session == "PRE_MARKET":
    price, closes, highs, lows, volumes, prev_close, pre_price = fetch_yahoo_data("1m", "1d", include_prepost=True)
    if price:
        pre_market_vol = sum([v for v in volumes if v is not None])
        vol_multiple = round(pre_market_vol / ROUTINE_PRE_VOLUME, 1) if pre_market_vol else 0
        
        change = round(pre_price - prev_close, 2)
        p_change = round((change / prev_close) * 100, 2)
        direction = "🚀 GAP-UP" if change >= 0 else "⚠️ GAP-DOWN"
        
        projection = "⚖️ ફ્લેટ ઓપનિંગ સંકેત."
        if p_change >= 0.6: projection = "🔥 <b>Strong Bullish Open!</b> પ્રી-વોલ્યુમ મોટો ધડાકો બતાવે છે, આજે ઇન્ટ્રાડે મુવમેન્ટ ફાસ્ટ આવી શકે."
        elif p_change <= -0.6: projection = "📉 <b>Bearish Open!</b> શરૂઆતમાં સેલિંગ પ્રેશર રહી શકે છે."

        msg_pre = f"""☀️ <b>HBL PRE-MARKET OPENING REPORT</b>

📊 <b>Pre-Open Price:</b> ₹{pre_price}
🔄 <b>Prev Close:</b> ₹{prev_close}
📈 <b>Expected Opening:</b> {direction} ({change:+} | {p_change:+}%)
📊 <b>Pre-Market Volume:</b> {pre_market_vol:,} ({vol_multiple}x Routine)

------------------------------------------
{projection}{news_update}
------------------------------------------
⏰ {now_ist().strftime('%d %b %Y %H:%M IST')}"""
        send_telegram(msg_pre)
    exit(0)

# =========================================================
# ૨. 🌗 AFTER-MARKET SESSION (બપોરે ૩:૩૫ વાગ્યે ફાઇનલ અપડેટ)
# =========================================================
if session == "AFTER_MARKET":
    price, closes, highs, lows, volumes, prev_close, _ = fetch_yahoo_data("1d", "5d")
    if price:
        day_high = max(highs[-1:]) if highs else price
        day_low = min(lows[-1:]) if lows else price
        change = round(price - prev_close, 2)
        p_change = round((change / prev_close) * 100, 2)
        status_emoji = "🎉🟢" if change >= 0 else "⚠️🔴"
        
        msg_post = f"""{status_emoji} <b>HBL AFTER-MARKET CLOSING REPORT</b>

🏁 <b>Final Closing Price:</b> ₹{price}
📈 <b>આજનો આખો વધઘટ:</b> {change:+} ({p_change:+}%)
🔼 <b>Day High:</b> ₹{day_high} | 🔽 <b>Day Low:</b> ₹{day_low}
📊 <b>Total Day Volume:</b> {int(volumes[-1]):,} shares

💡 <b>Closing Note:</b> HBL એ આજે પોતાનું ટ્રેડિંગ સેશન પૂરું કર્યું છે. ઇન્ડિકેટર્સ અને સેટઅપ હવે આવતીકાલના પ્રી-માર્કેટ માટે બેકગ્રાઉન્ડમાં મોનિટર થશે.{news_update}
⏰ {now_ist().strftime('%d %b %Y %H:%M IST')}"""
        send_telegram(msg_post)
    exit(0)

# =========================================================
# ૩. 📈 LIVE MARKET MULTI-TIMEFRAME LOGIC (૯:૧૫ થી ૩:૩૦)
# =========================================================
alert_sent = False

# A. 1 કલાક ફ્રેમ સ્કેન (₹50 Target / ₹20 SL)
price, closes, highs, volumes, _ , _ = fetch_yahoo_data("60m", "1mo")
if price and len(closes) >= 22 and not alert_sent:
    e9 = calc_ema(closes, 9); e21 = calc_ema(closes, 21); rsi = calc_rsi(closes)
    if e9 and e21 and (e9 > e21) and (rsi != "N/A" and rsi >= 55):
        send_telegram(f"🚀 <b>HBL 1-HOUR POSITIONAL ALERT!</b>\n\n💰 <b>Price:</b> ₹{price} | RSI: {rsi}\n✅ <b>Target (+₹50):</b> ₹{round(price+50,2)}\n🛑 <b>Stop Loss (-₹20):</b> ₹{round(price-20,2)}\n⏳ <b>Prediction:</b> 1 to 2 Weeks Hold (Qty: {QTY_1H}){news_update}")
        alert_sent = True

# B. 30 મિનિટ ફ્રેમ સ્કેન (₹30 Target / ₹15 SL)
if not alert_sent:
    price, closes, highs, volumes, _ , _ = fetch_yahoo_data("30m", "1mo")
    if price and len(closes) >= 22:
        e9 = calc_ema(closes, 9); e21 = calc_ema(closes, 21); rsi = calc_rsi(closes)
        if e9 and e21 and (e9 > e21) and (rsi != "N/A" and rsi >= 53):
            send_telegram(f"💎 <b>HBL 30-MIN MEDIUM SWING!</b>\n\n💰 <b>Price:</b> ₹{price} | RSI: {rsi}\n✅ <b>Target (+₹30):</b> ₹{round(price+30,2)}\n🛑 <b>Stop Loss (-₹15):</b> ₹{round(price-15,2)}\n⏳ <b>Prediction:</b> 4 to 5 Days Hold (Qty: {QTY_30M}){news_update}")
            alert_sent = True

# C. 15 મિનિટ ફ્રેમ સ્કેન (₹20 Target / ₹10 SL)
if not alert_sent:
    price, closes, highs, volumes, _ , _ = fetch_yahoo_data("15m", "7d")
    if price and len(closes) >= 22:
        e9 = calc_ema(closes, 9); e21 = calc_ema(closes, 21); rsi = calc_rsi(closes)
        if e9 and e21 and (e9 > e21) and (rsi != "N/A" and rsi >= 52):
            send_telegram(f"⚡ <b>HBL 15-MIN SHORT SWING!</b>\n\n💰 <b>Price:</b> ₹{price} | RSI: {rsi}\n✅ <b>Target (+₹20):</b> ₹{round(price+20,2)}\n🛑 <b>Stop Loss (-₹10):</b> ₹{round(price-10,2)}\n⏳ <b>Prediction:</b> 2 to 3 Days Hold (Qty: {QTY_15M}){news_update}")
            alert_sent = True

# D. 5 મિનિટ ફ્રેમ સ્કેન (₹5 Intraday Target / ₹5 SL)
if not alert_sent:
    price, closes, highs, volumes, _ , _ = fetch_yahoo_data("5m", "2d")
    if price and len(closes) >= 22:
        rsi = calc_rsi(closes); last_5_high = max(highs[-6:-1]) if highs else price
        avg_vol = sum(volumes[-6:-1])/5 if len(volumes)>=6 else 0
        vol_x = round(volumes[-1]/avg_vol, 1) if avg_vol else 0
        
        if (price > last_5_high) and (rsi != "N/A" and rsi >= 50) and (vol_x >= 1.5):
            send_telegram(f"🟢 <b>HBL 5-MIN INTRADAY BREAKOUT!</b>\n\n💰 <b>Price:</b> ₹{price} | Vol: {vol_x}x\n✅ <b>Target (+₹5):</b> ₹{round(price+5,2)}\n🛑 <b>Stop Loss (-₹5):</b> ₹{round(price-5,2)}\n⏳ <b>Prediction:</b> Intraday MIS (Qty: {QTY_5M}){news_update}")
            alert_sent = True

if not alert_sent:
    print("HBL માં અત્યારે કોઈ ટાઈમફ્રેમમાં સિગ્નલ સેટ થતું નથી. વેઇટિંગ...")
