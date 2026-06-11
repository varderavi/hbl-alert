import requests
import pytz
import xml.etree.ElementTree as ET
import timeimport os, asyncio, aiohttp, logging
from datetime import datetime
from flask import Flask, jsonify
from dotenv import load_dotenv

# Load secrets
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

# Logging setup
logging.basicConfig(filename="bot.log", level=logging.INFO)

# Flask dashboard
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify({"server": "running", "time": datetime.now().strftime("%H:%M:%S")})

# Async fetch
async def fetch_data(session, symbol, interval="5m"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range=1d"
    try:
        async with session.get(url) as r:
            res = await r.json()
            price = res["chart"]["result"][0]["meta"]["regularMarketPrice"]
            return symbol, price
    except Exception as e:
        logging.error(f"Fetch error {symbol}: {e}")
        return symbol, None

async def fetch_multiple(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_data(session, s) for s in symbols]
        return await asyncio.gather(*tasks)

# Alert throttling
last_alert_time = {}

def can_alert(symbol, cooldown=600):
    now = datetime.now().timestamp()
    if symbol not in last_alert_time or now - last_alert_time[symbol] > cooldown:
        last_alert_time[symbol] = now
        return True
    return False

from datetime import datetime
import threading
import os
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

# ============================================
# CONFIGURATION & DICTIONARY
# ============================================
BOT_TOKEN = "8907497350:AAHSJtlYPpkW0FAobFDx9wgNcl6MO2jngU0"
CHAT_ID   = "1358803794"

IST = pytz.timezone("Asia/Kolkata")

user_status = {}
last_alert_sent = None  
processed_updates = set() 
pre_market_checked_today = False

POPULAR_STOCKS = {
    "HBL POWER": "HBLENGINE.NS", "HBL": "HBLENGINE.NS", "WIPRO": "WIPRO.NS", "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS", "INFY": "INFY.NS", "TATA MOTORS": "TATAMOTORS.NS", "TATAMOTORS": "TATAMOTORS.NS", "HDFC BANK": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS", "ICICI BANK": "ICICIBANK.NS", "SBI": "SBIN.NS", "SBIN": "SBIN.NS", "ITC": "ITC.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS", "AIRTEL": "BHARTIARTL.NS", "IRCTC": "IRCTC.NS", "ZOMATO": "ZOMATO.NS"
}

def now_ist():
    return datetime.now(IST)

def is_market_hours():
    n = now_ist()
    current_time = n.hour * 100 + n.minute
    return 915 <= current_time <= 1530

def get_range_for_interval(symbol, interval):
    # 🎯 GIFT NIFTY લગભગ ૨૦ કલાક ચાલે છે, એટલે એનો પૂરો ટ્રેન્ડ પકડવા માટે વધુ ડેટા રેન્જ સેટ કરી
    if symbol == "GIFTY=F":
        return "5d"
    if interval == "1m": return "1d"
    elif interval in ["5m", "15m", "30m"]: return "2d"
    elif interval in ["1h", "4h"]: return "1mo"
    elif interval == "1d": return "3mo"
    elif interval == "1wk": return "1y"
    return "2d"

def fetch_live_data(symbol, interval="5m"):
    timeframe_range = get_range_for_interval(symbol, interval)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={timeframe_range}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=7) 
        res = r.json()["chart"]["result"][0]
        closes = [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
        highs  = [x for x in res["indicators"]["quote"][0]["high"] if x is not None]
        lows   = [x for x in res["indicators"]["quote"][0]["low"] if x is not None]
        volumes = [x for x in res["indicators"]["quote"][0]["volume"] if x is not None]
        price = res["meta"]["regularMarketPrice"]
        prev_close = res["meta"].get("previousClose", price)
        
        if symbol == "HBLENGINE.NS": name = "HBL POWER"
        elif symbol == "GIFTY=F": name = "GIFT NIFTY (SGX)"
        elif symbol == "BTC-USD": name = "BITCOIN (BTC)"
        elif symbol == "^NSEI": name = "NIFTY 50"
        elif symbol == "^NSEBANK": name = "BANK NIFTY"
        elif symbol == "^BSESN": name = "SENSEX"
        elif symbol == "^NSMIDCP": name = "NIFTY MIDCAP 100"
        elif symbol == "^NSE91": name = "NIFTY NEXT 50"
        elif symbol.endswith(".NS"): name = symbol.replace(".NS", "")
        else: name = symbol
        
        recent_highs = highs[-50:] if len(highs) >= 50 else highs
        recent_lows = lows[-50:] if len(lows) >= 50 else lows
        recent_vols = volumes[-50:] if len(volumes) >= 50 else volumes
        
        tf_resistance = round(max(recent_highs), 2) if recent_highs else price
        tf_support = round(min(recent_lows), 2) if recent_lows else price
        
        current_vol = volumes[-1] if volumes else 0
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
        vol_ratio = round(current_vol / avg_vol, 1) if current_vol else 0
        
        return round(price, 2), closes, highs, lows, volumes, round(prev_close, 2), name, tf_resistance, tf_support, vol_ratio
    except:
        return None, [], [], [], [], None, symbol, None, None, 0

def calc_ema(data, p):
    if len(data) < p: return None
    k = 2 / (p + 1)
    e = sum(data[:p]) / p
    for v in data[p:]: e = v * k + e * (1 - k)
    return round(e, 2)

def calc_rsi_list(data, p=14):
    if len(data) < p + 1: return []
    rsi_history = []
    gains = []; losses = []
    for i in range(1, len(data)):
        diff = data[i] - data[i - 1]
        if diff > 0: gains.append(diff); losses.append(0.0)
        else: gains.append(0.0); losses.append(abs(diff))
    ag = sum(gains[:p]) / p
    al = sum(losses[:p]) / p
    rsi_history.append(100.0 - (100.0 / (1.0 + ag / al)) if al else 100.0)
    for i in range(p, len(gains)):
        ag = (ag * (p - 1) + gains[i]) / p
        al = (al * (p - 1) + losses[i]) / p
        rsi_history.append(100.0 - (100.0 / (1.0 + ag / al)) if al else 100.0)
    return rsi_history

def calc_supertrend(highs, lows, closes, p=10, mult=3):
    if len(closes) < p: return "NEUTRAL"
    tr_sum = 0
    for i in range(len(closes) - p, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_sum += tr
    atr = tr_sum / p
    mid = (highs[-1] + lows[-1]) / 2
    upper_band = mid + (mult * atr)
    lower_band = mid - (mult * atr)
    if closes[-1] > upper_band: return "BULLISH"
    elif closes[-1] < lower_band: return "BEARISH"
    return "NEUTRAL"

# ============================================
# 📊 REPORT GENERATOR ENGINE
# ============================================
def generate_advanced_report(symbol, interval="5m", is_crypto=False):
    price, closes, highs, lows, volumes, prev_close, name, tf_res, tf_sup, vol_ratio = fetch_live_data(symbol, interval)
    if not price: return None, None
    
    st_trend = calc_supertrend(highs, lows, closes)
    rsi_vals = calc_rsi_list(closes)
    rsi = round(rsi_vals[-1], 1) if rsi_vals else "N/A"
    ema9 = calc_ema(closes, 9)
    
    change = round(price - prev_close, 2)
    p_change = round((change / prev_close) * 100, 2)
    
    if is_crypto or symbol == "BTC-USD": sign = "$"
    elif symbol == "GIFTY=F": sign = " pts"
    else: sign = "₹"
    
    bullish_votes = 0; bearish_votes = 0
    if rsi != "N/A" and rsi >= 50: bullish_votes += 1
    elif rsi != "N/A" and rsi < 45: bearish_votes += 1
    if st_trend == "BULLISH": bullish_votes += 1
    elif st_trend == "BEARISH": bearish_votes += 1

    if bullish_votes >= 2: live_signal = "🟢 <b>BULLISH ZONE</b>"
    elif bearish_votes >= 2: live_signal = "🔴 <b>BEARISH ZONE</b>"
    else: live_signal = "⚖️ <b>SIDEWAYS</b>"
        
    emoji = "🟢📈" if change >= 0 else "🔴📉"
    
    price_str = f"{price:,}{sign}" if sign == " pts" else f"{sign}{price:,}"
    change_str = f"{change:+}{sign}" if sign == " pts" else f"{change:+}"
    
    # GIFT NIFTY માટે સ્પેશિયલ ૨૦ કલાક ઇન્ફો ટેક્સ્ટ
    extra_info = ""
    if symbol == "GIFTY=F":
        extra_info = "⏱️ <b>Market Status:</b> ~20 Hours Continuous Live Trading\n"
    
    text = f"""{emoji} <b>{name} LIVE REPORT ({interval})</b>

📢 <b>ALGO SIGNAL: {live_signal}</b>
------------------------------------------
💰 <b>Price:</b> {price_str} ({change_str} | {p_change:+}-%)
📈 <b>EMA9:</b> {ema9 or 'N/A'} | 📉 <b>RSI(14):</b> {rsi}
⚡ <b>Supertrend:</b> {st_trend}
{extra_info}------------------------------------------
📍 <b>CHART LEVELS ({interval}):</b>
🚧 <b>Resistance:</b> {tf_res}
🛡️ <b>Support:</b> {tf_sup}
📊 <b>Volume Ratio:</b> {vol_ratio}x
⏰ {now_ist().strftime('%H:%M:%S IST')}"""

    c_flag = "1" if (is_crypto or symbol == "BTC-USD") else ("2" if symbol == "GIFTY=F" else "0")

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Refresh", "callback_data": f"tf_{symbol}_{interval}_{c_flag}_5m"}],
            [{"text": "🔙 Back to Main Menu", "callback_data": "go_main"}]
        ]
    }
    return text, markup

# ============================================
# 🎯 ALL-EQUITY SEARCH ROUTING
# ============================================
def handle_search_text(user_text, current_chat_id):
    query = user_text.upper().strip()
    
    if query in POPULAR_STOCKS:
        symbol = POPULAR_STOCKS[query]
    elif query in ["GIFT NIFTY", "GIFTNIFTY", "SGX NIFTY", "SGXNIFTY"]:
        symbol = "GIFTY=F"
    elif query in ["BTC", "BITCOIN"]:
        symbol = "BTC-USD"
    else:
        symbol = f"{query}.NS"
        
    is_cry = (symbol == "BTC-USD")
    text, markup = generate_advanced_report(symbol, "5m", is_crypto=is_cry)
    
    if text:
        send_telegram_msg(text, current_chat_id, reply_markup=markup)
    else:
        text, markup = generate_advanced_report(query, "5m")
        if text:
            send_telegram_msg(text, current_chat_id, reply_markup=markup)
        else:
            fallback_markup = {"inline_keyboard": [[{"text": "🔙 Main Menu", "callback_data": "go_main"}]]}
            send_telegram_msg(f"❌ <b>સ્ટોક શોધવામાં ભૂલ!</b>\n\n'<b>{query}</b>' નામની કોઈ ઇક્વિટી મળી નથી. કૃપા કરીને સ્પેલિંગ ચેક કરો.", current_chat_id, reply_markup=fallback_markup)

def send_telegram_msg(text, current_chat_id, reply_markup=None):
    if not BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(current_chat_id), "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def send_main_menu(current_chat_id):
    markup = {
        "inline_keyboard": [
            [{"text": "🚀 GIFT NIFTY (SGX)", "callback_data": "m_gift"}, {"text": "🪙 Bitcoin (24/7)", "callback_data": "m_btc"}],
            [{"text": "⚡ HBL Power", "callback_data": "m_hbl"}, {"text": "📊 NIFTY 50", "callback_data": "m_nifty"}],
            [{"text": "📈 BANK NIFTY", "callback_data": "m_bnifty"}, {"text": "💎 SENSEX", "callback_data": "m_sensex"}],
            [{"text": "🚀 NIFTY NEXT 50", "callback_data": "m_next50"}, {"text": "🔥 MIDCAP 100", "callback_data": "m_midcap"}],
            [{"text": "🔍 Search Stock", "callback_data": "m_search"}]
        ]
    }
    send_telegram_msg("👋 <b>નમસ્તે રવિ ભાઈ! (Ultimate Pro Engine)</b>\n\nસર્વર ૨૪/૭ લાઈવ છે. રિપોર્ટ જોવા નીચે ક્લિક કરો અથવા કોઈપણ ઇક્વિટીનું નામ લખો:", current_chat_id, reply_markup=markup)

def handle_callback(callback_id, data, current_chat_id):
    text, markup = "", None
    if data == "m_hbl": text, markup = generate_advanced_report("HBLENGINE.NS", "5m")
    elif data == "m_gift": text, markup = generate_advanced_report("GIFTY=F", "5m")
    elif data == "m_btc": text, markup = generate_advanced_report("BTC-USD", "5m", is_crypto=True)
    elif data == "m_nifty": text, markup = generate_advanced_report("^NSEI", "5m")
    elif data == "m_bnifty": text, markup = generate_advanced_report("^NSEBANK", "5m")
    elif data == "m_sensex": text, markup = generate_advanced_report("^BSESN", "5m")
    elif data == "m_next50": text, markup = generate_advanced_report("^NSE91", "5m")
    elif data == "m_midcap": text, markup = generate_advanced_report("^NSMIDCP", "5m")
    elif data == "go_main": send_main_menu(current_chat_id); return
    elif data == "m_search":
        send_telegram_msg("🔍 <b>કોઈપણ શેર સર્ચ કરો:</b>\n\nનામ ટાઈપ કરીને મોકલો (e.g. IRCTC, ZOMATO):", current_chat_id)
        return
    elif data.startswith("tf_"):
        parts = data.split("_")
        if parts[3] == "1":
            text, markup = generate_advanced_report(parts[1], parts[4], is_crypto=True)
        elif parts[3] == "2":
            text, markup = generate_advanced_report(parts[1], parts[4], is_crypto=False)
        else:
            text, markup = generate_advanced_report(parts[1], parts[4], is_crypto=False)

    if text: send_telegram_msg(text, current_chat_id, reply_markup=markup)
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})

# ============================================
# ☀️ MORNING PRE-MARKET TIMING
# ============================================
def check_and_send_morning_report():
    g_price, _, _, _, _, g_close, _, _, _, _ = fetch_live_data("GIFTY=F", "5m")
    h_price, _, _, _, _, h_close, _, _, _, _ = fetch_live_data("HBLENGINE.NS", "5m")
    
    msg = f"☀️ <b>મોર્નિંગ માર્કેટ મૂડ રિપોર્ટ</b> ☀️\n--------------------------------------\n"
    if g_price and g_close:
        g_chg = round(((g_price - g_close)/g_close)*100, 2)
        msg += f"🚀 <b>GIFT NIFTY (SGX) પ્રી-ઓપન:</b> {g_price} pts ({g_chg:+}%)\n"
    if h_price and h_close:
        h_chg = round(((h_price - h_close)/h_close)*100, 2)
        msg += f"⚡ <b>HBL POWER પ્રી-ઓપન:</b> ₹{h_price} ({h_chg:+}%)\n"
        
    msg += f"\n🎯 <b>ટ્રેડિંગ પ્લાન:</b> ૦૯:૧૫ એ માર્કેટ ખુલતા જ આજના એલ્ગો ટ્રિગર્સ એક્ટિવ થઈ જશે."
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

def background_alerts_worker():
    global last_alert_sent, pre_market_checked_today
    while True:
        try:
            n = now_ist()
            current_time = n.hour * 100 + n.minute
            
            if 908 <= current_time <= 912:
                if not pre_market_checked_today:
                    check_and_send_morning_report()
                    pre_market_checked_today = True
            
            if current_time == 0:
                pre_market_checked_today = False
                
            if is_market_hours():
                res = fetch_live_data("HBLENGINE.NS", "5m")
                price = res[0]
                if price:
                    closes, highs, lows, volumes, _, _, tf_res, tf_sup, vol_ratio = res[1:]
                    st_trend = calc_supertrend(highs, lows, closes)
                    current_minute = n.strftime("%H:%M")
                    
                    if price >= tf_res and vol_ratio >= 1.3 and st_trend == "BULLISH":
                        if last_alert_sent != f"BUY_{current_minute}":
                            msg = f"🔥 <b>[ALGO-BOOST] HBL જેકપોટ બ્રેકઆઉટ ટ્રિગર!</b>\n\n💰 <b>Live Price:</b> ₹{price}\n📊 <b>Vol Jump:</b> {vol_ratio}x\n🚧 <b>Res Broken:</b> ₹{tf_res}\n\n🚨 <b>Action:</b> BUY LONG!"
                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            last_alert_sent = f"BUY_{current_minute}"
        except:
            pass
        time.sleep(15)

class FakeServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Engine is Live!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

# START THREADS
threading.Thread(target=lambda: HTTPServer(('', int(os.environ.get("PORT", 10000))), FakeServer).serve_forever(), daemon=True).start()
threading.Thread(target=background_alerts_worker, daemon=True).start()

# ============================================
# 🚀 MAIN LOOP (🎯 DUPLICATE LOCK FIX)
# ============================================
offset = 0
while True:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=1&limit=10"
        r = requests.get(url, timeout=5).json()
        if "result" in r:
            for update in r["result"]:
                u_id = update["update_id"]
                offset = u_id + 1
                
                if u_id in processed_updates: 
                    continue
                processed_updates.add(u_id)
                if len(processed_updates) > 500: processed_updates.clear()
                
                msg_obj = update.get("message")
                cb_obj = update.get("callback_query")
                
                if msg_obj and "text" in msg_obj:
                    dynamic_chat_id = msg_obj["chat"]["id"]
                    user_msg = msg_obj["text"]
                    if user_msg.lower() in ["hi", "hello", "menu", "/start"]:
                        send_main_menu(dynamic_chat_id)
                    else:
                        handle_search_text(user_msg, dynamic_chat_id)
                elif cb_obj:
                    dynamic_chat_id = cb_obj["message"]["chat"]["id"]
                    handle_callback(cb_obj["id"], cb_obj["data"], dynamic_chat_id)
        time.sleep(1)
    except:
        time.sleep(2)
