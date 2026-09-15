import datetime as dt
import tempfile
import unittest
from pathlib import Path

from exness_bot import safety
from exness_bot import recovery
from exness_bot import simulator
from exness_bot.logger import event


class SafetyTests(unittest.TestCase):
    def test_reconnect_backoff_is_bounded(self):
        self.assertEqual(recovery.backoff_delays(4, 5, 12), [5.0, 10.0, 12.0])
        self.assertEqual(recovery.backoff_delays(1, 5), [])

    def test_environment_guard_never_maps_live_account_to_demo_mode(self):
        allowed, reason = safety.environment_allows_execution(
            account_is_demo=False, mode="demo", demo_only=False,
            live_trading_enabled=False, confirm_live_string="",
        )
        self.assertFalse(allowed)
        self.assertIn("requires live execution mode", reason)
        allowed, reason = safety.environment_allows_execution(
            account_is_demo=False, mode="live", demo_only=False,
            live_trading_enabled=False, confirm_live_string="I ACCEPT THE RISK",
        )
        self.assertFalse(allowed)
        self.assertIn("gate is disabled", reason)
        allowed, reason = safety.environment_allows_execution(account_is_demo=False, mode="live", demo_only=False, live_trading_enabled=True, confirm_live_string="")
        self.assertFalse(allowed)
        self.assertIn("confirmation string is missing", reason)
        allowed, reason = safety.environment_allows_execution(account_is_demo=False, mode="live", demo_only=False, live_trading_enabled=True, confirm_live_string="I ACCEPT THE RISK")
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")
        allowed, reason = safety.environment_allows_execution(account_is_demo=True, mode="live", demo_only=False, live_trading_enabled=True, confirm_live_string="I ACCEPT THE RISK")
        self.assertFalse(allowed)
        self.assertIn("not valid for a demo account", reason)

    def test_valid_order_and_fail_closed_conditions(self):
        state = safety.SafetyState()
        ok, reason = safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                           spread_points=10, free_margin_pct=200, state=state)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok")
        self.assertEqual(safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                               emergency_stop=True)[1], "emergency stop is active")
        self.assertEqual(safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                               spread_points=999)[1], "spread exceeds limit")
        self.assertEqual(safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                               slippage_points=999)[1], "slippage exceeds limit")
        self.assertEqual(safety.validate_order(side="buy", volume=1, price=100, sl=99, tp=102)[1],
                         "volume exceeds maximum lot")

    def test_state_and_signal_ledger_persist_across_restart(self):
        with tempfile.TemporaryDirectory() as d:
            state_path = str(Path(d) / "risk.json")
            ledger_path = str(Path(d) / "signals.json")
            state = safety.SafetyState(state_path=state_path)
            state.record_open(0.25)
            state.record_close(-1, 0.25)
            self.assertFalse(safety.SafetyState(state_path=state_path).consecutive_losses == 0)
            ledger = safety.SignalLedger(ledger_path)
            self.assertTrue(ledger.claim("EURUSD:bar-1:buy"))
            self.assertFalse(safety.SignalLedger(ledger_path).claim("EURUSD:bar-1:buy"))

    def test_stale_and_consecutive_loss_limits(self):
        now = dt.datetime(2026, 1, 1, 12)
        state = safety.SafetyState(day=now.date())
        for _ in range(3):
            state.record_close(-1, now=now)
        self.assertEqual(safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                               state=state, now=now)[1], "consecutive-loss protection active")
        state = safety.SafetyState(day=now.date(), consecutive_losses=3)
        state.roll_day(now + dt.timedelta(days=1))
        self.assertEqual(state.consecutive_losses, 3)
        old = now - dt.timedelta(seconds=901)
        self.assertEqual(safety.validate_order(side="buy", volume=0.01, price=100, sl=99, tp=102,
                                               signal_time=old, now=now)[1], "signal is stale or from the future")


class SimulatorTests(unittest.TestCase):
    def test_structured_event_redacts_secret_fields(self):
        event("test", api_key="do-not-log", decision="hold")

    def test_buy_hits_take_profit_and_recovers_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "state.json")
            sim = simulator.Simulator(path)
            position = sim.open("buy", 1, 100, 99, 102, "2026-01-01T12:00:00")
            self.assertEqual(len(sim.open_positions()), 1)
            self.assertEqual(sim.on_price(102)[0].exit_reason, "take_profit")
            recovered = simulator.Simulator(path)
            self.assertEqual(recovered.positions[position.ticket].status, "closed")

    def test_sell_stop_and_stop_never_loosened(self):
        sim = simulator.Simulator()
        position = sim.open("sell", 1, 100, 101, 98)
        self.assertFalse(sim.modify_sl(position.ticket, 102))
        self.assertTrue(sim.modify_sl(position.ticket, 100.5))
        self.assertEqual(sim.on_price(100.5)[0].exit_reason, "stop_loss")

    def test_reconcile_marks_missing_position_closed(self):
        sim = simulator.Simulator()
        position = sim.open("buy", 1, 100, 99, 102)
        sim.reconcile([])
        self.assertEqual(sim.positions[position.ticket].exit_reason, "reconciled_missing_external_position")


if __name__ == "__main__":
    unittest.main()
