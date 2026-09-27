"""Versioned, pure-Python V2 candidate filters and trailing exit.

This module is deliberately separate from the frozen legacy strategy.  It implements
only the four amendments in the second reference PDF; callers must enable each
variant independently and record its version and experiment evidence.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable, Mapping, Optional, Sequence, Tuple

V1 = "VP_BREAKOUT_M5_V1"
V1A = "VP_BREAKOUT_M5_V1a"
V1B = "VP_BREAKOUT_M5_V1b"
V1C = "VP_BREAKOUT_M5_V1c"
V1D = "VP_BREAKOUT_M5_V1d"
V2_TRAIL = "VP_BREAKOUT_M5_V2_TRAIL"
V2 = "VP_BREAKOUT_M5_V2"


@dataclass(frozen=True)
class V2FilterConfig:
    """Predefined candidate parameters; never optimize them inside execution."""

    trend_enabled: bool = False
    volatility_enabled: bool = False
    strength_enabled: bool = False
    min_breakout_strength: float = 0.20
    atr_lower_multiplier: float = 0.8
    atr_upper_multiplier: float = 2.0
    trail_enabled: bool = False
    trail_mult: float = 2.0


def _finite(value) -> bool:
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _time_before(value, cutoff: datetime) -> bool:
    """Compare timestamps without accepting a forming/equal-timeframe candle."""
    if value is None:
        return False
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value < cutoff


def ema(values: Sequence[float], period: int) -> list:
    """Return an EMA with an SMA seed and NaN until enough observations exist."""
    if period <= 0:
        raise ValueError("period must be positive")
    out = [float("nan")] * len(values)
    clean = [float(v) if _finite(v) else float("nan") for v in values]
    if len(clean) < period or any(not _finite(v) for v in clean[:period]):
        return out
    seed = sum(clean[:period]) / period
    out[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    previous = seed
    for index in range(period, len(clean)):
        if not _finite(clean[index]):
            previous = float("nan")
            continue
        if not _finite(previous):
            out[index] = float("nan")
            continue
        previous = alpha * clean[index] + (1.0 - alpha) * previous
        out[index] = previous
    return out


def higher_timeframe_trend(
    h1_candles: Iterable[Mapping], signal_time: datetime, ema_fast: int = 50, ema_slow: int = 200
) -> str:
    """Return BULLISH, BEARISH, or NEUTRAL using only closed H1 data before signal_time."""
    closed = [c for c in h1_candles if _time_before(c.get("time"), signal_time)]
    closes = [c.get("close") for c in closed]
    fast = ema(closes, ema_fast)
    slow = ema(closes, ema_slow)
    if not closed or not _finite(fast[-1]) or not _finite(slow[-1]) or not _finite(closes[-1]):
        return "NEUTRAL"
    if closes[-1] > slow[-1] and fast[-1] > slow[-1]:
        return "BULLISH"
    if closes[-1] < slow[-1] and fast[-1] < slow[-1]:
        return "BEARISH"
    return "NEUTRAL"


def trend_filter(side: str, h1_candles: Iterable[Mapping], signal_time: datetime) -> Tuple[bool, str]:
    trend = higher_timeframe_trend(h1_candles, signal_time)
    expected = "BULLISH" if side == "buy" else "BEARISH"
    return (trend == expected, "trend_filter_pass" if trend == expected else "trend_filter_block")


def volatility_filter(current_atr: float, atr_values: Sequence[float], config: V2FilterConfig = V2FilterConfig()) -> Tuple[bool, str]:
    """Require current ATR strictly inside the configured band around its 20-value average."""
    if not _finite(current_atr) or len(atr_values) < 20:
        return False, "volatility_filter_block"
    recent = [float(v) for v in atr_values[-20:] if _finite(v)]
    if len(recent) != 20:
        return False, "volatility_filter_block"
    average = sum(recent) / 20.0
    valid = average > 0 and config.atr_lower_multiplier * average < current_atr < config.atr_upper_multiplier * average
    return (valid, "volatility_filter_pass" if valid else "volatility_filter_block")


def breakout_strength_filter(side: str, close: float, level: float, current_atr: float, config: V2FilterConfig = V2FilterConfig()) -> Tuple[bool, str]:
    if not all(_finite(v) for v in (close, level, current_atr)) or current_atr <= 0 or config.min_breakout_strength < 0:
        return False, "weak_breakout_block"
    distance = close - level if side == "buy" else level - close
    valid = distance >= config.min_breakout_strength * current_atr
    return (valid, "weak_breakout_pass" if valid else "weak_breakout_block")


def validate_setup(
    side: str,
    close: float,
    level: float,
    current_atr: float,
    atr_values: Sequence[float],
    h1_candles: Iterable[Mapping],
    signal_time: datetime,
    config: V2FilterConfig = V2FilterConfig(),
) -> Tuple[bool, str]:
    """Apply enabled V2 filters in deterministic order and return an auditable reason."""
    if config.trend_enabled:
        passed, reason = trend_filter(side, h1_candles, signal_time)
        if not passed:
            return False, reason
    if config.volatility_enabled:
        passed, reason = volatility_filter(current_atr, atr_values, config)
        if not passed:
            return False, reason
    if config.strength_enabled:
        passed, reason = breakout_strength_filter(side, close, level, current_atr, config)
        if not passed:
            return False, reason
    return True, "v2_filters_pass"


def trailing_stop(
    side: str,
    entry_price: float,
    initial_sl: float,
    current_sl: float,
    market_price: float,
    highest_close: float,
    lowest_close: float,
    current_atr: float,
    trail_mult: float = 2.0,
) -> Tuple[Optional[float], str]:
    """Return a monotonic V2 trail using immutable initial risk.

    The stop reaches breakeven only at +1R.  Trailing uses the highest/lowest
    close since entry and never recomputes R from a moved stop.
    """
    values = (entry_price, initial_sl, current_sl, market_price, highest_close, lowest_close, current_atr)
    if not all(_finite(v) for v in values) or current_atr <= 0 or trail_mult <= 0:
        return None, "trail_invalid"
    risk = abs(entry_price - initial_sl)
    if risk <= 0:
        return None, "trail_invalid"
    profit = market_price - entry_price if side == "buy" else entry_price - market_price
    if profit < risk:
        return None, "trail_wait_1R"
    if side == "buy":
        candidate = max(entry_price, highest_close - trail_mult * current_atr)
        if candidate <= current_sl:
            return None, "trail_unchanged"
    else:
        candidate = min(entry_price, lowest_close + trail_mult * current_atr)
        if candidate >= current_sl:
            return None, "trail_unchanged"
    return candidate, "trail_update"
