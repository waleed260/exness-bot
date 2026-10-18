"""Multi-indicator regime detection: ADX (Wilder) + Bollinger Band width + ATR compression."""

import pandas as pd
import numpy as np

from exness_bot import config

TRENDING = "TRENDING"
RANGING = "RANGING"
TRANSITIONAL = "TRANSITIONAL"


def _wilder_smooth(series, period):
    """Wilder's exponential smoothing (alpha = 1/period)."""
    result = series.copy()
    result.iloc[:period] = np.nan
    result.iloc[period - 1] = series.iloc[:period].mean()
    for i in range(period, len(series)):
        result.iloc[i] = result.iloc[i - 1] + (series.iloc[i] - result.iloc[i - 1]) / period
    return result


def adx(d, period=None):
    """Compute ADX with proper Wilder smoothing. Returns (adx_series, plus_di, minus_di)."""
    if period is None:
        period = config.SMC_ADX_PERIOD
    high, low, close = d.high, d.low, d.close

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr_s = _wilder_smooth(tr, period)
    safe_atr = atr_s.replace(0, 1e-9)

    plus_di = 100 * _wilder_smooth(plus_dm, period) / safe_atr
    minus_di = 100 * _wilder_smooth(minus_dm, period) / safe_atr

    denom = (plus_di + minus_di).replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / denom
    adx_val = _wilder_smooth(dx, period)

    return adx_val, plus_di, minus_di


def adx_slope(adx_series, lookback=5):
    """Positive = trend strengthening, negative = weakening."""
    if len(adx_series) < lookback + 1:
        return 0.0
    cur = adx_series.iloc[-1]
    prev = adx_series.iloc[-1 - lookback]
    if pd.isna(cur) or pd.isna(prev):
        return 0.0
    return float(cur - prev)


def bb_width(close, period=None, std_mult=None):
    """Bollinger Band width = (upper - lower) / middle."""
    if period is None:
        period = config.SMC_REGIME_BB_PERIOD
    if std_mult is None:
        std_mult = config.SMC_REGIME_BB_STD
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    safe_mid = middle.replace(0, 1e-9)
    return (upper - lower) / safe_mid


def bb_squeeze(close, period=None, lookback=50):
    """True if current BB width is below the squeeze_pct percentile of recent width."""
    width = bb_width(close, period)
    if len(width) < lookback + 1:
        return False
    current = width.iloc[-1]
    if pd.isna(current):
        return False
    recent = width.iloc[-lookback - 1:-1].dropna()
    if len(recent) < 10:
        return False
    threshold = np.percentile(recent, config.SMC_REGIME_BB_SQUEEZE_PCT)
    return bool(current < threshold)


def atr_compression(d, fast=None, slow=None):
    """True if fast ATR / slow ATR < compression ratio (volatility contraction)."""
    if fast is None:
        fast = config.SMC_REGIME_ATR_FAST
    if slow is None:
        slow = config.SMC_REGIME_ATR_SLOW
    pc = d.close.shift()
    tr = pd.concat([
        d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs(),
    ], axis=1).max(axis=1)
    atr_fast = tr.rolling(fast).mean().iloc[-1]
    atr_slow = tr.rolling(slow).mean().iloc[-1]
    if pd.isna(atr_fast) or pd.isna(atr_slow) or atr_slow <= 0:
        return False
    return bool(atr_fast / atr_slow < config.SMC_REGIME_ATR_COMPRESS_RATIO)


def detect_regime(d, period=None):
    """Returns TRENDING, RANGING, or TRANSITIONAL based on multi-indicator consensus."""
    if period is None:
        period = config.SMC_ADX_PERIOD

    adx_val, plus_di, minus_di = adx(d, period)
    current_adx = adx_val.iloc[-1] if not pd.isna(adx_val.iloc[-1]) else 0.0
    slope = adx_slope(adx_val)

    ranging_signals = 0

    if current_adx < config.SMC_ADX_RANGE_THRESHOLD:
        ranging_signals += 1

    if bb_squeeze(d.close):
        ranging_signals += 1

    if atr_compression(d):
        ranging_signals += 1

    if current_adx > 25 and slope > 0 and not bb_squeeze(d.close):
        return TRENDING

    min_signals = config.SMC_REGIME_MIN_RANGING_SIGNALS
    if ranging_signals >= min_signals:
        return RANGING
    if ranging_signals >= 1:
        return TRANSITIONAL
    return TRENDING
