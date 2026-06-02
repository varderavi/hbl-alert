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
CHAT_ID   = "1358803794"

IST = pytz.timezone("Asia/Kolkata")

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

# 🎯 બેકગ્રાઉન્ડમાં બધી ટાઇમફ્રેમ્સના સપોર્ટ/રેઝિસ્ટન્સ એકસાથે ખેંચવા માટેનું નવું ફંક્શન
def get_multi_tf_summary_table(symbol):
    intervals = ["1m", "5m", "15m", "1h", "1d"]
    table_text = "\n📋 <b>MULTIPLE TIMEFRAME LEVELS:</b>\n"
    table_text += "<code>TF    | Resistance | Support   </code>\n"
    table_text += "<code>-------------------------------</code>\n"
    for tf in intervals:
        p, _, hs, ls, _, _, _, res, sup, _ = fetch_live_data(symbol, tf)
        if p and res and sup:
            # બરાબર ફોર્મેટિંગ જળવાય એ માટે સ્પેસિંગ સેટ કર્યું
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
    for v in data[p:]:
        e = v * k + e * (1 - k)
    return round(e, 2)

def calc_rsi_list(data, p=14):
    if len(data) < p + 1: return []
    rsi_history = []
    gains = []
    losses = []
    for i in range(1, len(data)):
        diff = data[i] - data[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
            
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
        if f_ema is not None and s_ema is not None: 
            macd_line.append(f_ema - s_ema)
    if len(macd_line) < signal: return "N/A", "N/A"
    signal_line = calc_ema(macd_line, signal)
    if macd_line and signal_line is not None:
