"""Pure indicator math shared by the live bot and the backtester.

No MT5 / broker imports here on purpose so backtest.py can run anywhere.
"""

import pandas as pd

from exness_bot import config


def rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def atr(df, period):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def add_indicators(df):
    """Add sma_fast / sma_slow / rsi / atr / trend columns in place and return df."""
    df["sma_fast"] = df["close"].rolling(config.SMA_FAST).mean()
    df["sma_slow"] = df["close"].rolling(config.SMA_SLOW).mean()
    df["rsi"] = rsi(df["close"], config.RSI_PERIOD)
    df["atr"] = atr(df, config.ATR_PERIOD)
    # higher-timeframe-ish trend proxy: slope of a longer SMA on this timeframe
    df["trend_sma"] = df["close"].rolling(config.TREND_SMA).mean()
    df["trend_up"] = df["trend_sma"] > df["trend_sma"].shift(config.TREND_SLOPE_LOOKBACK)
    df["trend_down"] = df["trend_sma"] < df["trend_sma"].shift(config.TREND_SLOPE_LOOKBACK)
    return df


def trailing_sl(side, entry, current_sl, atr, price):
    """Pure break-even + ATR-trail stop math shared by the bot and backtester.

    Returns a new SL price, or None to leave the stop where it is. Never loosens.
    """
    is_long = side == "buy"
    risk_dist = abs(entry - current_sl) if current_sl else config.SL_ATR_MULT * atr
    if risk_dist <= 0:
        return None
    profit_r = ((price - entry) if is_long else (entry - price)) / risk_dist

    candidates = []
    if config.BREAKEVEN_AT_R and profit_r >= config.BREAKEVEN_AT_R:
        candidates.append(entry)
    if config.TRAIL_AT_R and profit_r >= config.TRAIL_AT_R:
        candidates.append(price - config.TRAIL_ATR_MULT * atr if is_long
                          else price + config.TRAIL_ATR_MULT * atr)
    if not candidates:
        return None

    new_sl = max(candidates) if is_long else min(candidates)
    if current_sl:
        if is_long and new_sl <= current_sl:
            return None
        if not is_long and new_sl >= current_sl:
            return None
    return new_sl


def session_ok(ts):
    """True if timestamp `ts` (UTC) is inside config's trading day/hour window."""
    if config.TRADE_DAYS and ts.weekday() not in config.TRADE_DAYS:
        return False
    hours = config.SESSION_UTC_HOURS
    if not hours:
        return True
    start, end = hours
    return start <= ts.hour < end


def snapshot(df):
    """Compact dict of the latest closed bar for the strategy / LLM."""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    return {
        "time": str(last["time"]),
        "close": round(float(last["close"]), 6),
        "sma_fast": round(float(last["sma_fast"]), 6),
        "sma_slow": round(float(last["sma_slow"]), 6),
        "sma_fast_prev": round(float(prev["sma_fast"]), 6),
        "sma_slow_prev": round(float(prev["sma_slow"]), 6),
        "rsi": round(float(last["rsi"]), 2),
        "atr": round(float(last["atr"]), 6),
        "trend_up": bool(last["trend_up"]),
        "trend_down": bool(last["trend_down"]),
        "last_10_closes": [round(float(c), 6) for c in df["close"].tail(10)],
    }
