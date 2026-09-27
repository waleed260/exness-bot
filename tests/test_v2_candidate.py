import unittest
from datetime import datetime, timedelta

from exness_bot.v2_candidate import (
    V2FilterConfig, breakout_strength_filter, higher_timeframe_trend,
    trend_filter, trailing_stop, validate_setup, volatility_filter,
)


class V2CandidateTests(unittest.TestCase):
    def test_h1_trend_uses_only_strictly_prior_closed_candles(self):
        start = datetime(2020, 1, 1)
        candles = [{"time": start + timedelta(hours=i), "close": 100 + i * 0.2} for i in range(220)]
        signal = start + timedelta(hours=220)
        self.assertEqual(higher_timeframe_trend(candles, signal), "BULLISH")
        candles.append({"time": signal, "close": 1.0})
        self.assertEqual(higher_timeframe_trend(candles, signal), "BULLISH")
        self.assertEqual(trend_filter("sell", candles, signal)[1], "trend_filter_block")

    def test_h1_neutral_and_insufficient_history_block(self):
        now = datetime(2026, 1, 1)
        candles = [{"time": now - timedelta(hours=i + 1), "close": 100.0} for i in range(20)]
        self.assertEqual(higher_timeframe_trend(candles, now), "NEUTRAL")
        self.assertEqual(trend_filter("buy", candles, now), (False, "trend_filter_block"))

    def test_volatility_filter_requires_strict_band_and_history(self):
        values = [1.0] * 20
        self.assertEqual(volatility_filter(1.0, values)[0], True)
        self.assertEqual(volatility_filter(0.8, values)[1], "volatility_filter_block")
        self.assertEqual(volatility_filter(2.0, values)[1], "volatility_filter_block")
        self.assertEqual(volatility_filter(1.0, values[:19])[1], "volatility_filter_block")

    def test_breakout_strength_is_directional_and_atr_scaled(self):
        cfg = V2FilterConfig(min_breakout_strength=0.2)
        self.assertEqual(breakout_strength_filter("buy", 101.0, 100.0, 5.0, cfg)[0], True)
        self.assertEqual(breakout_strength_filter("buy", 100.9, 100.0, 5.0, cfg)[1], "weak_breakout_block")
        self.assertEqual(breakout_strength_filter("sell", 99.0, 100.0, 5.0, cfg)[0], True)

    def test_filters_are_independently_toggleable(self):
        now = datetime(2026, 1, 1)
        cfg = V2FilterConfig(strength_enabled=True, min_breakout_strength=0.2)
        ok, reason = validate_setup("buy", 101.0, 100.0, 5.0, [5.0] * 20, [], now, cfg)
        self.assertEqual((ok, reason), (True, "v2_filters_pass"))
        cfg = V2FilterConfig(volatility_enabled=True)
        self.assertEqual(validate_setup("buy", 101.0, 100.0, 5.0, [5.0] * 19, [], now, cfg)[1], "volatility_filter_block")

    def test_trailing_uses_initial_risk_and_never_loosens_buy(self):
        # Initial risk is 10, even though the current stop was already moved to 105.
        self.assertEqual(trailing_stop("buy", 100, 90, 105, 109, 112, 100, 2, 2.0)[1], "trail_wait_1R")
        stop, reason = trailing_stop("buy", 100, 90, 100, 111, 115, 100, 2, 2.0)
        self.assertEqual(reason, "trail_update")
        self.assertEqual(stop, 111.0)
        self.assertIsNone(trailing_stop("buy", 100, 90, 115, 111, 115, 100, 2, 2.0)[0])

    def test_trailing_sell_is_monotonic(self):
        stop, reason = trailing_stop("sell", 100, 110, 110, 89, 100, 85, 2, 2.0)
        self.assertEqual((stop, reason), (89.0, "trail_update"))
        self.assertIsNone(trailing_stop("sell", 100, 110, 85, 89, 100, 85, 2, 2.0)[0])


if __name__ == "__main__":
    unittest.main()
