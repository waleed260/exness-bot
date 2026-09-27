import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from exness_bot.vp_backtest import BacktestConfig, OpenTrade, _exit_for_bar, run


class VPBacktestTests(unittest.TestCase):
    def fixture(self):
        rows = []
        start = datetime(2026, 1, 5, 3, tzinfo=timezone.utc)
        for i in range(20):
            rows.append({"time": start + timedelta(minutes=5 * i), "open": 100.0,
                         "high": 100.1, "low": 99.9, "close": 100.0, "volume": 10})
        rows.append({"time": start + timedelta(minutes=100), "open": 100.0,
                     "high": 101.2, "low": 99.8, "close": 101.0, "volume": 10})
        rows.append({"time": start + timedelta(minutes=105), "open": 100.5,
                     "high": 102.0, "low": 100.4, "close": 101.5, "volume": 10})
        for i in range(22, 30):
            rows.append({"time": start + timedelta(minutes=5 * i), "open": 101.0,
                         "high": 107.0, "low": 100.0, "close": 106.5, "volume": 10})
        return pd.DataFrame(rows)

    def test_calls_phase_b_path_and_sizes_actual_volume(self):
        report = run(self.fixture(), BacktestConfig(min_trades=100, commission_per_lot=2.0))
        self.assertEqual(report["resolution_tier"], "LEVEL_2_OHLC")
        self.assertEqual(report["total_trades"], 1)
        self.assertNotEqual(report["trades"][0]["volume"], 1.0)
        self.assertEqual(report["sample_status"], "INSUFFICIENT SAMPLE")

    def test_full_section_24_report_schema_exists(self):
        report = run(self.fixture(), BacktestConfig(min_trades=100))
        required = {
            "total_trades", "win_rate_percent", "net_profit", "profit_factor",
            "max_drawdown", "expectancy_per_trade", "average_r", "median_r",
            "worst_losing_streak", "spread_cost", "commission_cost", "swap_cost",
            "slippage_cost", "long_results", "short_results", "session_results",
            "month_results", "quarter_results", "regime_results", "skipped_trade_count",
            "top_rejection_reasons", "sample_status",
        }
        self.assertTrue(required.issubset(report))

    def test_entry_bar_both_sl_tp_touched_uses_stop_first(self):
        trade = OpenTrade("buy", datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 99, 101,
                          0.1, 1, 0, 0, 0, "session", "breakout", 1)
        price, reason = _exit_for_bar(trade, {"time": datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
                                              "open": 100, "high": 102, "low": 98, "close": 100})
        self.assertEqual((price, reason), (99, "stop_loss"))

    def test_gap_uses_open_not_stop_price(self):
        trade = OpenTrade("buy", datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 99, 101,
                          0.1, 1, 0, 0, 0, "session", "breakout", 1)
        price, reason = _exit_for_bar(trade, {"time": datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
                                              "open": 98, "high": 99, "low": 97, "close": 98})
        self.assertEqual((price, reason), (98, "gap_stop_loss"))

    def test_level_and_confidence_are_explicit(self):
        report = run(self.fixture(), BacktestConfig(min_trades=100))
        self.assertEqual(report["confidence_tier"], "ENGINE_SMOKE_TEST_ONLY")
        self.assertIn("date_range", report)


if __name__ == "__main__":
    unittest.main()
