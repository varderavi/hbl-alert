import os, requests, time, threading, logging
from datetime import datetime
import pytz
from http.server import BaseHTTPRequestHandler, HTTPServer

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")   # .env ma rakho
CHAT_ID   = os.getenv("CHAT_ID")
IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(filename="bot.log", level=logging.INFO)

POPULAR_STOCKS = {
    "HBL": "HBLENGINE.NS", "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS", "ICICI": "ICICIBANK.NS", "SBI": "SBIN.NS",
    "ITC": "ITC.NS", "AIRTEL": "BHARTIARTL.NS", "IRCTC": "IRCTC.NS",
    "ZOMATO": "ZOMATO.NS"
}

# ============================================
# HELPERS
# ============================================
def now_ist():
    return datetime.now(IST)

def fetch_live_data(symbol, interval="5m"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=7)
        res = r.json()["chart"]["result"][0]
        price = res["meta"]["regularMarketPrice"]
        prev_close = res["meta"].get("previousClose", price)
        closes = [x for x in res["indicators"]["quote"][0]["close
