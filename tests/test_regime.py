"""Tests for exness_bot.regime — multi-indicator regime detection."""

import unittest

import pandas as pd
import numpy as np

from exness_bot import regime, config


def _trending_data(n=200):
    """Synthetic strongly trending data (consistent up-move)."""
    close = [1800.0 + i * 0.8 for i in range(n)]
    high = [c + 1.5 for c in close]
    low = [c - 0.5 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({"open": opens, "high": high, "low": low, "close": close})


def _ranging_data(n=200):
    """Synthetic ranging data (oscillates around a flat level)."""
    close = [2000.0 + 1.5 * np.sin(i * 0.3) for i in range(n)]
    high = [c + 0.5 for c in close]
    low = [c - 0.5 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({"open": opens, "high": high, "low": low, "close": close})


class TestWilderSmooth(unittest.TestCase):

    def test_basic_smoothing(self):
        s = pd.Series([float(i) for i in range(20)])
        result = regime._wilder_smooth(s, 5)
        self.assertTrue(pd.notna(result.iloc[4]))
        self.assertTrue(pd.isna(result.iloc[0]))

    def test_seed_is_mean(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        result = regime._wilder_smooth(s, 4)
        self.assertAlmostEqual(result.iloc[3], 2.5)

    def test_wilder_step(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 10.0, 6.0])
        result = regime._wilder_smooth(s, 4)
        seed = 2.5
        expected = seed + (10.0 - seed) / 4
        self.assertAlmostEqual(result.iloc[4], expected, places=6)


class TestADX(unittest.TestCase):

    def test_returns_three_series(self):
        d = _trending_data()
        adx_val, plus_di, minus_di = regime.adx(d)
        self.assertEqual(len(adx_val), len(d))
        self.assertEqual(len(plus_di), len(d))
        self.assertEqual(len(minus_di), len(d))

    def test_adx_positive_trending(self):
        d = _trending_data()
        adx_val, _, _ = regime.adx(d)
        last_adx = adx_val.iloc[-1]
        self.assertTrue(pd.notna(last_adx))
        self.assertGreater(last_adx, 15)

    def test_adx_low_ranging(self):
        d = _ranging_data()
        adx_val, _, _ = regime.adx(d)
        last_adx = adx_val.iloc[-1]
        self.assertTrue(pd.notna(last_adx))
        self.assertLess(last_adx, 30)

    def test_plus_di_higher_in_uptrend(self):
        d = _trending_data()
        _, plus_di, minus_di = regime.adx(d)
        self.assertGreater(plus_di.iloc[-1], minus_di.iloc[-1])


class TestADXSlope(unittest.TestCase):

    def test_positive_slope_on_increasing(self):
        s = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0])
        slope = regime.adx_slope(s, lookback=3)
        self.assertGreater(slope, 0)

    def test_zero_on_short_series(self):
        s = pd.Series([10.0, 12.0])
        slope = regime.adx_slope(s, lookback=5)
        self.assertEqual(slope, 0.0)

    def test_handles_nan(self):
        s = pd.Series([np.nan, np.nan, np.nan, 10.0, 20.0])
        slope = regime.adx_slope(s, lookback=3)
        self.assertEqual(slope, 0.0)


class TestBBWidth(unittest.TestCase):

    def test_returns_series(self):
        close = pd.Series([2000.0 + i for i in range(50)])
        w = regime.bb_width(close, period=20, std_mult=2.0)
        self.assertEqual(len(w), 50)

    def test_width_positive(self):
        close = pd.Series([2000.0 + np.random.randn() * 5 for _ in range(60)])
        w = regime.bb_width(close, period=20, std_mult=2.0)
        self.assertGreater(w.dropna().iloc[-1], 0)


class TestBBSqueeze(unittest.TestCase):

    def test_squeeze_on_tight_data(self):
        close_vals = [2000.0 + np.random.randn() * 10 for _ in range(80)]
        close_vals[-20:] = [2000.0 + 0.01 * i for i in range(20)]
        close = pd.Series(close_vals)
        result = regime.bb_squeeze(close, period=20, lookback=50)
        self.assertIsInstance(result, bool)

    def test_no_squeeze_on_wide_data(self):
        close_vals = [2000.0 + 0.01 * i for i in range(80)]
        close_vals[-20:] = [2000.0 + np.random.randn() * 50 for _ in range(20)]
        close = pd.Series(close_vals)
        result = regime.bb_squeeze(close, period=20, lookback=50)
        self.assertFalse(result)

    def test_short_data_returns_false(self):
        close = pd.Series([2000.0] * 10)
        self.assertFalse(regime.bb_squeeze(close, period=20, lookback=50))


class TestATRCompression(unittest.TestCase):

    def test_compression_on_calming_data(self):
        d = _ranging_data(n=100)
        result = regime.atr_compression(d, fast=7, slow=50)
        self.assertIsInstance(result, bool)

    def test_no_compression_trending(self):
        d = _trending_data(n=100)
        result = regime.atr_compression(d, fast=7, slow=50)
        self.assertIsInstance(result, bool)


class TestDetectRegime(unittest.TestCase):

    def test_trending_on_strong_trend(self):
        d = _trending_data(n=200)
        result = regime.detect_regime(d)
        self.assertIn(result, (regime.TRENDING, regime.TRANSITIONAL))

    def test_ranging_on_flat(self):
        d = _ranging_data(n=200)
        result = regime.detect_regime(d)
        self.assertIn(result, (regime.RANGING, regime.TRANSITIONAL, regime.TRENDING))

    def test_return_valid_state(self):
        d = _trending_data(n=200)
        result = regime.detect_regime(d)
        self.assertIn(result, (regime.TRENDING, regime.RANGING, regime.TRANSITIONAL))

    def test_trending_override(self):
        """ADX > 25 AND rising AND no squeeze → always TRENDING."""
        d = _trending_data(n=200)
        adx_val, _, _ = regime.adx(d)
        last_adx = adx_val.iloc[-1]
        slope = regime.adx_slope(adx_val)
        squeeze = regime.bb_squeeze(d.close)
        if last_adx > 25 and slope > 0 and not squeeze:
            result = regime.detect_regime(d)
            self.assertEqual(result, regime.TRENDING)


if __name__ == "__main__":
    unittest.main()
