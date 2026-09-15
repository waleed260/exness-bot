"""Deterministic rule-based trading decisions.

The strategy uses a fast/slow SMA crossover filtered by RSI and the long-term
trend. It returns buy, sell, close, or hold (no-trade).
"""

import math

from exness_bot.logger import log
from exness_bot import config

VALID_ACTIONS = {"buy", "sell", "close", "hold"}


def rule_based(snap, position_side):
    """Return a deterministic decision from the latest closed-candle snapshot."""
    required = ("sma_fast_prev", "sma_slow_prev", "sma_fast", "sma_slow", "rsi", "atr")
    try:
        if any(not math.isfinite(float(snap[key])) for key in required):
            return {"action": "hold", "confidence": 0.0, "reason": "invalid or incomplete market data"}
    except (KeyError, TypeError, ValueError):
        return {"action": "hold", "confidence": 0.0, "reason": "invalid or incomplete market data"}

    crossed_up = (
        snap["sma_fast_prev"] <= snap["sma_slow_prev"]
        and snap["sma_fast"] > snap["sma_slow"]
    )
    crossed_down = (
        snap["sma_fast_prev"] >= snap["sma_slow_prev"]
        and snap["sma_fast"] < snap["sma_slow"]
    )
    rsi = snap["rsi"]

    if position_side == "buy" and crossed_down:
        return {"action": "close", "confidence": 0.7, "reason": "fast SMA crossed below slow SMA"}
    if position_side == "sell" and crossed_up:
        return {"action": "close", "confidence": 0.7, "reason": "fast SMA crossed above slow SMA"}

    trend_ok_long = (not config.USE_TREND_FILTER) or snap.get("trend_up")
    trend_ok_short = (not config.USE_TREND_FILTER) or snap.get("trend_down")

    if position_side is None:
        if crossed_up and rsi < 70 and trend_ok_long:
            return {"action": "buy", "confidence": 0.62,
                    "reason": "bullish SMA crossover with trend, RSI ok"}
        if crossed_down and rsi > 30 and trend_ok_short:
            return {"action": "sell", "confidence": 0.62,
                    "reason": "bearish SMA crossover with trend, RSI ok"}

    return {"action": "hold", "confidence": 0.5, "reason": "no aligned crossover"}


def decide(snap, position_side):
    """Public strategy entry point; always uses the deterministic rule engine."""
    decision = rule_based(snap, position_side)
    log.logger.info(f"Rule-based decision: {decision}")
    return decision
