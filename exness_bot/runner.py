"""Main loop: on every newly closed candle -> data -> strategy -> risk -> execute.

Run:  python -m exness_bot.runner
Stop: Ctrl+C
"""

import time

import MetaTrader5 as mt5

from exness_bot.logger import log
from exness_bot import config
from exness_bot import mt5_client
from exness_bot import data as data_mod
from exness_bot import strategy
from exness_bot import risk
from exness_bot import executor


def _position_side(symbol_info=None):
    for p in mt5_client.positions(config.SYMBOL):
        if p.magic == config.MAGIC:
            return ("buy" if p.type == mt5.POSITION_TYPE_BUY else "sell"), p
    return None, None


def _guard_live():
    demo = mt5_client.is_demo_account()
    if demo:
        return
    if config.DEMO_ONLY:
        raise SystemExit("Refusing to run: connected account is LIVE and config.DEMO_ONLY is True.")
    if config.CONFIRM_LIVE_STRING != "I ACCEPT THE RISK":
        raise SystemExit("LIVE account: set config.CONFIRM_LIVE_STRING = 'I ACCEPT THE RISK' to proceed.")
    log.logger.warning("Running against a LIVE account. DRY_RUN=%s", config.DRY_RUN)


def _handle_candle(symbol_info, guard):
    df = data_mod.load_frame()
    snap = data_mod.snapshot(df)
    side, pos = _position_side()

    decision = strategy.decide(snap, side)
    action = decision["action"]
    conf = decision["confidence"]

    if action == "hold":
        return
    if action in ("buy", "sell") and conf < config.MIN_CONFIDENCE:
        log.logger.info(f"Skip {action}: confidence {conf:.2f} < {config.MIN_CONFIDENCE}")
        return

    if action == "close" and pos is not None:
        executor.close_position(pos, symbol_info)
        return

    if action in ("buy", "sell"):
        if side is not None:
            log.logger.info("Already in a position, ignoring new entry")
            return
        if len(mt5_client.positions(config.SYMBOL)) >= config.MAX_OPEN_POSITIONS:
            log.logger.info("Max open positions reached")
            return
        if not guard.can_trade():
            return

        atr = snap["atr"]
        tick = mt5_client.tick(config.SYMBOL)
        entry = tick.ask if action == "buy" else tick.bid
        sl_price, tp_price = risk.sl_tp(action, entry, atr, symbol_info)
        lot = risk.position_size(symbol_info, abs(entry - sl_price))
        log.logger.info(f"Entering {action} {lot} lots, entry~{entry} sl={sl_price:.5f} tp={tp_price:.5f}")
        executor.open_position(action, lot, sl_price, tp_price, symbol_info)


def main():
    mt5_client.connect()
    _guard_live()
    symbol_info = mt5_client.ensure_symbol(config.SYMBOL)
    guard = risk.DailyGuard()

    log.logger.info(
        f"Bot started. symbol={config.SYMBOL} tf={config.TIMEFRAME} "
        f"DRY_RUN={config.DRY_RUN} USE_LLM={config.USE_LLM}"
    )

    last_bar_time = None
    try:
        while True:
            rates = mt5_client.rates(config.SYMBOL, config.TIMEFRAME, 2)
            if rates is not None and len(rates) >= 2:
                closed_bar_time = int(rates[-2]["time"])  # -1 is the forming candle
                if closed_bar_time != last_bar_time:
                    last_bar_time = closed_bar_time
                    try:
                        _handle_candle(symbol_info, guard)
                    except Exception as e:
                        log.logger.exception(f"Error handling candle: {e}")
            time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        log.logger.info("Stopped by user")
    finally:
        mt5_client.shutdown()


if __name__ == "__main__":
    main()
