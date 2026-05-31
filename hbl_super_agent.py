import requests
import pytz
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = "8874026729:AAEgzZr0UslgaKGdPiUjZMONNuFCKL-pqsY"
CHAT_ID   = "1358803794"

IST = pytz.timezone("Asia/Kolkata")

user_status = {}
last_alert_sent = None  # એક જ એલર્ટ વારંવાર ન જાય તે માટે

def now_ist():
    return datetime.now(IST)

def is_market_hours():
    # ⏱️ રિયલ-ટાઇમ માર્કેટ અવર્સ (સવારે ૦૯:૧૫ થી સાંજે ૦૩:૩૦)
    n = now_ist()
    current_time = n.hour * 100 + n.minute
    return 915 <= current_time <= 1530

def get_range_for_interval(interval):
    if interval in ["5m", "15m", "30m"]: return "2d"
    elif interval == "1h": return "1mo"
    elif interval == "1d": return "3mo"
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
        
        recent_highs = highs[-20:] if len(highs) >= 20 else highs
        recent_lows = lows[-20:] if len(lows) >= 20 else lows
        recent_vols = volumes[-20:] if len(volumes) >= 20 else volumes
        
        tf_resistance = round(max(recent_highs), 2) if recent_highs else price
        tf_support = round(min(recent_lows), 2) if recent_lows else price
        
        current_vol = volumes[-1] if volumes else 0
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 1
        vol_ratio = round(current_vol / avg_vol, 1) if current_vol else 0
        
        return round(price, 2), closes, round(prev_close, 2), symbol, tf_resistance, tf_support, vol_ratio
    except:
        return None, [], None, symbol, None, None, 0

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

def check_and_send_auto_alerts():
    global last_alert_sent
    price, closes, _, _, tf_res, tf_sup, vol_ratio = fetch_live_data("HBLENGINE.NS", "5m")
    if not price: return
    
    rsi = calc_rsi(closes)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    
    current_minute = now_ist().strftime("%H:%M")
    
    if len(closes) > 21 and ema9 and ema21 and rsi != "N/A":
        # 🚀 જેકપોટ બાય કન્ડિશન
        if price > tf_res and rsi >= 55 and vol_ratio >= 2.0:
            if last_alert_sent != f"BUY_{current_minute}":
                msg = f"🔥 <b>[REAL-TIME] HBL જેકપોટ બ્રેકઆઉટ!</b>\n\n💰 <b>Live Price:</b> ₹{price}\n📊 <b>Vol Boost:</b> {vol_ratio}x\n🚧 <b>Res Broken:</b> ₹{tf_res}\n\n🚨 <b>Action:</b> હાઇ વોલ્યુમ બ્રેકઆઉટ છે, Trailing SL સાથે એન્ટ્રી લો!"
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
                last_alert_sent = f"BUY_{current_minute}"
        
        # 🛑 હોલ્ડિંગ ક્રેશ કન્ડિશન
        elif price < tf_sup and rsi <= 42:
            if last_alert_sent != f"SELL_{current_minute}":
                msg = f"🛑 <b>[REAL-TIME] HBL સપોર્ટ તૂટ્યો!</b>\n\n💰 <b>Live Price:</b> ₹{price}\n📉 <b>RSI:</b> {rsi}\n🛡️ <b>Support Broken:</b> ₹{tf_sup}\n\n🚨 <b>Action:</b> જો હોલ્ડિંગ હોય તો કેપિટલ બચાવવા <b>EXIT (Sell)</b> કરો!"
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
                last_alert_sent = f"SELL_{current_minute}"

# ============================================
# 🌐 NON-STOP REAL TIME LOOP
# ============================================
print("Real-Time Non-Stop Market Agent Active...")
last_auto_check = 0

while True:
    try:
        current_time = time.time()
        
        # ⚡ દર ૫ સેકન્ડે ડેટા સ્કેન (Real-Time Non-Stop)
        if current_time - last_auto_check >= 5:
            if is_market_hours():
                check_and_send_auto_alerts()
            last_auto_check = current_time

        time.sleep(1) # સર્વર ક્રેશ ન થાય તે માટે ૧ સેકન્ડનો શ્વાસ
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
