import unittest
from datetime import datetime, timedelta, timezone

from exness_bot.volume_profile import profile_session_id, profile_snapshot
from exness_bot.vp_breakout_strategy import VPBreakoutStrategy
from exness_bot.vp_risk import (
    DailyGuard, fixed_sl_tp, size_for_risk, spread_allowed, validate_pip_size,
)


class PhaseBTests(unittest.TestCase):
    def setUp(self):
        self.info = {"point": 0.01, "trade_tick_size": 0.01, "digits": 2,
                     "volume_min": 0.01, "volume_max": 10.0, "volume_step": 0.01}
        self.t0 = datetime(2026, 1, 5, 3, 0, tzinfo=timezone.utc)

    def _profile_candles(self):
        return [
            {"time": self.t0 + timedelta(minutes=5 * i), "price": 100.0 + i, "volume": 10.0}
            for i in range(6)
        ]

    def test_03_00_profile_reset(self):
        self.assertEqual(profile_session_id(datetime(2026, 1, 5, 2, 59, tzinfo=timezone.utc)), "2026-01-04")
        self.assertEqual(profile_session_id(datetime(2026, 1, 5, 3, 0, tzinfo=timezone.utc)), "2026-01-05")

    def test_no_previous_day_level_leakage(self):
        candles = [{"time": datetime(2026, 1, 5, 2, 55, tzinfo=timezone.utc), "price": 999, "volume": 100}]
        candles += [{"time": self.t0, "price": 100, "volume": 10}, {"time": self.t0 + timedelta(minutes=5), "price": 101, "volume": 10}]
        snap = profile_snapshot(candles, self.t0 + timedelta(minutes=10), bin_size=1)
        self.assertEqual(snap.included_candles, 2)
        self.assertNotEqual(snap.poc, 999)

    def test_pre_breakout_snapshot_correctness(self):
        candles = self._profile_candles()
        evaluation = self.t0 + timedelta(minutes=30)
        snap = profile_snapshot(candles, evaluation, bin_size=1)
        self.assertEqual(snap.included_candles, 6)
        candles.append({"time": evaluation, "price": 10000, "volume": 100000})
        same = profile_snapshot(candles, evaluation, bin_size=1)
        self.assertEqual((snap.vah, snap.val, snap.poc), (same.vah, same.val, same.poc))

    def test_wick_only_breakout_gives_no_trade(self):
        strategy = VPBreakoutStrategy()
        event = strategy.on_closed_candle(self.t0, 110, 99, 100, 105, 95)
        self.assertEqual(event.event, "no_setup")

    def test_close_above_green_creates_buy_setup(self):
        event = VPBreakoutStrategy().on_closed_candle(self.t0, 110, 100, 106, 105, 95)
        self.assertEqual((event.event, event.direction), ("breakout_detected", "buy"))

    def test_close_below_red_creates_sell_setup(self):
        event = VPBreakoutStrategy().on_closed_candle(self.t0, 100, 90, 94, 105, 95)
        self.assertEqual((event.event, event.direction), ("breakout_detected", "sell"))

    def test_next_candle_high_trigger_creates_buy(self):
        strategy = VPBreakoutStrategy()
        detected = strategy.on_closed_candle(self.t0, 110, 100, 106, 105, 95)
        event = strategy.on_tick(self.t0 + timedelta(minutes=5, seconds=1), 109, 110.1)
        self.assertEqual((event.event, event.breakout_id), ("buy_triggered", detected.breakout_id))

    def test_next_candle_low_trigger_creates_sell(self):
        strategy = VPBreakoutStrategy()
        detected = strategy.on_closed_candle(self.t0, 100, 90, 94, 105, 95)
        event = strategy.on_tick(self.t0 + timedelta(minutes=5, seconds=1), 89.9, 90.1)
        self.assertEqual((event.event, event.breakout_id), ("sell_triggered", detected.breakout_id))

    def test_confirmation_expires_after_one_candle(self):
        strategy = VPBreakoutStrategy()
        detected = strategy.on_closed_candle(self.t0, 110, 100, 106, 105, 95)
        event = strategy.on_tick(self.t0 + timedelta(minutes=10), 109, 109.1)
        self.assertEqual((event.event, event.breakout_id), ("setup_expired", detected.breakout_id))

    def test_duplicate_breakout_blocked(self):
        strategy = VPBreakoutStrategy()
        first = strategy.on_closed_candle(self.t0, 110, 100, 106, 105, 95)
        strategy.on_tick(self.t0 + timedelta(minutes=5, seconds=1), 111, 112)
        duplicate = strategy.on_closed_candle(self.t0, 110, 100, 106, 105, 95)
        self.assertEqual((duplicate.event, duplicate.reason), ("setup_rejected", "duplicate_breakout"))
        self.assertEqual(first.breakout_id, duplicate.breakout_id)

    def test_exact_30_40_pip_distances(self):
        sl, tp = fixed_sl_tp("buy", 2000.0, 0.1, {"point": 0.1, "trade_tick_size": 0.1, "digits": 1})
        self.assertEqual((sl, tp), (1997.0, 2004.0))
        sl, tp = fixed_sl_tp("sell", 2000.0, 0.1, {"point": 0.1, "trade_tick_size": 0.1, "digits": 1})
        self.assertEqual((sl, tp), (2003.0, 1996.0))

    def test_pip_configuration_validation(self):
        self.assertTrue(validate_pip_size(0.1, {"point": 0.1, "trade_tick_size": 0.1, "digits": 1}))
        self.assertFalse(validate_pip_size(0.015, self.info))
        with self.assertRaises(ValueError):
            fixed_sl_tp("buy", 100, 0.015, self.info)

    def test_safe_lot_floor_behavior(self):
        result = size_for_risk(1000, 100, 99, self.info, lambda volume, entry, stop: -100 * volume)
        self.assertTrue(result.approved)
        self.assertEqual(result.volume, 0.05)
        self.assertEqual(result.reason, "approved")

    def test_minimum_lot_rejection(self):
        result = size_for_risk(100, 100, 99, self.info, lambda volume, entry, stop: -1000 * volume)
        self.assertFalse(result.approved)
        self.assertEqual(result.reason, "minimum volume exceeds risk budget")

    def test_daily_loss_stop(self):
        guard = DailyGuard.start(datetime(2026, 1, 5).date(), 1000)
        guard.record_close(-20)
        self.assertEqual(guard.can_trade(), (False, "daily-loss stop"))

    def test_consecutive_loss_stop(self):
        guard = DailyGuard.start(datetime(2026, 1, 5).date(), 1000)
        guard.record_close(-1)
        guard.record_close(-1)
        self.assertEqual(guard.can_trade(), (False, "consecutive-loss stop"))

    def test_spread_rejection(self):
        self.assertFalse(spread_allowed(2000.0, 2000.6, 0.1, 5.0))
        self.assertTrue(spread_allowed(2000.0, 2000.2, 0.1, 5.0))


if __name__ == "__main__":
    unittest.main()
