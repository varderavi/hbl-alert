import os, requests, time, logging
from datetime import datetime
import pytz

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")
IST = pytz.timezone("Asia/Kolkata")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")

logging.basicConfig(filename="bot.log", level=logging.INFO)

# ============================================
# HELPERS
# ============================================
def now_ist():
    return datetime.now(IST)

# --- Indian Stock Market API ---
def fetch_indian_stock(symbol, retries=3):
    for attempt in range(retries):
        try:
            url = f"http://65.0.104.9/stock?symbol={symbol}&res=num"
            r = requests.get(url, timeout=5).json()
            return round(r["data"]["last_price"],2), r["data"]["change"], r["data"]["percent_change"]
        except Exception as e:
            logging.error(f"Indian API error {symbol}: {e}")
            time.sleep(1)
    return None, None, None

# --- Finnhub API ---
def fetch_finnhub_quote(symbol, retries=3):
    for attempt in range(retries):
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            r = requests.get(url, timeout=5).json()
            return round(r["c"],2), r["h"], r["l"], r["pc"]
        except Exception as e:
            logging.error(f"Finnhub error {symbol}: {e}")
            time.sleep(1)
    return None, None, None, None

# ============================================
# INDICATORS
# ============================================
def calc_ema(data, p):
    if len(data) < p: return None
    k = 2/(p+1); e = sum(data[:p])/p
    for v in data[p:]: e = v*k + e*(1-k)
    return round(e,2)

def calc_rsi(data, p=14):
    if len(data) < p+1: return None
    gains, losses = [], []
    for i in range(1,len(data)):
        diff = data[i]-data[i-1]
        gains.append(max(diff,0)); losses.append(max(-diff,0))
    ag = sum(gains[:p])/p; al = sum(losses[:p])/p
    rs = ag/al if al else 0
    return round(100-(100/(1+rs)),1)

def calc_macd(data, fast=12, slow=26, signal=9):
    if len(data)<slow: return None,None
    fast_ema = calc_ema(data,fast); slow_ema = calc_ema(data,slow)
    macd_line = fast_ema - slow_ema
    signal_line = calc_ema([macd_line]*len(data),signal)
    return macd_line, signal_line

def calc_bollinger(data,p=20,mult=2):
    if len(data)<p: return None,None
    sma = sum(data[-p:])/p
    std = (sum([(x-sma)**2 for x in data[-p:]])/p)**0.5
    return round(sma+mult*std,2), round(sma-mult*std,2)

# ============================================
# PREDICTION
# ============================================
def intraday_prediction(price,res,sup,rsi,macd,boll):
    if price>res and rsi and rsi>55: return "🚀 Breakout → Upside"
    elif price<sup and rsi and rsi<45: return "⚠️ Breakdown → Downside"
    elif macd and macd[0]>macd[1]: return "📈 MACD Bullish"
    elif macd and macd[0]<macd[1]: return "📉 MACD Bearish"
    else: return "⚖️ Neutral"

# ============================================
# REPORT GENERATOR
# ============================================
def generate_report(symbol, source="indian", name="Stock"):
    if source=="indian":
        price, change, p_change = fetch_indian_stock(symbol)
        if not price: return None,None
        text = f"""📊 <b>{name} LIVE (NSE)</b>
💰 Price: ₹{price}
📈 Change: {change} ({p_change}%)
⏰ {now_ist().strftime('%H:%M:%S IST')}"""
    else:
        price, high, low, prev_close = fetch_finnhub_quote(symbol)
        if not price: return None,None
        change = round(price-prev_close,2)
        p_change = round((change/prev_close)*100,2)
        # Indicators demo with dummy closes
        closes = [prev_close, price
