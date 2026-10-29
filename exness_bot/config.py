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
DRY_RUN = False           # True = never send a real order, only log the intent
DEMO_ONLY = True          # refuse to run if the connected account is a real/live account
CONFIRM_LIVE_STRING = ""  # to trade live, set DEMO_ONLY=False AND set this to "I ACCEPT THE RISK"
EXECUTION_MODE = "demo"   # simulation | demo | live; simulation logs only, demo trades on demo account
LIVE_TRADING_ENABLED = False    # remains False until a separately reviewed release
EMERGENCY_STOP_FILE = "exness_bot/STOP_TRADING"
SAFETY_STATE_FILE = "exness_bot/logs/safety_state.json"
SIGNAL_LEDGER_FILE = "exness_bot/logs/signal_ledger.json"
MIN_SL_DISTANCE = 0.0       # price units; 0 = broker/strategy minimum only
MAX_SL_DISTANCE = 0.0       # price units; 0 = disabled
MIN_TP_DISTANCE = 0.0       # price units; 0 = broker/strategy minimum only
MAX_TP_DISTANCE = 0.0       # price units; 0 = disabled
MAX_TRADES_PER_DAY = 10
MAX_CONSECUTIVE_LOSSES = 3
MAX_ACCOUNT_EXPOSURE_PCT = 2.0
MIN_FREE_MARGIN_PCT = 100.0
MAX_SIGNAL_AGE_SECONDS = 900
MAX_DATA_AGE_SECONDS = 7200
MAX_SLIPPAGE_POINTS = 20

# ---------------- Market ----------------
SYMBOL = "EURUSD"         # base name; broker suffix (m, ., z ...) is auto-resolved
TIMEFRAME = _M15          # candle used for decisions
LOOKBACK_BARS = 400       # bars pulled for indicators and strategy warmup

# ---------------- Risk ----------------
# Conservative by default: small size, tight loss caps. No bot can promise profit
# or "no losses" - these limits just keep any single bad run small.
RISK_PER_TRADE_PCT = 0.25 # % of balance risked per trade (used for lot sizing)
FIXED_LOT_FALLBACK = 0.01 # used if lot sizing cannot be computed (also clamped to MAX_LOT)
MAX_LOT = 0.05            # hard cap on lot size
MAX_OPEN_POSITIONS = 1    # per symbol
ATR_PERIOD = 14
SL_ATR_MULT = 2.0         # stop loss distance = SL_ATR_MULT * ATR
TP_ATR_MULT = 3.0         # take profit distance = TP_ATR_MULT * ATR
MIN_ATR_POINTS = 0        # skip entries when ATR (in points) is below this (0 = off)
DAILY_MAX_LOSS_PCT = 2.0  # stop opening trades for the day after this equity drawdown
MAX_TOTAL_LOSS_PCT = 10.0 # hard kill switch: stop the bot for good if equity falls
                          # this far below the equity it launched with (0 = off)
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
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BACKOFF_SECONDS = 5
ORDER_RETRIES = 3         # retries on requote / price-changed
TRADE_LOG_CSV = "exness_bot/logs/trades.csv"

# ---------------- Strategy ----------------
SMA_FAST = 20
SMA_SLOW = 50
RSI_PERIOD = 14

# ---------------- Backtest ----------------
BT_SPREAD_POINTS = 12     # assumed round-trip spread cost per trade, in points
BT_COMMISSION_PER_LOT = 7.0   # USD per lot round-trip (Exness Raw/Zero style); 0 for Standard
BT_START_BALANCE = 1000.0

# ---------------- Strategy Selector ----------------
ACTIVE_STRATEGY = "smc"   # "sma" | "smc" | "vp_breakout"

# ---------------- SMC XAUUSD M5 ----------------
SMC_SYMBOL = "XAUUSD"
SMC_PRIMARY_TF = _M5
SMC_STRUCTURE_TF = _M15
SMC_TREND_TF = _H1
SMC_LOOKBACK_M5 = 500
SMC_LOOKBACK_M15 = 200
SMC_LOOKBACK_H1 = 300
SMC_MIN_SCORE = 6
SMC_COOLDOWN_BARS = 8
SMC_TP1_R = 1.5
SMC_TP2_R = 2.5
SMC_PARTIAL_CLOSE_PCT = 0.5
SMC_SL_ATR_BUFFER = 0.15
SMC_DISPLACEMENT_ATR = 0.55
SMC_BODY_FRAC = 0.55
SMC_SWING_LOOKBACK = 3
SMC_SIGNAL_LOOKBACK = 12   # candles back to detect sweep / BOS (~1 hour on M5)
SMC_ATR_PERIOD = 14
SMC_USE_VP_CONFLUENCE = True
SMC_VP_BIN_SIZE = 1.0
SMC_USE_H1_TREND = True
SMC_SPREAD_FILTER_POINTS = 40
SMC_SESSION_LONDON = (7, 11.5)
SMC_SESSION_NY = (13, 17.5)
SMC_SESSION_ASIAN = (23, 5)       # Tokyo session (wraps midnight)
SMC_USE_ASIAN_SESSION = False     # enable to trade Asian session setups
SMC_USE_VOLUME_CONFIRM = True     # above-average volume adds +1 score
SMC_USE_REGIME_FILTER = True      # penalize score in ranging markets (ADX-based)
SMC_REGIME_PENALTY = 2            # score deducted when market is ranging
SMC_VOLATILITY_PENALTY = 2        # score deducted on abnormal volatility spike
SMC_ADX_PERIOD = 14
SMC_ADX_RANGE_THRESHOLD = 20     # ADX below this = ranging market, hold
SMC_USE_NEWS_FILTER = True        # hold on abnormal volatility spikes (news proxy)
SMC_NEWS_VOLATILITY_MULT = 2.5   # current ATR / avg ATR above this = spike

# ---- Volume (graduated 0/1/2) ----
SMC_VOLUME_DELTA_LOOKBACK = 20
SMC_VOLUME_OB_MULTIPLIER = 1.0   # OB candle volume must exceed avg * this

# ---- Session quality / killzones ----
SMC_KILLZONE_LONDON = (7, 9)
SMC_KILLZONE_NY = (13, 15)
SMC_KILLZONE_OVERLAP = (13, 16)
SMC_KILLZONE_ASIAN = (0, 3)
SMC_USE_DST_ADJUST = True
SMC_USE_SESSION_QUALITY = True

# ---- News calendar ----
SMC_NEWS_BLACKOUT_BEFORE_MIN = 15
SMC_NEWS_BLACKOUT_AFTER_MIN = 10
SMC_NEWS_USE_MT5_CALENDAR = True
SMC_NEWS_USE_STATIC_SCHEDULE = True
SMC_NEWS_HIGH_IMPACT_ONLY = True
SMC_FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]

# ---- Regime detection (multi-indicator) ----
SMC_REGIME_BB_PERIOD = 20
SMC_REGIME_BB_STD = 2.0
SMC_REGIME_BB_SQUEEZE_PCT = 20
SMC_REGIME_ATR_FAST = 7
SMC_REGIME_ATR_SLOW = 50
SMC_REGIME_ATR_COMPRESS_RATIO = 0.75
SMC_REGIME_MIN_RANGING_SIGNALS = 2

# ---- Backtest validation ----
SMC_BT_WALK_FORWARD_WINDOWS = 6
SMC_BT_SENSITIVITY_PCT = [10, 20]
SMC_BT_MONTE_CARLO_RUNS = 1000
