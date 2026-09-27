"""Phase D backtester for VP_BREAKOUT_M5_V1.

This is intentionally separate from the legacy backtest.py.  It calls the
Phase B volume profile, breakout state machine, and risk modules directly.
For OHLC bars this engine is Level 2: trigger order inside a bar is unknown,
so ambiguous SL/TP uses the conservative stop-first rule. Tick/M1 Level 3
execution is not claimed unless a higher-resolution adapter is added.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from exness_bot.volume_profile import profile_snapshot
from exness_bot.vp_breakout_strategy import VPBreakoutStrategy
from exness_bot.vp_risk import DailyGuard, fixed_sl_tp, size_for_risk, spread_allowed


@dataclass(frozen=True)
class BacktestConfig:
    pip_size: float = 0.1
    bin_size: float = 0.1
    initial_balance: float = 10_000.0
    money_per_price_unit_per_lot: float = 100.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    max_spread_pips: float = 5.0
    commission_per_lot: float = 0.0
    swap_per_lot_per_day: float = 0.0
    slippage_pips: float = 0.0
    min_trades: int = 100
    data_source: str = "caller-supplied CSV"
    level: str = "LEVEL_2_OHLC"


@dataclass
class OpenTrade:
    direction: str
    entry_time: datetime
    entry: float
    sl: float
    tp: float
    volume: float
    risk_money: float
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    profile_session_id: str
    breakout_id: str
    entry_bar: int


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = pd.Timestamp(value).to_pydatetime()
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def load_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame.columns = [str(column).lower().strip() for column in frame.columns]
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if "volume" not in frame and "tick_volume" not in frame:
        frame["volume"] = 1.0
    elif "volume" not in frame:
        frame["volume"] = pd.to_numeric(frame["tick_volume"], errors="raise")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="raise")
    frame = frame.sort_values("time").reset_index(drop=True)
    if frame["time"].duplicated().any():
        raise ValueError("duplicate timestamps")
    if not (frame["high"] >= frame[["open", "close"]].max(axis=1)).all():
        raise ValueError("high is below open or close")
    if not (frame["low"] <= frame[["open", "close"]].min(axis=1)).all():
        raise ValueError("low is above open or close")
    return frame


def _symbol_info(config: BacktestConfig) -> dict:
    point = config.pip_size / 10.0
    return {"point": point, "trade_tick_size": point, "digits": 5,
            "volume_min": config.volume_min, "volume_max": config.volume_max,
            "volume_step": config.volume_step}


def _bar_candle(row: Mapping) -> dict:
    return {"time": _parse_time(row["time"]), "open": float(row["open"]),
            "high": float(row["high"]), "low": float(row["low"]),
            "close": float(row["close"]), "volume": float(row.get("volume", 1.0))}


def _spread_pips(row: Mapping, config: BacktestConfig) -> float:
    value = row.get("spread_pips", config.max_spread_pips)
    return float(value)


def _holding_days(entry: datetime, exit_time: datetime) -> int:
    # Swap is modeled by crossed UTC calendar days, not rounded-up intraday hours.
    return max(0, (exit_time.date() - entry.date()).days)


def _close_trade(trade: OpenTrade, row: Mapping, exit_price: float, reason: str,
                 balance: float, config: BacktestConfig, exit_bar: Optional[int] = None) -> dict:
    exit_time = _parse_time(row["time"])
    direction_factor = 1 if trade.direction == "buy" else -1
    gross = (exit_price - trade.entry) * direction_factor * config.money_per_price_unit_per_lot * trade.volume
    swap = config.swap_per_lot_per_day * trade.volume * _holding_days(trade.entry_time, exit_time)
    net = gross - trade.spread_cost - trade.commission_cost - trade.slippage_cost - swap
    risk = trade.risk_money if trade.risk_money > 0 else 1.0
    hold_bars = max(0, exit_bar - trade.entry_bar) if exit_bar is not None else 0
    return {
        "entry_time": trade.entry_time.isoformat(), "exit_time": exit_time.isoformat(),
        "side": trade.direction, "entry": trade.entry, "exit": exit_price,
        "volume": trade.volume, "hold_bars": hold_bars, "gross_profit": gross, "net_profit": net,
        "r": net / risk, "reason": reason, "hold_days": _holding_days(trade.entry_time, exit_time),
        "spread_cost": trade.spread_cost, "commission_cost": trade.commission_cost,
        "swap_cost": swap, "slippage_cost": trade.slippage_cost,
        "profile_session_id": trade.profile_session_id, "breakout_id": trade.breakout_id,
    }


def _exit_for_bar(trade: OpenTrade, row: Mapping) -> tuple[Optional[float], Optional[str]]:
    """Level-2 bar exit; gaps use the executable open, both touches use stop first."""
    open_price, high, low = float(row["open"]), float(row["high"]), float(row["low"])
    if trade.direction == "buy":
        if open_price <= trade.sl:
            return open_price, "gap_stop_loss"
        if low <= trade.sl:
            return trade.sl, "stop_loss"
        if open_price >= trade.tp:
            return open_price, "gap_take_profit"
        if high >= trade.tp:
            return trade.tp, "take_profit"
    else:
        if open_price >= trade.sl:
            return open_price, "gap_stop_loss"
        if high >= trade.sl:
            return trade.sl, "stop_loss"
        if open_price <= trade.tp:
            return open_price, "gap_take_profit"
        if low <= trade.tp:
            return trade.tp, "take_profit"
    return None, None


def _empty_report(frame: pd.DataFrame, config: BacktestConfig, skipped: int, reasons: dict) -> dict:
    report = {
        "engine": "VP_BREAKOUT_M5_V1",
        "resolution_tier": config.level,
        "confidence_tier": "ENGINE_SMOKE_TEST_ONLY",
        "data_source": config.data_source,
        "date_range": {"start": frame["time"].iloc[0].isoformat(), "end": frame["time"].iloc[-1].isoformat()},
        "bars": len(frame), "starting_balance": config.initial_balance, "ending_balance": config.initial_balance,
        "net_profit": 0.0, "return_percent": 0.0, "total_trades": 0, "win_rate_percent": 0.0,
        "average_win": 0.0, "average_loss": 0.0, "payoff_ratio": 0.0, "expectancy_per_trade": 0.0,
        "average_r": 0.0, "median_r": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
        "drawdown_duration_bars": 0, "worst_losing_streak": 0, "exposure_time_bars": 0,
        "average_hold_time_days": 0.0, "spread_cost": 0.0, "commission_cost": 0.0,
        "swap_cost": 0.0, "slippage_cost": 0.0, "long_results": {}, "short_results": {},
        "session_results": {}, "month_results": {}, "quarter_results": {}, "regime_results": {},
        "skipped_trade_count": skipped, "top_rejection_reasons": reasons,
        "sample_status": "INSUFFICIENT SAMPLE" if 0 < config.min_trades else "NO TRADES",
        "trades": [],
    }
    return report


def _report(frame: pd.DataFrame, trades: list[dict], config: BacktestConfig, skipped: int, reasons: dict) -> dict:
    if not trades:
        return _empty_report(frame, config, skipped, reasons)
    rs = [float(t["r"]) for t in trades]
    wins = [t for t in trades if t["net_profit"] > 0]
    losses = [t for t in trades if t["net_profit"] <= 0]
    gross_wins = sum(t["net_profit"] for t in wins)
    gross_losses = -sum(t["net_profit"] for t in losses)
    balance = config.initial_balance
    peak = balance
    max_dd = 0.0
    dd_duration = 0
    current_dd = 0
    for trade in trades:
        balance += trade["net_profit"]
        if balance >= peak:
            peak = balance
            current_dd = 0
        else:
            current_dd += 1
            dd_duration = max(dd_duration, current_dd)
        max_dd = max(max_dd, (peak - balance) / peak if peak else 0)
    streak = worst = 0
    for trade in trades:
        if trade["net_profit"] <= 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    def group(side: Optional[str] = None, selected=None):
        selected = list(selected if selected is not None else [t for t in trades if side is None or t["side"] == side])
        return {"trades": len(selected), "net_profit": sum(t["net_profit"] for t in selected),
                "expectancy": (sum(t["r"] for t in selected) / len(selected)) if selected else 0.0}

    def grouped(field):
        groups = {}
        for trade in trades:
            timestamp = trade["entry_time"]
            if field == "month":
                key = timestamp[:7]
            elif field == "quarter":
                month = timestamp[:7]
                year, month_number = map(int, month.split("-"))
                key = f"{year}-Q{((month_number - 1) // 3) + 1}"
            else:
                key = trade[field]
            groups.setdefault(key, []).append(trade)
        return {str(key): group(selected=values) for key, values in groups.items()}

    return {
        **_empty_report(frame, config, skipped, reasons),
        "ending_balance": balance, "net_profit": balance - config.initial_balance,
        "return_percent": (balance / config.initial_balance - 1) * 100 if config.initial_balance else 0.0,
        "total_trades": len(trades), "win_rate_percent": len(wins) / len(trades) * 100,
        "average_win": gross_wins / len(wins) if wins else 0.0,
        "average_loss": gross_losses / len(losses) if losses else 0.0,
        "payoff_ratio": (gross_wins / len(wins)) / (gross_losses / len(losses)) if wins and losses and gross_losses else 0.0,
        "expectancy_per_trade": sum(rs) / len(rs), "average_r": sum(rs) / len(rs),
        "median_r": median(rs), "profit_factor": gross_wins / gross_losses if gross_losses else float("inf"),
        "max_drawdown": max_dd, "drawdown_duration_bars": dd_duration,
        "worst_losing_streak": worst, "exposure_time_bars": sum(t["hold_bars"] for t in trades),
        "average_hold_time_days": sum(t["hold_days"] for t in trades) / len(trades),
        "spread_cost": sum(t["spread_cost"] for t in trades),
        "commission_cost": sum(t["commission_cost"] for t in trades),
        "swap_cost": sum(t["swap_cost"] for t in trades),
        "slippage_cost": sum(t["slippage_cost"] for t in trades),
        "long_results": group("buy"), "short_results": group("sell"),
        "session_results": grouped("profile_session_id"),
        "month_results": grouped("month"),
        "quarter_results": grouped("quarter"),
        "regime_results": {"unclassified_level_2_ohlc": group(selected=trades)},
        "trades": trades,
        "sample_status": "PASS SAMPLE" if len(trades) >= config.min_trades else "INSUFFICIENT SAMPLE",
    }


def run(frame: pd.DataFrame, config: BacktestConfig = BacktestConfig()) -> dict:
    if frame.empty:
        raise ValueError("backtest requires at least one bar")
    if config.level != "LEVEL_2_OHLC":
        raise ValueError("only LEVEL_2_OHLC is implemented; Level 3 tick ordering is not claimed")
    frame = frame.copy()
    frame["time"] = frame["time"].map(_parse_time)
    candles = [_bar_candle(row) for row in frame.to_dict("records")]
    symbol_info = _symbol_info(config)
    strategy = VPBreakoutStrategy()
    guard = DailyGuard.start(_parse_time(frame.iloc[0]["time"]).date(), config.initial_balance)
    open_trade: Optional[OpenTrade] = None
    trades: list[dict] = []
    skipped = 0
    reasons: dict[str, int] = {}

    def skip(reason: str):
        nonlocal skipped
        skipped += 1
        reasons[reason] = reasons.get(reason, 0) + 1

    for index, row in frame.iterrows():
        candle = candles[index]
        current_time = candle["time"]
        guard.roll(current_time.date(), config.initial_balance)
        if open_trade is not None:
            exit_price, reason = _exit_for_bar(open_trade, candle)
            if exit_price is not None:
                trades.append(_close_trade(open_trade, candle, exit_price, reason, config.initial_balance, config, index))
                guard.record_close(trades[-1]["net_profit"])
                open_trade = None
                continue
        if open_trade is None and strategy.pending is not None:
            # Preserve setup metadata before on_tick clears the pending state.
            pending_setup = strategy.pending
            # Level 2 OHLC model: test gap-at-open first, then the relevant extreme.
            if pending_setup.direction == "buy":
                trigger = strategy.on_tick(current_time + pd.Timedelta(seconds=1), float(row["open"]), float(row["open"]))
                if trigger.event == "waiting":
                    trigger = strategy.on_tick(current_time + pd.Timedelta(seconds=2), float(row["low"]), float(row["high"]))
            else:
                trigger = strategy.on_tick(current_time + pd.Timedelta(seconds=1), float(row["open"]), float(row["open"]))
                if trigger.event == "waiting":
                    trigger = strategy.on_tick(current_time + pd.Timedelta(seconds=2), float(row["low"]), float(row["high"]))
            if trigger.event in {"buy_triggered", "sell_triggered"}:
                spread = _spread_pips(row, config)
                spread_bid = float(trigger.price)
                spread_ask = spread_bid + spread * config.pip_size
                if not spread_allowed(spread_bid, spread_ask, config.pip_size, config.max_spread_pips):
                    skip("spread_filter_block")
                elif not guard.can_trade()[0]:
                    skip(guard.can_trade()[1])
                else:
                    raw_entry = float(trigger.price)
                    entry = raw_entry + spread * config.pip_size if trigger.direction == "buy" else raw_entry - spread * config.pip_size
                    sl, tp = fixed_sl_tp(trigger.direction, entry, config.pip_size, symbol_info)
                    calc = lambda volume, entry_price, stop_price: -abs(entry_price - stop_price) * config.money_per_price_unit_per_lot * volume
                    sizing = size_for_risk(config.initial_balance, entry, sl, symbol_info, calc,
                                           commission_per_lot=config.commission_per_lot)
                    if not sizing.approved:
                        skip(sizing.reason)
                    else:
                        volume = sizing.volume
                        open_trade = OpenTrade(
                            trigger.direction, current_time, entry, sl, tp, volume, sizing.risk_budget,
                            spread * config.pip_size * config.money_per_price_unit_per_lot * volume,
                            config.commission_per_lot * volume, config.slippage_pips * config.pip_size * config.money_per_price_unit_per_lot * volume,
                            pending_setup.session_id if hasattr(pending_setup, "session_id") else pending_setup.candle_time.date().isoformat(), trigger.breakout_id, index,
                        )
                        # Apply entry-bar SL/TP after the trigger; conservative stop-first rule.
                        exit_price, reason = _exit_for_bar(open_trade, candle)
                        if exit_price is not None:
                            trades.append(_close_trade(open_trade, candle, exit_price, "entry_bar_" + reason, config.initial_balance, config, index))
                            guard.record_close(trades[-1]["net_profit"])
                            open_trade = None
                continue
        if open_trade is None:
            try:
                snapshot = profile_snapshot(candles[:index], current_time, bin_size=config.bin_size)
            except ValueError:
                skip("profile_unavailable")
                continue
            event = strategy.on_closed_candle(current_time, candle["high"], candle["low"], candle["close"], snapshot.vah, snapshot.val)
            if event.event == "no_setup":
                skip(event.reason or "no_setup")
    if open_trade is not None:
        last = candles[-1]
        trades.append(_close_trade(open_trade, last, last["close"], "end_of_data", config.initial_balance, config, len(frame) - 1))
    return _report(frame, trades, config, skipped, reasons)


def main(argv=None):
    parser = argparse.ArgumentParser(description="VP_BREAKOUT_M5_V1 Level-2 OHLC backtester")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", default="vp_backtest_report.json")
    parser.add_argument("--pip-size", type=float, default=0.1)
    parser.add_argument("--bin-size", type=float, default=0.1)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--money-per-price-unit-per-lot", type=float, default=100.0)
    parser.add_argument("--max-spread-pips", type=float, default=5.0)
    parser.add_argument("--commission-per-lot", type=float, default=0.0)
    parser.add_argument("--swap-per-lot-per-day", type=float, default=0.0)
    parser.add_argument("--slippage-pips", type=float, default=0.0)
    parser.add_argument("--min-trades", type=int, default=100)
    args = parser.parse_args(argv)
    config = BacktestConfig(pip_size=args.pip_size, bin_size=args.bin_size, initial_balance=args.initial_balance,
                            money_per_price_unit_per_lot=args.money_per_price_unit_per_lot,
                            max_spread_pips=args.max_spread_pips, commission_per_lot=args.commission_per_lot,
                            swap_per_lot_per_day=args.swap_per_lot_per_day, slippage_pips=args.slippage_pips,
                            min_trades=args.min_trades, data_source=args.csv)
    frame = load_csv(args.csv)
    report = run(frame, config)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))
    if report["sample_status"] == "INSUFFICIENT SAMPLE":
        print("INSUFFICIENT SAMPLE")


if __name__ == "__main__":
    main()
