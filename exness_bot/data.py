"""Turn MT5 rates into a DataFrame and compute the indicators the strategy needs."""

import pandas as pd

from exness_bot import config
from exness_bot import mt5_client


def _rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def _atr(df, period):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def load_frame():
    """Return a DataFrame of closed candles with indicator columns.

    The most recent (still forming) candle is dropped so signals only fire on
    completed bars.
    """
    raw = mt5_client.rates(config.SYMBOL, config.TIMEFRAME, config.LOOKBACK_BARS)
    if raw is None or len(raw) < config.SMA_SLOW + 5:
        raise RuntimeError("Not enough price history returned from MT5")

    df = pd.DataFrame(raw)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.iloc[:-1].reset_index(drop=True)  # drop the forming candle

    df["sma_fast"] = df["close"].rolling(config.SMA_FAST).mean()
    df["sma_slow"] = df["close"].rolling(config.SMA_SLOW).mean()
    df["rsi"] = _rsi(df["close"], config.RSI_PERIOD)
    df["atr"] = _atr(df, config.ATR_PERIOD)
    return df


def snapshot(df):
    """Compact dict of the latest bar, safe to hand to the LLM or the rules."""
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
        "last_10_closes": [round(float(c), 6) for c in df["close"].tail(10)],
    }
