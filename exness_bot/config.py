"""Bot configuration. Safe-by-default: DRY_RUN is on, demo-only guard is on."""

try:
    import MetaTrader5 as mt5
    _M1 = mt5.TIMEFRAME_M1
    _M5 = mt5.TIMEFRAME_M5
    _M15 = mt5.TIMEFRAME_M15
    _H1 = mt5.TIMEFRAME_H1
    _H4 = mt5.TIMEFRAME_H4
except Exception:  # MetaTrader5 only installs on Windows; allow import elsewhere
    _M1 = _M5 = _M15 = _H1 = _H4 = None


# ---------------- Safety ----------------
DRY_RUN = True            # True = never send a real order, only log the intent
DEMO_ONLY = True          # refuse to run if the connected account is a real/live account
CONFIRM_LIVE_STRING = ""  # to trade live, set DEMO_ONLY=False AND set this to "I ACCEPT THE RISK"

# ---------------- Market ----------------
SYMBOL = "EURUSD"         # base name; broker suffix (m, ., z ...) is auto-resolved
TIMEFRAME = _M15          # candle used for decisions
LOOKBACK_BARS = 400       # bars pulled for indicators / LLM context

# ---------------- Risk ----------------
RISK_PER_TRADE_PCT = 0.5  # % of balance risked per trade (used for lot sizing)
FIXED_LOT_FALLBACK = 0.01 # used if lot sizing cannot be computed
MAX_LOT = 0.10            # hard cap on lot size
MAX_OPEN_POSITIONS = 1    # per symbol
ATR_PERIOD = 14
SL_ATR_MULT = 2.0         # stop loss distance = SL_ATR_MULT * ATR
TP_ATR_MULT = 3.0         # take profit distance = TP_ATR_MULT * ATR
MIN_ATR_POINTS = 0        # skip entries when ATR (in points) is below this (0 = off)
DAILY_MAX_LOSS_PCT = 3.0  # stop trading for the day after this equity drawdown
MIN_CONFIDENCE = 0.55     # ignore signals weaker than this

# ---- trailing / break-even (managed every poll on the open position) ----
BREAKEVEN_AT_R = 1.0      # move SL to entry once price is +1.0R in profit (0 = off)
TRAIL_AT_R = 1.5          # start trailing once price is +1.5R in profit (0 = off)
TRAIL_ATR_MULT = 2.0      # trailing SL distance = TRAIL_ATR_MULT * ATR

# ---------------- Entry filters ----------------
MAX_SPREAD_POINTS = 25    # skip entries when current spread (points) is above this
USE_TREND_FILTER = True   # only take longs in an up-trend, shorts in a down-trend
TREND_SMA = 200           # long SMA used as the trend proxy
TREND_SLOPE_LOOKBACK = 20 # bars back to measure the trend SMA slope
# trading session, UTC hours [start, end); empty list = always on
SESSION_UTC_HOURS = [7, 16]   # ~London + NY overlap for EURUSD; set [] to disable
TRADE_DAYS = [0, 1, 2, 3, 4]  # Mon..Fri (weekday numbers)

# ---------------- Execution ----------------
DEVIATION_POINTS = 20     # max slippage in points
MAGIC = 20240601          # bot id stamped on orders
POLL_SECONDS = 5          # how often the loop checks for a new closed candle
ORDER_RETRIES = 3         # retries on requote / price-changed
TRADE_LOG_CSV = "exness_bot/logs/trades.csv"

# ---------------- Strategy ----------------
USE_LLM = True            # if False (or no API key) use the rule-based strategy
SMA_FAST = 20
SMA_SLOW = 50
RSI_PERIOD = 14

# ---------------- Backtest ----------------
BT_SPREAD_POINTS = 12     # assumed round-trip spread cost per trade, in points
BT_COMMISSION_PER_LOT = 7.0   # USD per lot round-trip (Exness Raw/Zero style); 0 for Standard
BT_START_BALANCE = 1000.0
