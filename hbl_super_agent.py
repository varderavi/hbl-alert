# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = os.getenv("BOT_TOKEN")   # .env ma rakho
CHAT_ID   = os.getenv("CHAT_ID")

# ============================================
# ADVANCED INDICATORS
# ============================================
def calc_macd(data, fast=12, slow=26, signal=9):
    if len(data) < slow: return None, None
    fast_ema = calc_ema(data, fast)
    slow_ema = calc_ema(data, slow)
    macd_line = fast_ema - slow_ema
    signal_line = calc_ema([macd_line] * len(data), signal)
    return round(macd_line, 2), round(signal_line, 2)

def calc_bollinger(data, p=20, mult=2):
    if len(data) < p: return None, None
    sma = sum(data[-p:]) / p
    std = (sum([(x - sma) ** 2 for x in data[-p:]]) / p) ** 0.5
    upper = round(sma + mult * std, 2)
    lower = round(sma - mult * std, 2)
    return upper, lower

# =================================
