"""Main loop.

Every poll: manage the open position (break-even / trailing SL).
Every newly CLOSED candle: data -> strategy -> filters -> risk -> execute.

Run:  python -m exness_bot.runner
Stop: Ctrl+C
"""

import csv
import os
import platform
import sys
import time
import datetime

import MetaTrader5 as mt5

from exness_bot.logger import log
from exness_bot import config
from exness_bot import mt5_client
from exness_bot import data as data_mod
from exness_bot import strategy
from exness_bot import risk
from exness_bot import executor


def _position(symbol_info=None):
    for p in mt5_client.positions():
        if p.magic == config.MAGIC:
            return ("buy" if p.type == mt5.POSITION_TYPE_BUY else "sell"), p
    return None, None


def _trade_log(row):
    try:
        os.makedirs(os.path.dirname(config.TRADE_LOG_CSV), exist_ok=True)
        new = not os.path.exists(config.TRADE_LOG_CSV)
        with open(config.TRADE_LOG_CSV, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["utc_time", "event", "side", "lot", "price", "sl", "tp", "note"])
            w.writerow(row)
    except Exception as e:  # logging must never crash the loop
        log.logger.warning(f"trade-log write failed: {e}")


def _guard_live():
    if mt5_client.is_demo_account():
        return
    if config.DEMO_ONLY:
        raise SystemExit("Refusing to run: connected account is LIVE and config.DEMO_ONLY is True.")
    if config.CONFIRM_LIVE_STRING != "I ACCEPT THE RISK":
        raise SystemExit("LIVE account: set config.CONFIRM_LIVE_STRING = 'I ACCEPT THE RISK' to proceed.")
    log.logger.warning(f"Running against a LIVE account. DRY_RUN={config.DRY_RUN}")


def _manage_open(symbol_info):
    side, pos = _position(symbol_info)
    if pos is None:
        return
    try:
        df = data_mod.load_frame()
        atr = float(df.iloc[-1]["atr"])
    except Exception:
        return
    t = mt5_client.tick()
    price = t.bid if side == "buy" else t.ask
    new_sl = risk.new_trailing_sl(pos, atr, symbol_info, price)
    if new_sl is not None:
        log.logger.info(f"Trailing SL ticket {pos.ticket}: {pos.sl} -> {new_sl}")
        executor.modify_sl(pos, new_sl, symbol_info)


def _entry_allowed(snap, symbol_info, guard):
    if not risk.within_session():
        log.logger.info("Outside trading session, no new entries")
        return False
    if not guard.can_trade():
        return False
    spread = mt5_client.spread_points()
    if spread is not None and spread > config.MAX_SPREAD_POINTS:
        log.logger.info(f"Spread {spread}p > {config.MAX_SPREAD_POINTS}p, skip entry")
        return False
    if config.MIN_ATR_POINTS:
        atr_pts = snap["atr"] / symbol_info.point
        if atr_pts < config.MIN_ATR_POINTS:
            log.logger.info(f"ATR {atr_pts:.0f}p < {config.MIN_ATR_POINTS}p, skip entry")
            return False
    return True


def _handle_candle(symbol_info, guard):
    df = data_mod.load_frame()
    snap = data_mod.snapshot(df)
    side, pos = _position(symbol_info)

    decision = strategy.decide(snap, side)
    action, conf = decision["action"], decision["confidence"]
    log.logger.info(f"{snap['time']} decision={action} conf={conf:.2f} :: {decision['reason']}")

    if action == "close" and pos is not None:
        r = executor.close_position(pos, symbol_info)
        _trade_log([datetime.datetime.utcnow().isoformat(), "close", side, pos.volume,
                    getattr(r, "price", ""), "", "", decision["reason"]])
        return

    if action in ("buy", "sell"):
        if side is not None:
            return
        if conf < config.MIN_CONFIDENCE:
            log.logger.info(f"Skip {action}: confidence {conf:.2f} < {config.MIN_CONFIDENCE}")
            return
        if len(mt5_client.positions()) >= config.MAX_OPEN_POSITIONS:
            return
        if not _entry_allowed(snap, symbol_info, guard):
            return

        atr = snap["atr"]
        t = mt5_client.tick()
        entry = t.ask if action == "buy" else t.bid
        sl_price, tp_price = risk.sl_tp(action, entry, atr, symbol_info)
        lot = risk.position_size(symbol_info, abs(entry - sl_price))
        log.logger.info(f"Entering {action} {lot} lots entry~{entry} sl={sl_price:.5f} tp={tp_price:.5f}")
        r = executor.open_position(action, lot, sl_price, tp_price, symbol_info)
        _trade_log([datetime.datetime.utcnow().isoformat(), "open", action, lot,
                    getattr(r, "price", entry), round(sl_price, 5), round(tp_price, 5),
                    decision["reason"]])


def _log_environment():
    """Print OS / Python info - handy when debugging a first run."""
    log.logger.info(
        f"Environment: {platform.system()} {platform.release()} "
        f"| Python {sys.version.split()[0]} ({platform.architecture()[0]})"
    )
    if platform.system() != "Windows":
        log.logger.warning(
            "Not running on Windows - the MetaTrader5 package is Windows-only, "
            "so live/demo trading will not work here (backtesting still does)."
        )
        return
    try:
        # platform.release() is '7', '10', '11', ... on Windows
        major = int(str(platform.release()).split(".")[0])
        if major < 7:
            log.logger.warning(
                "This looks older than Windows 7. Supported: Windows 7, 10, 11."
            )
    except ValueError:
        pass


def main():
    _log_environment()
    mt5_client.connect()
    _guard_live()
    symbol_info = mt5_client.resolve_symbol()
    guard = risk.DailyGuard()

    log.logger.info(
        f"Bot started. symbol={mt5_client.resolved_symbol()} tf={config.TIMEFRAME} "
        f"DRY_RUN={config.DRY_RUN} USE_LLM={config.USE_LLM}"
    )

    last_bar_time = None
    try:
        while True:
            _manage_open(symbol_info)

            r = mt5_client.rates(mt5_client.resolved_symbol(), config.TIMEFRAME, 2)
            if r is not None and len(r) >= 2:
                closed_bar_time = int(r[-2]["time"])
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
