"""Broker-independent OHLC validation used before strategy analysis."""

import datetime as _dt

import numpy as np

from exness_bot import config


def validate_frame(df, *, now=None, require_fresh=False):
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"market data missing columns: {sorted(missing)}")
    if len(df) < 2:
        raise ValueError("market data needs at least two candles")
    times = df["time"]
    if times.isna().any() or times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError("market data times must be unique and increasing")
    prices = df[["open", "high", "low", "close"]].apply(lambda col: np.isfinite(col.astype(float)))
    if not prices.all().all():
        raise ValueError("market data contains non-finite prices")
    if (df["high"] < df[["open", "close"]].max(axis=1)).any():
        raise ValueError("high price is below open/close")
    if (df["low"] > df[["open", "close"]].min(axis=1)).any():
        raise ValueError("low price is above open/close")
    if require_fresh:
        latest = times.iloc[-1]
        if hasattr(latest, "to_pydatetime"):
            latest = latest.to_pydatetime()
        current = now or _dt.datetime.utcnow()
        if getattr(latest, "tzinfo", None) is not None:
            latest = latest.replace(tzinfo=None)
        if getattr(current, "tzinfo", None) is not None:
            current = current.replace(tzinfo=None)
        age = (current - latest).total_seconds()
        if age < 0 or age > config.MAX_DATA_AGE_SECONDS:
            raise ValueError(f"market data is stale ({age:.0f}s old)")
    return True
