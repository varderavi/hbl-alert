import requests
import pytz
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import threading
import os
import difflib  # સ્પેલિંગ ચેક કરવા અને ઓટો-કરેક્ટ કરવા માટે
from http.server import BaseHTTPRequestHandler, HTTPServer

# ============================================
# CONFIGURATION & DICTIONARY
# ============================================
BOT_TOKEN = "8874026729:AAEgzZr0UslgaKGdPiUjZMONNuFCKL-pqsY"
CHAT_ID   = "1358803794"

IST = pytz.timezone("Asia/Kolkata")

user_status = {}
last_alert_sent = None  

# મોસ્ટ પોપ્યુલર ઇન્ડિયન સ્ટોક્સનું માસ્ટર લિસ્ટ
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

# ============================================
# 📊 MATHEMATICAL INDICATORS ENGINE
# ============================================
def calc_ema(data, p):
    if len(data) < p: return None
    k = 2/(p+1); e = sum(data[:p])/p
    for v in data[p:]: e = v*k + e*(1-k)
    return round(e, 2)

def calc_rsi_list(data, p=14):
    if len(data) < p+1: return []
    rsi_history = []
    gains = [max(data[i]-data[i-1], 0) for i in range(1, len(data))]
    losses = [max(data[i-1]-data[i], 0) for i in range(1, len(data))]
    
    ag = sum(gains[:p])/p
    al = sum(losses[:p])/p
    rsi_history.append(100 - 100/(1+ag/al) if al
