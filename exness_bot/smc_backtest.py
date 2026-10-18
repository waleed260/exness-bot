"""SMC XAUUSD M5 backtester — Level-2 OHLC with partial close simulation.

Usage:
    python -m exness_bot.smc_backtest --m5-csv data/XAUUSD_M5.csv --m15-csv data/XAUUSD_M15.csv [--h1-csv data/XAUUSD_H1.csv]
"""

import argparse
import csv
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from exness_bot import config
from exness_bot.smc_strategy import SMCStrategy
from exness_bot.volume_profile import VolumeProfile


@dataclass
class SMCBacktestConfig:
    pip_size: float = 0.01
    bin_size: float = 1.0
    initial_balance: float = 10_000.0
    risk_fraction: float = 0.005
    money_per_price_unit_per_lot: float = 100.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    max_spread_pips: float = 4.0
    commission_per_lot: float = 7.0
    swap_per_lot_per_day: float = 0.0
    slippage_pips: float = 0.5
    min_trades: int = 30
    use_vp: bool = True
    use_h1: bool = True


@dataclass
class _OpenTrade:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    volume: float
    bar_index: int
    partial_done: bool = False
    be_done: bool = False
    initial_sl: float = 0.0

    def __post_init__(self):
        if self.initial_sl == 0.0:
            self.initial_sl = self.sl


def load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace("<", "").replace(">", "") for c in df.columns]
    renames = {"date": "time", "datetime": "time", "gmt time": "time"}
    df.rename(columns={k: v for k, v in renames.items() if k in df.columns}, inplace=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    if "volume" not in df.columns:
        df["volume"] = df.get("tick_volume", pd.Series(1.0, index=df.index)).astype(float)
    return df.sort_values("time").reset_index(drop=True)


def _align_htf(m5_time, htf_df, lookback):
    mask = htf_df["time"] < m5_time
    sub = htf_df.loc[mask].tail(lookback)
    return sub.reset_index(drop=True) if len(sub) >= 40 else None


def _exit_for_bar(trade, row):
    """Conservative stop-first exit on a single bar."""
    h, l = float(row["high"]), float(row["low"])
    if trade.side == "buy":
        sl_hit = l <= trade.sl
        tp_target = trade.tp2 if trade.partial_done else trade.tp1
        tp_hit = h >= tp_target
        if sl_hit and tp_hit:
            return trade.sl, "stop_loss"
        if sl_hit:
            return trade.sl, "stop_loss"
        if tp_hit:
            return tp_target, ("take_profit_tp2" if trade.partial_done else "take_profit_tp1")
    else:
        sl_hit = h >= trade.sl
        tp_target = trade.tp2 if trade.partial_done else trade.tp1
        tp_hit = l <= tp_target
        if sl_hit and tp_hit:
            return trade.sl, "stop_loss"
        if sl_hit:
            return trade.sl, "stop_loss"
        if tp_hit:
            return tp_target, ("take_profit_tp2" if trade.partial_done else "take_profit_tp1")
    return None, None


def run(m5_frame, m15_frame, h1_frame=None, cfg=None):
    if cfg is None:
        cfg = SMCBacktestConfig()

    strategy = SMCStrategy()
    balance = cfg.initial_balance
    peak = balance
    max_dd = 0.0
    trades = []
    trade: Optional[_OpenTrade] = None
    vp = VolumeProfile(bin_size=cfg.bin_size) if cfg.use_vp else None

    warmup = 80

    for i in range(warmup, len(m5_frame)):
        row = m5_frame.iloc[i]
        m5_time = row["time"]

        if vp is not None:
            vp.add_closed_candle(m5_frame.iloc[i - 1].to_dict())

        # Check exit on current bar first
        if trade is not None:
            exit_price, exit_reason = _exit_for_bar(trade, row)

            if exit_reason is not None and "tp1" in exit_reason and not trade.partial_done:
                partial_vol = round(trade.volume * config.SMC_PARTIAL_CLOSE_PCT, 2)
                remaining = round(trade.volume - partial_vol, 2)
                direction = 1 if trade.side == "buy" else -1
                partial_pnl = (exit_price - trade.entry) * direction * partial_vol * cfg.money_per_price_unit_per_lot
                partial_pnl -= cfg.commission_per_lot * partial_vol
                balance += partial_pnl
                trades.append({
                    "side": trade.side, "entry": trade.entry, "exit": exit_price,
                    "pnl": partial_pnl, "reason": "partial_close_tp1",
                    "volume": partial_vol, "bar": i,
                })
                if remaining >= cfg.volume_min:
                    trade.volume = remaining
                    trade.partial_done = True
                    trade.sl = trade.entry  # breakeven
                    exit_price, exit_reason = None, None
                else:
                    trade = None
                    exit_price, exit_reason = None, None

            if exit_price is not None and trade is not None:
                direction = 1 if trade.side == "buy" else -1
                pnl = (exit_price - trade.entry) * direction * trade.volume * cfg.money_per_price_unit_per_lot
                pnl -= cfg.commission_per_lot * trade.volume
                slip = cfg.slippage_pips * cfg.pip_size
                pnl -= slip * trade.volume * cfg.money_per_price_unit_per_lot
                balance += pnl
                trades.append({
                    "side": trade.side, "entry": trade.entry, "exit": exit_price,
                    "pnl": pnl, "reason": exit_reason, "volume": trade.volume, "bar": i,
                })
                trade = None

        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

        if trade is not None:
            continue

        m5_window = m5_frame.iloc[max(0, i - 499) : i + 1].reset_index(drop=True)
        m15_window = _align_htf(m5_time, m15_frame, 200)
        h1_window = _align_htf(m5_time, h1_frame, 300) if h1_frame is not None and cfg.use_h1 else None

        vp_snapshot = None
        if vp is not None:
            try:
                vp_snapshot = vp.snapshot_before(m5_time.to_pydatetime() if hasattr(m5_time, "to_pydatetime") else m5_time)
            except (ValueError, RuntimeError):
                pass

        if m15_window is None:
            continue

        decision = strategy.decide(m5_window, m15_window, h1=h1_window, vp_snapshot=vp_snapshot)
        action = decision["action"]
        if action not in ("buy", "sell"):
            continue

        entry = decision["entry"]
        sl = decision["sl"]
        risk_dist = abs(entry - sl)
        if risk_dist <= 0:
            continue

        risk_budget = balance * cfg.risk_fraction
        loss_per_lot = risk_dist * cfg.money_per_price_unit_per_lot
        raw_vol = risk_budget / loss_per_lot if loss_per_lot > 0 else 0
        vol = math.floor(raw_vol / cfg.volume_step) * cfg.volume_step
        vol = round(max(cfg.volume_min, min(vol, cfg.volume_max)), 2)
        if vol < cfg.volume_min:
            continue

        trade = _OpenTrade(
            side=action, entry=entry, sl=sl,
            tp1=decision["tp1"], tp2=decision["tp2"],
            volume=vol, bar_index=i,
        )

    return _report(trades, balance, cfg, m5_frame)


def _report(trades, final_balance, cfg, m5_frame):
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "gross_profit": 0, "gross_loss": 0,
            "profit_factor": 0, "max_drawdown_pct": 0,
            "final_balance": round(final_balance, 2),
            "return_pct": 0, "partial_closes": 0, "tp2_hits": 0,
            "sample_status": "LOW SAMPLE", "initial_balance": cfg.initial_balance,
        }

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0

    peak = cfg.initial_balance
    max_dd = 0.0
    bal = cfg.initial_balance
    for t in trades:
        bal += t["pnl"]
        peak = max(peak, bal)
        dd = (peak - bal) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    partial_trades = [t for t in trades if t["reason"] == "partial_close_tp1"]
    tp2_trades = [t for t in trades if t["reason"] == "take_profit_tp2"]

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_pnl": round(total_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "max_drawdown_pct": round(max_dd, 2),
        "final_balance": round(final_balance, 2),
        "return_pct": round((final_balance - cfg.initial_balance) / cfg.initial_balance * 100, 2),
        "partial_closes": len(partial_trades),
        "tp2_hits": len(tp2_trades),
        "sample_status": "PASS SAMPLE" if len(trades) >= cfg.min_trades else "LOW SAMPLE",
        "initial_balance": cfg.initial_balance,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="SMC XAUUSD M5 Backtester")
    parser.add_argument("--m5-csv", required=True)
    parser.add_argument("--m15-csv", required=True)
    parser.add_argument("--h1-csv", default=None)
    parser.add_argument("--balance", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.005)
    parser.add_argument("--no-vp", action="store_true")
    parser.add_argument("--no-h1", action="store_true")
    parser.add_argument("--output", default="exness_bot/logs/smc_backtest_trades.csv")
    args = parser.parse_args(argv)

    m5 = load_csv(args.m5_csv)
    m15 = load_csv(args.m15_csv)
    h1 = load_csv(args.h1_csv) if args.h1_csv else None

    cfg = SMCBacktestConfig(
        initial_balance=args.balance,
        risk_fraction=args.risk,
        use_vp=not args.no_vp,
        use_h1=not args.no_h1,
    )

    report = run(m5, m15, h1, cfg)
    print("\n=== SMC Backtest Report ===")
    for k, v in report.items():
        print(f"  {k:25s}: {v}")
    print()


if __name__ == "__main__":
    main()
