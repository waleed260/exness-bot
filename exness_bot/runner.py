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
from exness_bot import strategy_dispatch
from exness_bot import risk
from exness_bot import executor
from exness_bot import safety
from exness_bot import recovery

_smc_meta = {}  # ticket -> {tp1, tp2, initial_sl, entry, partial_done, side}


def _position(symbol_info=None):
    for p in mt5_client.positions():
        if p.magic == config.MAGIC:
            return ("buy" if p.type == mt5.POSITION_TYPE_BUY else "sell"), p
    return None, None


def _tracked_positions():
    return {p.ticket: p for p in mt5_client.positions() if p.magic == config.MAGIC}


def _reconcile_closed_positions(previous, current, safety_state):
    for ticket in set(previous) - set(current):
        pnl = mt5_client.position_profit(ticket)
        # If broker history is unavailable, treat the unknown outcome as a loss
        # so the bot fails closed rather than silently bypassing loss protection.
        safety_state.record_close(-1.0 if pnl is None else pnl, config.RISK_PER_TRADE_PCT)
        log.event("position_reconciled_closed", ticket=ticket,
                  pnl="unknown" if pnl is None else pnl)


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
    allowed, reason = safety.environment_allows_execution(
        account_is_demo=mt5_client.is_demo_account(), mode=config.EXECUTION_MODE,
        demo_only=config.DEMO_ONLY, live_trading_enabled=config.LIVE_TRADING_ENABLED,
        confirm_live_string=config.CONFIRM_LIVE_STRING,
    )
    if not allowed:
        raise SystemExit(f"Execution environment rejected: {reason}")
    if not mt5_client.is_demo_account():
        log.logger.warning(f"Running against a LIVE account. DRY_RUN={config.DRY_RUN}")


def _manage_open(symbol_info):
    side, pos = _position(symbol_info)
    if pos is None:
        return

    # SMC partial close + breakeven + trailing management
    if config.ACTIVE_STRATEGY == "smc" and pos.ticket in _smc_meta:
        meta = _smc_meta[pos.ticket]
        t = mt5_client.tick()
        if t is None:
            return
        price = t.bid if side == "buy" else t.ask

        if not meta["partial_done"]:
            hit_tp1 = (price >= meta["tp1"]) if side == "buy" else (price <= meta["tp1"])
            if hit_tp1:
                log.logger.info(f"SMC TP1 hit at {price}; partial close + BE for ticket {pos.ticket}")
                executor.partial_close(pos, config.SMC_PARTIAL_CLOSE_PCT, symbol_info)
                executor.modify_sl(pos, meta["entry"], symbol_info)
                meta["partial_done"] = True

        if meta["partial_done"]:
            from exness_bot.v2_candidate import trailing_stop
            try:
                frames = data_mod.load_multi_frame()
                m5 = frames["m5"]
                from exness_bot.smc_strategy import SMCStrategy
                atr = SMCStrategy()._atr(m5.copy().rename(columns=str.lower)).iloc[-1]
            except Exception:
                return
            highest = float(m5["close"].iloc[-20:].max()) if side == "buy" else meta["entry"]
            lowest = float(m5["close"].iloc[-20:].min()) if side == "sell" else meta["entry"]
            new_sl, reason = trailing_stop(
                side=side, entry_price=meta["entry"], initial_sl=meta["initial_sl"],
                current_sl=pos.sl, market_price=price,
                highest_close=highest, lowest_close=lowest,
                current_atr=atr, trail_mult=2.0,
            )
            if new_sl is not None:
                log.logger.info(f"SMC trail SL ticket {pos.ticket}: {pos.sl} -> {new_sl} ({reason})")
                executor.modify_sl(pos, new_sl, symbol_info)
        return

    # Legacy SMA trailing
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
    if safety.emergency_stop_active():
        log.logger.critical("Emergency stop is active; no new entries")
        return False
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


def _handle_candle(symbol_info, guard, safety_state, signal_ledger):
    if config.ACTIVE_STRATEGY == "smc":
        _handle_candle_smc(symbol_info, guard, safety_state, signal_ledger)
        return

    df = data_mod.load_frame()
    snap = data_mod.snapshot(df)
    side, pos = _position(symbol_info)

    decision = strategy.decide(snap, side)
    action, conf = decision["action"], decision["confidence"]
    log.logger.info(f"{snap['time']} decision={action} conf={conf:.2f} :: {decision['reason']}")

    if action == "close" and pos is not None:
        r = executor.close_position(pos, symbol_info)
        if config.DRY_RUN or executor.succeeded(r):
            _trade_log([datetime.datetime.utcnow().isoformat(), "close", side, pos.volume,
                        getattr(r, "price", ""), "", "", decision["reason"]])
        else:
            log.logger.error("Close did not execute - position left open, will retry next candle")
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
        acc = mt5_client.account_info()
        free_margin_pct = None
        if acc is not None and getattr(acc, "equity", 0):
            free_margin_pct = getattr(acc, "margin_free", acc.equity) / acc.equity * 100.0
        valid, reason = safety.validate_order(
            side=action, volume=lot, price=entry, sl=sl_price, tp=tp_price,
            spread_points=mt5_client.spread_points(), slippage_points=config.DEVIATION_POINTS,
            free_margin_pct=free_margin_pct,
            state=safety_state, existing_positions=len(mt5_client.positions()),
            account_exposure_pct=config.RISK_PER_TRADE_PCT,
        )
        if not valid:
            log.event("trade_rejected", side=action, reason=reason, mode=config.EXECUTION_MODE)
            log.logger.warning(f"Rejected {action} entry: {reason}")
            return
        signal_id = f"{mt5_client.resolved_symbol()}:{snap['time']}:{action}"
        if not signal_ledger.claim(signal_id):
            log.logger.warning(f"Rejected duplicate/stale signal claim: {signal_id}")
            return
        log.logger.info(f"Entering {action} {lot} lots entry~{entry} sl={sl_price:.5f} tp={tp_price:.5f}")
        r = executor.open_position(action, lot, sl_price, tp_price, symbol_info)
        if config.DRY_RUN or executor.succeeded(r):
            safety_state.record_open(config.RISK_PER_TRADE_PCT)
            _trade_log([datetime.datetime.utcnow().isoformat(), "open", action, lot,
                        getattr(r, "price", entry), round(sl_price, 5), round(tp_price, 5),
                        decision["reason"]])
        else:
            log.logger.error(f"Open did not execute (retcode={getattr(r, 'retcode', 'n/a')}); no position taken")


def _handle_candle_smc(symbol_info, guard, safety_state, signal_ledger):
    """SMC strategy candle handler — uses multi-timeframe data and strategy-provided SL/TP."""
    frames = data_mod.load_multi_frame()
    side, pos = _position(symbol_info)

    decision = strategy_dispatch.decide(frames, side)
    action, conf = decision["action"], decision["confidence"]
    reason_str = decision.get("reason", "")
    log.logger.info(f"SMC decision={action} conf={conf:.2f} score={decision.get('score', 0)} :: {reason_str}")

    if action not in ("buy", "sell"):
        return

    if side is not None:
        return
    if len(mt5_client.positions()) >= config.MAX_OPEN_POSITIONS:
        return

    if safety.emergency_stop_active():
        log.logger.critical("Emergency stop is active; no new entries")
        return
    if not guard.can_trade():
        return

    entry = decision["entry"]
    sl_raw = decision["sl"]
    tp2 = decision["tp2"]
    tp1 = decision["tp1"]

    sl_price, tp_price = risk.smc_sl_tp(action, entry, sl_raw, tp2, symbol_info)
    lot = risk.position_size(symbol_info, abs(entry - sl_price))

    acc = mt5_client.account_info()
    free_margin_pct = None
    if acc is not None and getattr(acc, "equity", 0):
        free_margin_pct = getattr(acc, "margin_free", acc.equity) / acc.equity * 100.0

    valid, val_reason = safety.validate_order(
        side=action, volume=lot, price=entry, sl=sl_price, tp=tp_price,
        spread_points=mt5_client.spread_points(), slippage_points=config.DEVIATION_POINTS,
        free_margin_pct=free_margin_pct,
        state=safety_state, existing_positions=len(mt5_client.positions()),
        account_exposure_pct=config.RISK_PER_TRADE_PCT,
    )
    if not valid:
        log.event("trade_rejected", side=action, reason=val_reason, mode=config.EXECUTION_MODE)
        log.logger.warning(f"SMC rejected {action}: {val_reason}")
        return

    m5_time = str(frames["m5"]["time"].iloc[-1])
    signal_id = f"SMC:{mt5_client.resolved_symbol()}:{m5_time}:{action}"
    if not signal_ledger.claim(signal_id):
        log.logger.warning(f"Rejected duplicate SMC signal: {signal_id}")
        return

    log.logger.info(
        f"SMC entering {action} {lot} lots entry~{entry:.2f} sl={sl_price:.2f} "
        f"tp1={tp1:.2f} tp2={tp_price:.2f}"
    )
    r = executor.open_position(action, lot, sl_price, tp_price, symbol_info)
    if config.DRY_RUN or executor.succeeded(r):
        safety_state.record_open(config.RISK_PER_TRADE_PCT)
        actual_entry = getattr(r, "price", entry)
        ticket = getattr(r, "order", None)
        if ticket is not None:
            _smc_meta[ticket] = {
                "tp1": tp1, "tp2": tp2, "initial_sl": sl_price,
                "entry": actual_entry, "partial_done": False, "side": action,
            }
        _trade_log([datetime.datetime.utcnow().isoformat(), "open", action, lot,
                    actual_entry, round(sl_price, 2), round(tp_price, 2), reason_str])
    else:
        log.logger.error(f"SMC open failed (retcode={getattr(r, 'retcode', 'n/a')})")


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


def _recover_connection():
    """Bounded reconnect loop; returns resolved symbol info or None."""
    delays = recovery.backoff_delays(config.MAX_RECONNECT_ATTEMPTS, config.RECONNECT_BACKOFF_SECONDS)
    for attempt in range(1, config.MAX_RECONNECT_ATTEMPTS + 1):
        try:
            mt5_client.reconnect()
            info = mt5_client.resolve_symbol()
            log.event("reconnected", attempt=attempt)
            return info
        except Exception as exc:
            log.event("reconnect_failed", attempt=attempt, error=str(exc))
            log.logger.error(f"Reconnect attempt {attempt} failed: {exc}")
            if attempt < config.MAX_RECONNECT_ATTEMPTS:
                time.sleep(delays[attempt - 1])
    return None


def _total_loss_exceeded(launch_equity):
    """Hard kill switch: stop the bot for good if equity falls too far below the
    equity we started this run with. Not reset by the day rollover."""
    limit = getattr(config, "MAX_TOTAL_LOSS_PCT", 0) or 0
    if limit <= 0 or launch_equity <= 0:
        return False
    acc = mt5_client.account_info()
    if acc is None:
        return False
    dd = (launch_equity - acc.equity) / launch_equity * 100.0
    if dd >= limit:
        log.logger.error(
            f"MAX_TOTAL_LOSS_PCT hit: equity down {dd:.2f}% from {launch_equity:.2f} "
            f"since launch (limit {limit}%). Stopping. Review before restarting."
        )
        return True
    return False


def main():
    _log_environment()
    mt5_client.connect()
    _guard_live()
    base_symbol = config.SMC_SYMBOL if config.ACTIVE_STRATEGY == "smc" else None
    symbol_info = mt5_client.resolve_symbol(base_symbol)
    guard = risk.DailyGuard()
    safety_state = safety.SafetyState(config.SAFETY_STATE_FILE)
    signal_ledger = safety.SignalLedger(config.SIGNAL_LEDGER_FILE)
    known_positions = _tracked_positions()
    safety_state.reconcile_open_positions(len(known_positions), config.RISK_PER_TRADE_PCT)

    _acc = mt5_client.account_info()
    launch_equity = _acc.equity if _acc else 0.0

    candle_tf = config.SMC_PRIMARY_TF if config.ACTIVE_STRATEGY == "smc" else config.TIMEFRAME

    log.event("startup", mode=config.EXECUTION_MODE, dry_run=config.DRY_RUN,
              live_trading_enabled=config.LIVE_TRADING_ENABLED,
              strategy=config.ACTIVE_STRATEGY)
    log.logger.info(
        f"Bot started. symbol={mt5_client.resolved_symbol()} "
        f"strategy={config.ACTIVE_STRATEGY} "
        f"mode={config.EXECUTION_MODE} DRY_RUN={config.DRY_RUN} "
        f"LIVE_TRADING_ENABLED={config.LIVE_TRADING_ENABLED} "
        f"launch_equity={launch_equity}"
    )

    last_bar_time = None
    try:
        while True:
            if _total_loss_exceeded(launch_equity):
                break

            current_positions = _tracked_positions()
            _reconcile_closed_positions(known_positions, current_positions, safety_state)
            # Clean up _smc_meta for closed tickets
            for ticket in set(_smc_meta) - set(current_positions):
                del _smc_meta[ticket]
            known_positions = current_positions
            if not mt5_client.connected():
                log.event("connection_lost")
                symbol_info = _recover_connection()
                if symbol_info is None:
                    log.logger.critical("Connection recovery exhausted; stopping safely")
                    break
                known_positions = _tracked_positions()
                safety_state.reconcile_open_positions(len(known_positions), config.RISK_PER_TRADE_PCT)
                continue

            _manage_open(symbol_info)

            r = mt5_client.rates(mt5_client.resolved_symbol(), candle_tf, 2)
            if r is not None and len(r) >= 2:
                closed_bar_time = int(r[-2]["time"])
                if closed_bar_time != last_bar_time:
                    last_bar_time = closed_bar_time
                    try:
                        _handle_candle(symbol_info, guard, safety_state, signal_ledger)
                    except Exception as e:
                        log.logger.exception(f"Error handling candle: {e}")
            time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        log.logger.info("Stopped by user")
    finally:
        mt5_client.shutdown()


if __name__ == "__main__":
    main()
