"""Unit tests for the enhanced SMC XAUUSD M5 strategy."""

import unittest
from datetime import datetime, time, timezone
from unittest.mock import patch

import pandas as pd
import numpy as np

from exness_bot.smc_strategy import SMCStrategy
from exness_bot import config


def _make_m5(n=100, base=2000.0, trend=0.1, session_hour=9):
    """Generate synthetic M5 OHLC with controllable swing structure."""
    times = pd.date_range(
        datetime(2026, 1, 5, session_hour, 0), periods=n, freq="5min", tz=timezone.utc
    )
    close = [base + i * trend + (2.0 if (i // 10) % 2 else 0) for i in range(n)]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({"time": times, "open": opens, "high": high, "low": low, "close": close})


def _make_m15(n=60, base=2000.0, trend=0.3, session_hour=9):
    times = pd.date_range(
        datetime(2026, 1, 5, session_hour, 0), periods=n, freq="15min", tz=timezone.utc
    )
    close = [base + i * trend + (3.0 if (i // 8) % 2 else 0) for i in range(n)]
    high = [c + 1.5 for c in close]
    low = [c - 1.5 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({"time": times, "open": opens, "high": high, "low": low, "close": close})


def _make_h1(n=300, base=2000.0, trend=0.5):
    times = pd.date_range(
        datetime(2025, 12, 1, 0, 0), periods=n, freq="1h", tz=timezone.utc
    )
    close = [base + i * trend for i in range(n)]
    high = [c + 2.0 for c in close]
    low = [c - 2.0 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({"time": times, "open": opens, "high": high, "low": low, "close": close})


class TestSMCStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = SMCStrategy()

    def test_hold_on_insufficient_m5_candles(self):
        m5 = _make_m5(n=30)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("not enough candles", result["reason"])

    def test_hold_on_insufficient_m15_candles(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=10)
        result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("not enough candles", result["reason"])

    def test_hold_outside_session(self):
        m5 = _make_m5(n=100, session_hour=18)
        m15 = _make_m15(n=60, session_hour=18)
        result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("outside", result["reason"])

    def test_hold_during_cooldown(self):
        self.strategy.last_trade = 95
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("cooldown", result["reason"])

    def test_hold_on_wide_spread(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15, spread_points=100)
        self.assertEqual(result["action"], "hold")
        self.assertIn("spread", result["reason"])

    def test_decision_returns_required_keys(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15)
        self.assertIn("action", result)
        self.assertIn("confidence", result)
        self.assertIn("reason", result)
        self.assertIn(result["action"], {"buy", "sell", "hold"})

    def test_confidence_bounded_0_to_1(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15)
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_bias_detection_bullish(self):
        s = self.strategy
        m15 = _make_m15(n=60, trend=0.5)
        bias = s._m15_bias(s._clean(m15))
        self.assertEqual(bias, 1)

    def test_bias_detection_bearish(self):
        s = self.strategy
        m15 = _make_m15(n=60, trend=-0.5)
        bias = s._m15_bias(s._clean(m15))
        self.assertEqual(bias, -1)

    def test_hold_returns_hold_dict(self):
        result = self.strategy._hold("test reason", score=5)
        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["reason"], "test reason")

    def test_entry_returns_sl_tp_keys(self):
        """If the strategy returns buy/sell it must include sl/tp1/tp2/entry."""
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        result = self.strategy.decide(m5, m15)
        if result["action"] in ("buy", "sell"):
            for key in ("entry", "sl", "tp1", "tp2", "risk_distance"):
                self.assertIn(key, result, f"Missing key: {key}")
            self.assertGreater(result["risk_distance"], 0)

    def test_vp_confluence_returns_false_when_none(self):
        self.assertFalse(self.strategy._vp_confluence(2000, None, 5.0, True))

    def test_session_london(self):
        ts = pd.Timestamp("2026-01-05 09:00:00")
        self.assertTrue(self.strategy._in_session(ts))

    def test_session_ny(self):
        ts = pd.Timestamp("2026-01-05 14:30:00")
        self.assertTrue(self.strategy._in_session(ts))

    def test_session_off_hours(self):
        ts = pd.Timestamp("2026-01-05 03:00:00")
        self.assertFalse(self.strategy._in_session(ts))

    # ---- regime filter ----

    def test_regime_filter_ranging_hold(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        with patch.object(self.strategy, '_is_ranging', return_value=True):
            result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("ranging", result["reason"])

    def test_regime_filter_disabled_passes(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        with patch.object(config, 'SMC_USE_REGIME_FILTER', False), \
             patch.object(self.strategy, '_is_ranging', return_value=True):
            result = self.strategy.decide(m5, m15)
        self.assertNotIn("ranging", result.get("reason", ""))

    # ---- news / volatility filter ----

    def test_volatility_spike_hold(self):
        m5 = _make_m5(n=100)
        m15 = _make_m15(n=60)
        with patch.object(self.strategy, '_volatility_spike', return_value=True):
            result = self.strategy.decide(m5, m15)
        self.assertEqual(result["action"], "hold")
        self.assertIn("volatility", result["reason"])

    # ---- Asian session ----

    def test_asian_session_enabled(self):
        with patch.object(config, 'SMC_USE_ASIAN_SESSION', True):
            ts = pd.Timestamp("2026-01-05 02:00:00")
            self.assertTrue(self.strategy._in_session(ts))

    def test_asian_session_disabled(self):
        ts = pd.Timestamp("2026-01-05 02:00:00")
        self.assertFalse(self.strategy._in_session(ts))


class TestSMCHelpers(unittest.TestCase):

    def test_atr_computation(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        atr = s._atr(m5_clean)
        self.assertTrue(atr.iloc[-1] > 0)

    def test_swing_detection(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        sw = s._swings(m5_clean)
        self.assertIn("h", sw)
        self.assertIn("l", sw)
        self.assertGreater(len(sw["h"]), 0)
        self.assertGreater(len(sw["l"]), 0)

    def test_fvg_needs_3_candles(self):
        s = SMCStrategy()
        m5 = _make_m5(n=2)
        m5_clean = s._clean(m5)
        self.assertFalse(s._fvg(m5_clean, True))

    def test_equilibrium_returns_midpoint(self):
        s = SMCStrategy()
        sw = {"h": [(10, 2010.0)], "l": [(5, 1990.0)]}
        mid = s._equilibrium(sw)
        self.assertEqual(mid, 2000.0)

    def test_equilibrium_none_when_no_swings(self):
        s = SMCStrategy()
        self.assertIsNone(s._equilibrium({"h": [], "l": []}))

    # ---- ADX / regime ----

    def test_adx_computation(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        adx = s._adx(m5_clean)
        self.assertEqual(len(adx), len(m5_clean))
        self.assertTrue(pd.notna(adx.iloc[-1]))

    def test_is_ranging_returns_bool(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        result = s._is_ranging(m5_clean)
        self.assertIsInstance(result, bool)

    # ---- volatility spike ----

    def test_volatility_spike_normal_data(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        atr_series = s._atr(m5_clean)
        atr = atr_series.iloc[-1]
        self.assertFalse(s._volatility_spike(atr_series, atr))

    # ---- volume ----

    def test_volume_score_with_tick_volume(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5["tick_volume"] = [100] * 99 + [200]
        m5_clean = s._clean(m5)
        score = s._volume_score(m5_clean)
        self.assertEqual(score, 1)

    def test_volume_score_no_volume_col(self):
        s = SMCStrategy()
        m5 = _make_m5(n=100)
        m5_clean = s._clean(m5)
        score = s._volume_score(m5_clean)
        self.assertEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
