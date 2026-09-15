import unittest

import pandas as pd

from exness_bot import backtest, indicators, strategy


class StrategyTests(unittest.TestCase):
    def test_invalid_snapshot_is_no_trade(self):
        decision = strategy.rule_based({"rsi": float("nan")}, None)
        self.assertEqual(decision["action"], "hold")
        self.assertEqual(decision["confidence"], 0.0)

    def test_rule_strategy_buy_sell_and_close_contract(self):
        base = {"sma_fast_prev": 1.0, "sma_slow_prev": 1.1, "sma_fast": 1.2,
                "sma_slow": 1.1, "rsi": 55, "atr": 0.01, "trend_up": True, "trend_down": False}
        self.assertEqual(strategy.rule_based(base, None)["action"], "buy")
        reverse = dict(base, sma_fast_prev=1.2, sma_slow_prev=1.1, sma_fast=1.0, trend_up=False, trend_down=True, rsi=45)
        self.assertEqual(strategy.rule_based(reverse, None)["action"], "sell")
        self.assertEqual(strategy.rule_based(reverse, "buy")["action"], "close")

    def test_indicator_snapshot_contains_expected_fields(self):
        close = [100 + i * 0.02 for i in range(260)]
        df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=260, freq="15min"),
                           "open": close, "high": [x + 0.1 for x in close],
                           "low": [x - 0.1 for x in close], "close": close})
        snap = indicators.snapshot(indicators.add_indicators(df))
        self.assertIn("sma_fast", snap)
        self.assertIn("atr", snap)
        self.assertTrue(snap["trend_up"])

    def test_backtest_runs_on_historical_dataframe(self):
        close = [100 + i * 0.02 + (0.4 if (i // 8) % 2 else 0) for i in range(320)]
        df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=320, freq="15min"),
                           "open": close, "high": [x + 0.1 for x in close],
                           "low": [x - 0.1 for x in close], "close": close})
        result = backtest.run(df, 0.01)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
