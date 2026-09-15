import importlib
import sys
import types
import unittest
from unittest import mock


class FakeResult:
    def __init__(self, retcode):
        self.retcode = retcode
        self.deal = 1
        self.order = 2
        self.price = 100.0
        self.volume = 0.01
        self.comment = "test"


class ExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        fake = types.SimpleNamespace(
            TRADE_RETCODE_REQUOTE=10004,
            TRADE_RETCODE_PRICE_CHANGED=10020,
            TRADE_RETCODE_PRICE_OFF=10021,
            TRADE_RETCODE_TIMEOUT=10012,
            TRADE_RETCODE_DONE=10009,
            TRADE_RETCODE_DONE_PARTIAL=10010,
            TRADE_RETCODE_INVALID_FILL=10030,
            SYMBOL_FILLING_IOC=1,
            SYMBOL_FILLING_FOK=2,
            ORDER_FILLING_IOC=1,
            ORDER_FILLING_FOK=2,
            ORDER_FILLING_RETURN= 4,
        )
        self.fake = fake
        self.modules = {"MetaTrader5": fake}
        self.patcher = mock.patch.dict(sys.modules, self.modules)
        self.patcher.start()
        for name in ("exness_bot.executor", "exness_bot.mt5_client"):
            sys.modules.pop(name, None)
        self.executor = importlib.import_module("exness_bot.executor")
        self.config = importlib.import_module("exness_bot.config")
        self.original = {k: getattr(self.config, k) for k in ("DRY_RUN", "EXECUTION_MODE", "LIVE_TRADING_ENABLED", "ORDER_RETRIES")}

    def tearDown(self):
        for key, value in self.original.items():
            setattr(self.config, key, value)
        self.patcher.stop()
        sys.modules.pop("exness_bot.executor", None)
        sys.modules.pop("exness_bot.mt5_client", None)

    def test_simulation_never_calls_order_send(self):
        self.config.DRY_RUN = False
        self.config.EXECUTION_MODE = "simulation"
        sender = mock.Mock()
        self.executor.mt5.order_send = sender
        result = self.executor._send_with_retry(lambda filling: {"type_filling": filling}, "TEST")
        self.assertIsNone(result)
        sender.assert_not_called()

    def test_live_gate_refuses_before_order_send(self):
        self.config.DRY_RUN = False
        self.config.EXECUTION_MODE = "live"
        self.config.LIVE_TRADING_ENABLED = False
        sender = mock.Mock()
        self.executor.mt5.order_send = sender
        result = self.executor._send_with_retry(lambda filling: {"type_filling": filling}, "TEST")
        self.assertIsNone(result)
        sender.assert_not_called()

    def test_timeout_is_not_retried(self):
        self.config.DRY_RUN = False
        self.config.EXECUTION_MODE = "demo"
        self.config.ORDER_RETRIES = 3
        sender = mock.Mock(return_value=FakeResult(self.fake.TRADE_RETCODE_TIMEOUT))
        self.executor.mt5.order_send = sender
        result = self.executor._send_with_retry(lambda filling: {"type_filling": filling}, "TEST")
        self.assertEqual(result.retcode, self.fake.TRADE_RETCODE_TIMEOUT)
        self.assertEqual(sender.call_count, 1)

    def test_requote_retries_then_succeeds(self):
        self.config.DRY_RUN = False
        self.config.EXECUTION_MODE = "demo"
        self.config.ORDER_RETRIES = 3
        sender = mock.Mock(side_effect=[FakeResult(self.fake.TRADE_RETCODE_REQUOTE), FakeResult(self.fake.TRADE_RETCODE_DONE)])
        self.executor.mt5.order_send = sender
        result = self.executor._send_with_retry(lambda filling: {"type_filling": filling}, "TEST")
        self.assertEqual(result.retcode, self.fake.TRADE_RETCODE_DONE)
        self.assertEqual(sender.call_count, 2)


if __name__ == "__main__":
    unittest.main()
