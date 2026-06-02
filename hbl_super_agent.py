import requests
import pytz
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import threading
import os
import difflib
from http.server import BaseHTTPRequestHandler, HTTPServer

# ============================================
# CONFIGURATION & DICTIONARY
# ============================================
BOT_TOKEN = "8874026729:AAEgzZr0UslgaKGdPiUjZMONNuFCKL-pqsY"
# 🎯 જેકપોટ બ્રેકઆઉટના ઓટોમેટિક રિયલ-ટાઇમ એલર્ટ્સ માત્ર તમારા પર્સનલ આઈડી પર જ આવશે
CHAT_ID   = "1358803794"

IST = pytz.timezone("Asia/Kolkata")

# 👥 દરેક મિત્રનું સર્ચ સ્ટેટસ અલગ રાખવા માટેનું નવું ડાયનેમિક સેટિંગ
user_status = {}
last_alert_sent = None  

POPULAR_STOCKS = {
    "HBL POWER": "HBLENGINE.NS",
    "HBL": "HBLENGINE.NS",
    "WIPRO": "WIPRO.NS",
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "INFY": "INFY.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "SBI": "SBIN.NS",
    "SBIN": "SBIN.NS",
    "ITC": "ITC.NS",
    "BHARTI AIRTEL": "BHARTIARTL.NS",
    "AIRTEL": "BHARTIARTL.NS"
}

def now_ist():
    return datetime.now(IST)

def is_market_hours():
    n = now_ist()
    current_time = n.hour * 100 + n.minute
    return 915 <= current_time <= 1530

def get_expiry_alert():
    n = now_ist()
    weekday = n.weekday() 
    if weekday == 0: return "📅 <b>EXPIRY ALERT:</b> આજે <b>MIDCAP SELECT</b> ની એક્સપાયરી છે! 🎯"
    elif weekday == 1: return "📅 <b>EXPIRY ALERT:</b> આજે <b>FINNIFTY</b> ની ધાંસુ એક્સપાયરી છે! 🎯"
    elif weekday == 2: return "📅 <b>EXPIRY ALERT:</b> આજે <b>BANKNIFTY</b> નો મોટો દિવસ (Expiry) છે! 🎯"
    elif weekday == 3: return "📅 <b>EXPIRY ALERT:</b> આજે <b>NIFTY 50</b> નો મેઈન એક્સપાયરી ધડાકો છે! 🎯"
    elif weekday == 4: return "📅 <b>EXPIRY ALERT:</b> આજે <b>SENSEX</b> ની ધમાકેદાર એક્સપાયરી છે! 🎯"
    return ""

def get_range_for_interval(interval):
    if interval == "1m": return "1d"
    elif interval in ["5m", "15m", "30m"]: return "2d"
    elif interval in ["1h", "4h"]: return "1mo"
    elif interval == "1d": return "3mo"
    elif interval == "1wk": return "1y"
    return "2d"

def fetch_live_data(symbol, interval="5m"):
    timeframe_range = get_range_for_interval(interval)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={timeframe_range}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        res = r.json()["chart"]["result"][0]
        closes = [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
        highs  = [x for x in res["indicators"]["quote"][0]["high"] if x is not None]
        lows   = [x for x in res["indicators"]["quote"][0]["low"] if x is not None]
        volumes = [x for x in res["indicators"]["quote"][0]["volume"] if x is not None]
        price = res["meta"]["regularMarketPrice"]
        prev_close = res["meta"].get("previousClose", price)
        
        name = symbol
        if symbol == "^NSEI": name = "NIFTY 50"
        elif symbol == "^NSEBANK": name = "BANK NIFTY"
        elif symbol == "^BSESN": name = "SENSEX"
        elif symbol == "^NSMIDCP": name = "NIFTY MIDCAP 100"
        elif symbol == "^NSE91": name = "NIFTY NEXT 50"
        elif symbol == "HBLENGINE.NS": name = "HBL POWER"
        
        recent_highs = highs[-20:] if len(highs) >= 20 else highs
        recent_lows = lows[-20:] if len(lows) >= 20 else lows
        recent_vols = volumes[-20:] if len(volumes) >= 20 else volumes
        
        tf_resistance = round(max(recent_highs), 2) if recent_highs else price
        tf_support = round(min(recent_lows), 2) if recent_lows else price
        
        current_vol = volumes[-1] if volumes else 0
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
        vol_ratio = round(current_vol / avg_vol, 1) if current_vol else 0
        
        return round(price, 2), closes, highs, lows, volumes, round(prev_close, 2), name, tf_resistance, tf_support, vol_ratio
    except:
        return None, [], [], [], [], None, symbol, None, None, 0

def get_multi_tf_summary_table(symbol):
    intervals = ["1m", "5m", "15m", "1h", "1d"]
    table_text = "\n📋 <b>MULTIPLE TIMEFRAME LEVELS:</b>\n"
    table_text += "<code>TF    | Resistance | Support   </code>\n"
    table_text += "<code>-------------------------------</code>\n"
    for tf in intervals:
        p, _, hs, ls, _, _, _, res, sup, _ = fetch_live_data(symbol, tf)
        if p and res and sup:
            tf_pad = tf.ljust(5)
            res_pad = f"{res:,}".ljust(11)
            sup_pad = f"{sup:,}"
            table_text += f"<code>{tf_pad}| {res_pad}| {sup_pad}</code>\n"
    return table_text

# ============================================
# 📊 MATHEMATICAL INDICATORS ENGINE
# ============================================
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

def calc_stoch_rsi(closes, p=14, k_p=3, d_p=3):
    rsi_vals = calc_rsi_list(closes, p)
    if len(rsi_vals) < p: return "N/A", "N/A"
    stoch_rsi_list = []
    for i in range(p, len(rsi_vals) + 1):
        window = rsi_vals[i - p:i]
        if not window: continue
        low_rsi = min(window)
        high_rsi = max(window)
        diff = high_rsi - low_rsi
        stoch_val = ((rsi_vals[i - 1] - low_rsi) / diff * 100.0) if diff != 0 else 50.0
        stoch_rsi_list.append(stoch_val)
    if len(stoch_rsi_list) < k_p: return "N/A", "N/A"
    k_vals = [sum(stoch_rsi_list[i - k_p:i]) / k_p for i in range(k_p, len(stoch_rsi_list) + 1)]
    if len(k_vals) < d_p: return round(k_vals[-1], 1), "N/A"
    d_val = sum(k_vals[-d_p:]) / d_p
    return round(k_vals[-1], 1), round(d_val, 1)

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal: return "N/A", "N/A"
    macd_line = []
    for i in range(slow, len(closes) + 1):
        f_ema = calc_ema(closes[:i], fast)
        s_ema = calc_ema(closes[:i], slow)
        if f_ema is not None and s_ema is not None: macd_line.append(f_ema - s_ema)
    if len(macd_line) < signal: return "N/A", "N/A"
    signal_line = calc_ema(macd_line, signal)
    if macd_line and signal_line is not None: return round(macd_line[-1], 2), round(signal_line, 2)
    return "N/A", "N/A"

def calc_vwap(highs, lows, closes, volumes):
    if not closes or len(closes) != len(volumes): return None
    total_pv = 0; total_v = 0
    for h, l, c, v in zip(highs[-20:], lows[-20:], closes[-20:], volumes[-20:]):
        typ_price = (h + l + c) / 3
        total_pv += typ_price * v
        total_v += v
    return round(total_pv / total_v, 2) if total_v else closes[-1]

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

def fetch_google_news(query):
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:1]:
            title = item.find("title").text.split(" - ")[0]
            link = item.find("link").text
            return f"\n\n📢 <b>LATEST NEWS:</b>\n• <b>{title}</b>\n  🔗 <a href='{link}'>વાંચવા માટે ક્લિક કરો</a>"
    except:
        pass
    return ""

# ============================================
# 📊 REPORT GENERATOR ENGINE
# ============================================
def generate_advanced_report(symbol, interval="5m", is_crypto=False):
    price, closes, highs, lows, volumes, prev_close, name, tf_res, tf_sup, vol_ratio = fetch_live_data(symbol, interval)
    if not price: return None, None
    
    st_trend = calc_supertrend(highs, lows, closes)
    macd_l, macd_s = calc_macd(closes)
    stoch_k, stoch_d = calc_stoch_rsi(closes)
    vwap_val = calc_vwap(highs, lows, closes, volumes) if not is_crypto else None
    
    rsi_vals = calc_rsi_list(closes)
    rsi = round(rsi_vals[-1], 1) if rsi_vals else "N/A"
    ema9 = calc_ema(closes, 9)
    
    change = round(price - prev_close, 2)
    p_change = round((change / prev_close) * 100, 2)
    sign = "$" if is_crypto else "₹"
    
    bullish_votes = 0; bearish_votes = 0
    if rsi != "N/A" and rsi >= 50: bullish_votes += 1
    elif rsi != "N/A" and rsi < 45: bearish_votes += 1
    if st_trend == "BULLISH": bullish_votes += 1
    elif st_trend == "BEARISH": bearish_votes += 1
    if macd_l != "N/A" and macd_s != "N/A" and macd_l > macd_s: bullish_votes += 1
    elif macd_l != "N/A" and macd_s != "N/A" and macd_l < macd_s: bearish_votes += 1
    if vwap_val and price > vwap_val: bullish_votes += 1
    elif vwap_val and price < vwap_val: bearish_votes += 1

    if bullish_votes >= 3 and vol_ratio >= 1.2:
        live_signal = "🟢 <b>STRONG BUY / BULLISH ZONE</b>"
        action = "બધા જ પ્રો ઇન્ડિકેટર્સ તેજી બતાવે છે! સેફ બાયિંગ સજેશન છે."
        sentiment = "🚀 BULLET BULLISH"
    elif bearish_votes >= 3:
        live_signal = "🔴 <b>STRONG SELL / BEARISH EXITS</b>"
        action = "ભારે નુકસાનથી બચવા હોલ્ડિંગમાંથી એક્ઝિટ (Sell) કરો અથવા નવું બાયિંગ અટકાવો."
        sentiment = "⚠️ DANGER BEARISH"
    else:
        live_signal = "⚖️ <b>HOLD / WAIT (SIDEWAYS)</b>"
        action = "માર્કેટ ચોપ્પી (Sideways) છે. કન્ફર્મ મોમેન્ટમ ન મળે ત્યાં સુધી શાંતિ રાખો."
        sentiment = "⚖️ NEUTRAL RANGING"
        
    vol_emoji = "📊"
    if vol_ratio >= 2.0: vol_emoji = "🔥 HIGH VOLUME BOOST"
    elif vol_ratio <= 0.5: vol_emoji = "💤 LOW VOLUME DRY"
    vol_text = f"{vol_emoji} ({vol_ratio}x of Avg)"
    
    vwap_text = f"🔹 <b>VWAP:</b> {sign}{vwap_val}\n" if vwap_val else ""
    
    suggested_entry = round(max(price, tf_res), 2) if "BUY" in live_signal else price
    suggested_sl = tf_sup
    risk_points = round(suggested_entry - suggested_sl, 2) if suggested_entry > suggested_sl else 1
    suggested_tgt = round(suggested_entry + (risk_points * 2), 2)
    
    setup_text = f"\n💡 <b>PRO ALGO SETUP (R:R 1:2):</b>\n🚀 <b>Entry Level:</b> {sign}{suggested_entry}\n🎯 <b>Target (TGT):</b> {sign}{suggested_tgt}\n🛑 <b>Stop Loss (SL):</b> {sign}{suggested_sl}"
    if "HOLD" in live_signal: setup_text = "\n💡 <b>PRO ALGO SETUP:</b>\n⏱️ રેઝિસ્ટન્સ બ્રેકઆઉટ કે સપોર્ટ હોલ્ડ થવાની રાહ જુઓ."

    tf_summary_table = get_multi_tf_summary_table(symbol) if interval == "5m" else ""
    news = fetch_google_news("Bitcoin Crypto" if is_crypto else name) if interval == "5m" else ""
    expiry_text = get_expiry_alert() if (not is_crypto and interval == "5m") else ""
    if expiry_text: expiry_text = f"\n\n{expiry_text}"
    
    emoji = "🟢📈" if change >= 0 else "🔴📉"
    
    text = f"""{emoji} <b>{name} LIVE REPORT ({interval})</b>

📢 <b>ALGO SIGNAL: {live_signal}</b>
🔥 <b>Trend Quality:</b> {sentiment}
👉 <b>એક્શન પ્લાન:</b> {action}
------------------------------------------
💰 <b>Price:</b> {sign}{price:,} ({change:+} | {p_change:+}-%)
📈 <b>EMA9:</b> {ema9 or 'N/A'} | 📉 <b>RSI(14):</b> {rsi}
⚡ <b>Supertrend:</b> {st_trend}
🎛️ <b>MACD Line:</b> {macd_l} (Signal: {macd_s})
🌀 <b>Stoch RSI:</b> K:{stoch_k} | D:{stoch_d}
{vwap_text}------------------------------------------
📍 <b>CHART LEVELS ({interval}):</b>
🚧 <b>Resistance:</b> {sign}{tf_res:,}
🛡️ <b>Support:</b> {sign}{tf_sup:,}
📊 <b>Volume Mood:</b> {vol_text}
{tf_summary_table}{setup_text}{expiry_text}{news}
⏰ {now_ist().strftime('%H:%M:%S IST')}"""

    c_type = "1" if is_crypto else "0"
    markup = {
        "inline_keyboard": [
            [{"text": "⚡ 1 Min", "callback_data": f"tf_{symbol}_{interval}_{c_type}_1m"},
             {"text": "⏱️ 5 Min", "callback_data": f"tf_{symbol}_{interval}_{c_type}_5m"},
             {"text": "⏱️ 15 Min", "callback_data": f"tf_{symbol}_{interval}_{c_type}_15m"}],
            [{"text": "⏱️ 30 Min", "callback_data": f"tf_{symbol}_{interval}_{c_type}_30m"},
             {"text": "⏳ 1 Hour", "callback_data": f"tf_{symbol}_{interval}_{c_type}_1h"},
             {"text": "🕒 4 Hour", "callback_data": f"tf_{symbol}_{interval}_{c_type}_4h"}],
            [{"text": "📅 1 Day", "callback_data": f"tf_{symbol}_{interval}_{c_type}_1d"},
             {"text": "🗓️ 1 Week", "callback_data": f"tf_{symbol}_{interval}_{c_type}_1wk"}],
            [{"text": "🔙 Back to Main Menu", "callback_data": "go_main"}]
        ]
    }
    return text, markup

# ============================================
# 🎯 DYNAMIC MULTI-USER DYNAMIC ROUTING
# ============================================
def handle_search_text(user_text, current_chat_id):
    query = user_text.upper().strip()
    str_chat_id = str(current_chat_id)
    
    # જો આ યુઝરે પહેલા સર્ચ બટન દબાવ્યું હોય, તો એનું સ્ટેટસ ક્લિયર કરીને ડાયરેક્ટ સર્ચ કરશે
    if user_status.get(str_chat_id) == "WAITING_FOR_SEARCH":
        user_status[str_chat_id] = None
    
    if query in POPULAR_STOCKS:
        symbol = POPULAR_STOCKS[query]
        text, markup = generate_advanced_report(symbol, "5m")
        if text:
            send_telegram_msg(text, current_chat_id, reply_markup=markup)
            return

    all_keys = list(POPULAR_STOCKS.keys())
    close_matches = difflib.get_close_matches(query, all_keys, n=2, cutoff=0.6)
    
    if close_matches:
        buttons = []
        for match in close_matches:
            sym = POPULAR_STOCKS[match]
            buttons.append([{"text": f"🔍 {match} નો રિપોર્ટ જુઓ", "callback_data": f"tf_{sym}_5m_0_5m"}])
        buttons.append([{"text": "🔙 Main Menu", "callback_data": "go_main"}])
        
        markup = {"inline_keyboard": buttons}
        send_telegram_msg(f"🤔 <b>ખોટો સ્પેલિંગ પકડાયો!</b>\n\nશું તમે આમાંથી કંઈક સર્ચ કરવા માંગો છો? નીચે ક્લિક કરો:", current_chat_id, reply_markup=markup)
        return

    symbol = f"{query}.NS"
    text, markup = generate_advanced_report(symbol, "5m")
    if text:
        send_telegram_msg(text, current_chat_id, reply_markup=markup)
    else:
        fallback_markup = {"inline_keyboard": [[{"text": "🔙 Main Menu", "callback_data": "go_main"}]]}
        send_telegram_msg(f"❌ <b>સ્ટોક ન મળ્યો!</b>\n\n'<b>{query}</b>' નામનો કોઈ સ્ટોક ઇન્ડિયન માર્કેટમાં મળ્યો નથી.", current_chat_id, reply_markup=fallback_markup)

def send_telegram_msg(text, current_chat_id, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": str(current_chat_id), "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

def send_main_menu(current_chat_id):
    markup = {
        "inline_keyboard": [
            [{"text": "⚡ HBL Power", "callback_data": "m_hbl"}, {"text": "🪙 Bitcoin (24/7)", "callback_data": "m_btc"}],
            [{"text": "📊 NIFTY 50", "callback_data": "m_nifty"}, {"text": "📈 BANK NIFTY", "callback_data": "m_bnifty"}],
            [{"text": "💎 SENSEX", "callback_data": "m_sensex"}, {"text": "🚀 NIFTY NEXT 50", "callback_data": "m_next50"}],
            [{"text": "🔥 MIDCAP 100", "callback_data": "m_midcap"}, {"text": "🔍 Search Stock", "callback_data": "m_search"}]
        ]
    }
    send_telegram_msg("👋 <b>નમસ્તે! (Ultimate Pro Indicator Engine)</b>\n\nસર્વર ૨૪/૭ લાઈવ છે. રિપોર્ટ જોવા નીચે ક્લિક કરો:", current_chat_id, reply_markup=markup)

def handle_callback(callback_id, data, current_chat_id):
    text, markup = "", None
    str_chat_id = str(current_chat_id)
    
    if data == "m_hbl": text, markup = generate_advanced_report("HBLENGINE.NS", "5m")
    elif data == "m_btc": text, markup = generate_advanced_report("BTC-USD", "5m", is_crypto=True)
    elif data == "m_nifty": text, markup = generate_advanced_report("^NSEI", "5m")
    elif data == "m_bnifty": text, markup = generate_advanced_report("^NSEBANK", "5m")
    elif data == "m_sensex": text, markup = generate_advanced_report("^BSESN", "5m")
    elif data == "m_next50": text, markup = generate_advanced_report("^NSE91", "5m")
    elif data == "m_midcap": text, markup = generate_advanced_report("^NSMIDCP", "5m")
    elif data == "go_main": 
        send_main_menu(current_chat_id)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
        return
    elif data == "m_search":
        user_status[str_chat_id] = "WAITING_FOR_SEARCH"
        send_telegram_msg("🔍 <b>Pro Script Search Activated:</b>\n\nકૃપા કરીને નામ મોકલો (e.g. WIPRO):", current_chat_id)
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
        return
    elif data.startswith("tf_"):
        parts = data.split("_")
        text, markup = generate_advanced_report(parts[1], parts[4], is_crypto=(parts[3] == "1"))

    if text: send_telegram_msg(text, current_chat_id, reply_markup=markup)
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})

# ============================================
# REAL-TIME BACKGROUND ALERTS
# ============================================
def check_and_send_auto_alerts():
    global last_alert_sent
    res = fetch_live_data("HBLENGINE.NS", "5m")
    price = res[0]
    if not price: return
    closes, highs, lows, volumes, _, _, tf_res, tf_sup, vol_ratio = res[1:]
    
    st_trend = calc_supertrend(highs, lows, closes)
    rsi_vals = calc_rsi_list(closes)
    rsi = rsi_vals[-1] if rsi_vals else 50
    current_minute = now_ist().strftime("%H:%M")
    
    if price > tf_res and rsi >= 55 and vol_ratio >= 2.0 and st_trend == "BULLISH":
        if last_alert_sent != f"BUY_{current_minute}":
            msg = f"🔥 <b>[ALGO-BOOST] HBL જેકપોટ બ્રેકઆઉટ!</b>\n\n💰 <b>Live Price:</b> ₹{price}\n⚡ <b>Supertrend:</b> BULLISH\n📊 <b>Vol Boost:</b> {vol_ratio}x\n🚧 <b>Res Broken:</b> ₹{tf_res}\n\n🚨 <b>Action:</b> BUY!"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
            last_alert_sent = f"BUY_{current_minute}"

class FakeServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot Engine is Running Perfectly!")
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

def run_fake_web_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, FakeServer)
    httpd.serve_forever()

# ============================================
# MAIN MULTI-USER LOOP
# ============================================
print("Multi-User Dynamic Engine Initiating...")
web_thread = threading.Thread(target=run_fake_web_server, daemon=True)
web_thread.start()

offset = 0
last_auto_check = 0

while True:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=2"
        r = requests.get(url, timeout=5).json()
        if "result" in r:
            for update in r["result"]:
                offset = update["update_id"] + 1
                
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
                    
        current_time = time.time()
        if current_time - last_auto_check >= 5:
            if is_market_hours(): check_and_send_auto_alerts()
            else: fetch_live_data("BTC-USD", "5m")
            last_auto_check = current_time
    except:
        time.sleep(2)
