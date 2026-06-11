import os, requests, time, logging
from datetime import datetime
import pytz

BOT_TOKEN = os.getenv("BOT_TOKEN")
FINNHUB_KEY = os.getenv("FINNHUB_KEY")
IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(filename="bot.log", level=logging.INFO)

def now_ist():
    return datetime.now(IST)

# --- Indian API ---
def fetch_indian_stock(symbol):
    try:
        url = f"http://65.0.104.9/stock?symbol={symbol}&res=num"
        r = requests.get(url, timeout=5).json()
        return round(r["data"]["last_price"],2), r["data"]["change"], r["data"]["percent_change"]
    except: return None,None,None

# --- Finnhub ---
def fetch_finnhub_quote(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=5).json()
        return round(r["c"],2), r["h"], r["l"], r["pc"]
    except: return None,None,None,None

# --- Yahoo fallback ---
def fetch_yahoo(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r = requests.get(url, timeout=7).json()
        res = r["chart"]["result"][0]
        price = res["meta"]["regularMarketPrice"]
        prev_close = res["meta"].get("previousClose", price)
        return round(price,2), round(prev_close,2)
    except: return None,None

# --- Indicators ---
def calc_ema(data,p):
    if len(data)<p: return None
    k=2/(p+1); e=sum(data[:p])/p
    for v in data[p:]: e=v*k+e*(1-k)
    return round(e,2)

def calc_rsi(data,p=14):
    if len(data)<p+1: return None
    gains,losses=[],[]
    for i in range(1,len(data)):
        diff=data[i]-data[i-1]
        gains.append(max(diff,0)); losses.append(max(-diff,0))
    ag=sum(gains[:p])/p; al=sum(losses[:p])/p
    rs=ag/al if al else 0
    return round(100-(100/(1+rs)),1)

def calc_macd(data,fast=12,slow=26,signal=9):
    if len(data)<slow: return None,None
    fast_ema=calc_ema(data,fast); slow_ema=calc_ema(data,slow)
    macd_line=fast_ema-slow_ema
    signal_line=calc_ema([macd_line]*len(data),signal)
    return macd_line,signal_line

def calc_bollinger(data,p=20,mult=2):
    if len(data)<p: return None,None
    sma=sum(data[-p:])/p
    std=(sum([(x-sma)**2 for x in data[-p:]])/p)**0.5
    return round(sma+mult*std,2), round(sma-mult*std,2)

# --- Prediction ---
def intraday_prediction(price,res,sup,rsi,macd,boll):
    if price>res and rsi and rsi>55: return "🚀 Breakout → Upside"
    elif price<sup and rsi and rsi<45: return "⚠️ Breakdown → Downside"
    elif macd and macd[0]>macd[1]: return "📈 MACD Bullish"
    elif macd and macd[0]<macd[1]: return "📉 MACD Bearish"
    else: return "⚖️ Neutral"

# --- Report ---
def generate_report(symbol,source="indian",name="Stock"):
    if source=="indian":
        price,change,p_change=fetch_indian_stock(symbol)
        if not price:
            price,prev_close=fetch_yahoo(f"{symbol}.NS")
            if not price: return "⚠️ NSE data not available.",None
            change=round(price-prev_close,2); p_change=round((change/prev_close)*100,2)
            src="Yahoo (Delayed)"
        else: src="Indian API (Live)"
        text=f"""📊 <b>{name} LIVE</b>
💰 Price: ₹{price} | Source: {src}
📈 Change: {change} ({p_change}%)
⏰ {now_ist().strftime('%H:%M:%S IST')}"""
    else:
        price,high,low,prev_close=fetch_finnhub_quote(symbol)
        if not price:
            price,prev_close=fetch_yahoo(symbol)
            if not price: return "⚠️ SGX data not available.",None
            high,low=price,price; src="Yahoo (Delayed)"
        else: src="Finnhub (Live)"
        change=round(price-prev_close,2); p_change=round((change/prev_close)*100,2)
        closes=[prev_close,price]
        ema9=calc_ema(closes,9); rsi=calc_rsi(closes)
        macd=calc_macd(closes); boll=calc_bollinger(closes)
        prediction=intraday_prediction(price,high,low,rsi,macd,boll)
        text=f"""📊 <b>{name} LIVE</b>
💰 Price: {price} ({change:+} | {p_change:+}%) | Source: {src}
📈 High: {high} | Low: {low}
📉 Prev Close: {prev_close}
📊 EMA9: {ema9} | RSI: {rsi}
⚡ MACD: {macd} | 📊 Bollinger: {boll}
🔮 Prediction: {prediction}
⏰ {now_ist().strftime('%H:%M:%S IST')}"""
    markup={"inline_keyboard":[
        [{"text":"⚡ Refresh","callback_data":f"refresh_{symbol}_{source}"}],
        [{"text":"🔙 Back","callback_data":"go_main"}]
    ]}
    return text,markup

def send_msg(text,chat_id,markup=None,msg_id=None):
    if msg_id:
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
        payload={"chat_id":chat_id,"message_id":msg_id,"text":text,"parse_mode":"HTML"}
        if markup: payload["reply_markup"]=markup
    else:
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload={"chat_id":chat_id,"text":text,"parse_mode":"HTML"}
        if markup: payload["reply_markup"]=markup
    requests.post(url,json=payload,timeout=5)

# --- Menu ---
def send_main_menu(chat_id,msg_id=None):
    markup={"inline_keyboard":[
        [{"text":"🚀 SGX NIFTY","callback_data":"m_sgx"},
         {"text":"⚡ Reliance","callback_data":"m_rel"}]
    ]}
    send_msg("👋 <b>નમસ્તે રવિ ભાઈ!</b>\n\nChoose source:",chat_id,markup,msg_id)

# --- Callback ---
def handle_callback(data,chat_id,msg_id):
    if data=="m_sgx":
        text,markup=generate_report("SGX:NIFTY","finnhub","SGX NIFTY")
        if text: send_msg(text,chat_id,markup,msg_id)
    elif data=="m_rel":
        text,markup=generate_report("RELIANCE","indian","Reliance")
        if text: send_msg(text,chat_id,markup,msg_id)
    elif data.startswith("refresh_"):
        parts=data.split("_")
        symbol,source=parts[1],parts[2]
        text,markup=generate_report(symbol,source,symbol)
        if text: send_msg(text,chat_id,markup,msg_id)
    elif data=="go_main":
        send_main_menu(chat_id,msg_id)

# --- Main Loop ---
offset=0
last_response_time={}
while True:
    try:
        url=f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=10"
        r=requests.get(url,timeout=5).json()
        if "result" in r:
            for update in r["result"]:
                offset=update["update_id"]+1
                chat_id=None; msg_id=None
                if "message" in update:
                    chat_id=update["message"]["chat"]["id"]
                    msg_id=update["message"]["message_id"]
                    txt=update["message"].get("text","")
                    if txt.lower() in ["hi","hello","menu","/start"]:
                        send_main_menu(chat_id)
