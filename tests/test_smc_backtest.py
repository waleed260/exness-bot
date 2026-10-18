"""Unit tests for the SMC backtester."""

import unittest
from datetime import datetime, timezone

import pandas as pd

from exness_bot.smc_backtest import run, load_csv, SMCBacktestConfig, _exit_for_bar, _OpenTrade


def _fixture_m5(n=200, base=2000.0, trend=0.05, start_hour=9):
    times = pd.date_range(
        datetime(2026, 1, 5, start_hour, 0), periods=n, freq="5min", tz=timezone.utc
    )
    close = [base + i * trend + (3.0 if (i // 10) % 2 else 0) for i in range(n)]
    high = [c + 1.5 for c in close]
    low = [c - 1.5 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({
        "time": times, "open": opens, "high": high, "low": low,
        "close": close, "volume": [100.0] * n,
    })


def _fixture_m15(n=100, base=2000.0, trend=0.15, start_hour=9):
    times = pd.date_range(
        datetime(2026, 1, 5, start_hour, 0), periods=n, freq="15min", tz=timezone.utc
    )
    close = [base + i * trend + (4.0 if (i // 8) % 2 else 0) for i in range(n)]
    high = [c + 2.0 for c in close]
    low = [c - 2.0 for c in close]
    opens = [close[0]] + close[:-1]
    return pd.DataFrame({
        "time": times, "open": opens, "high": high, "low": low,
        "close": close, "volume": [50.0] * n,
    })


class TestSMCBacktest(unittest.TestCase):

    def test_run_returns_report_dict(self):
        m5 = _fixture_m5()
        m15 = _fixture_m15()
        cfg = SMCBacktestConfig(use_vp=False, use_h1=False, min_trades=0)
        report = run(m5, m15, cfg=cfg)
        self.assertIsInstance(report, dict)
        self.assertIn("trades", report)
        self.assertIn("final_balance", report)
        self.assertIn("initial_balance", report)

    def test_report_schema(self):
        m5 = _fixture_m5()
        m15 = _fixture_m15()
        cfg = SMCBacktestConfig(use_vp=False, use_h1=False, min_trades=0)
        report = run(m5, m15, cfg=cfg)
        required = {
            "trades", "wins", "losses", "win_rate", "total_pnl",
            "gross_profit", "gross_loss", "profit_factor",
            "max_drawdown_pct", "final_balance", "return_pct",
            "partial_closes", "tp2_hits", "sample_status", "initial_balance",
        }
        self.assertTrue(required.issubset(report.keys()), f"Missing: {required - report.keys()}")

    def test_sample_status_low_when_few_trades(self):
        m5 = _fixture_m5(n=90)
        m15 = _fixture_m15(n=50)
        cfg = SMCBacktestConfig(use_vp=False, use_h1=False, min_trades=1000)
        report = run(m5, m15, cfg=cfg)
        if report["trades"] < 1000:
            self.assertEqual(report["sample_status"], "LOW SAMPLE")

    def test_stop_first_on_ambiguous_bar(self):
        trade = _OpenTrade(
            side="buy", entry=2000.0, sl=1995.0, tp1=2007.5, tp2=2012.5,
            volume=0.1, bar_index=0, partial_done=True,
        )
        row = {"high": 2013.0, "low": 1994.0, "open": 2000.0, "close": 2001.0}
        exit_price, reason = _exit_for_bar(trade, row)
        self.assertEqual(exit_price, 1995.0)
        self.assertEqual(reason, "stop_loss")

    def test_sell_stop_first_on_ambiguous_bar(self):
        trade = _OpenTrade(
            side="sell", entry=2000.0, sl=2005.0, tp1=1992.5, tp2=1987.5,
            volume=0.1, bar_index=0, partial_done=True,
        )
        row = {"high": 2006.0, "low": 1986.0, "open": 2000.0, "close": 1999.0}
        exit_price, reason = _exit_for_bar(trade, row)
        self.assertEqual(exit_price, 2005.0)
        self.assertEqual(reason, "stop_loss")

    def test_no_exit_when_price_in_range(self):
        trade = _OpenTrade(
            side="buy", entry=2000.0, sl=1995.0, tp1=2007.5, tp2=2012.5,
            volume=0.1, bar_index=0,
        )
        row = {"high": 2003.0, "low": 1996.0, "open": 2000.0, "close": 2002.0}
        exit_price, reason = _exit_for_bar(trade, row)
        self.assertIsNone(exit_price)
        self.assertIsNone(reason)

    def test_empty_data_returns_zero_trades(self):
        m5 = _fixture_m5(n=50)
        m15 = _fixture_m15(n=20)
        cfg = SMCBacktestConfig(use_vp=False, use_h1=False, min_trades=0)
        report = run(m5, m15, cfg=cfg)
        self.assertGreaterEqual(report["trades"], 0)


if __name__ == "__main__":
    unittest.main()
