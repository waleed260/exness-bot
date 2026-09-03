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
SYMBOL = "EURUSD"
TIMEFRAME = _M15          # candle used for decisions
LOOKBACK_BARS = 200       # bars pulled for indicators / LLM context

# ---------------- Risk ----------------
RISK_PER_TRADE_PCT = 0.5  # % of balance risked per trade (used for lot sizing)
FIXED_LOT_FALLBACK = 0.01 # used if lot sizing cannot be computed
MAX_LOT = 0.10            # hard cap on lot size
MAX_OPEN_POSITIONS = 1    # per symbol
ATR_PERIOD = 14
SL_ATR_MULT = 2.0         # stop loss distance = SL_ATR_MULT * ATR
TP_ATR_MULT = 3.0         # take profit distance = TP_ATR_MULT * ATR
DAILY_MAX_LOSS_PCT = 3.0  # stop trading for the day after this equity drawdown
MIN_CONFIDENCE = 0.55     # ignore signals weaker than this

# ---------------- Execution ----------------
DEVIATION_POINTS = 20     # max slippage in points
MAGIC = 20240601          # bot id stamped on orders
POLL_SECONDS = 5          # how often the loop checks for a new closed candle

# ---------------- Strategy ----------------
USE_LLM = True            # if False (or no API key) use the rule-based strategy
SMA_FAST = 20
SMA_SLOW = 50
RSI_PERIOD = 14
