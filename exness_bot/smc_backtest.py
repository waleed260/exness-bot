"""SMC XAUUSD M5 backtester — Level-2 OHLC with partial close simulation.

Includes walk-forward validation, parameter sensitivity analysis,
Monte Carlo simulation, and enhanced reporting (Sharpe/Sortino/Calmar).

Usage:
    python -m exness_bot.smc_backtest --m5-csv data/XAUUSD_M5.csv --m15-csv data/XAUUSD_M15.csv [--h1-csv data/XAUUSD_H1.csv]
"""

import argparse
import csv
import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict

import pandas as pd
import numpy as np

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
                    "time": str(m5_time),
                    "risk_dist": abs(trade.entry - trade.initial_sl),
                })
                if remaining >= cfg.volume_min:
                    trade.volume = remaining
                    trade.partial_done = True
                    trade.sl = trade.entry
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
                    "time": str(m5_time),
                    "risk_dist": abs(trade.entry - trade.initial_sl),
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
    empty = {
        "trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
        "total_pnl": 0, "gross_profit": 0, "gross_loss": 0,
        "profit_factor": 0, "max_drawdown_pct": 0,
        "final_balance": round(final_balance, 2),
        "return_pct": 0, "partial_closes": 0, "tp2_hits": 0,
        "sample_status": "LOW SAMPLE", "initial_balance": cfg.initial_balance,
        "sharpe_ratio": 0, "sortino_ratio": 0, "calmar_ratio": 0,
        "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        "avg_r_per_trade": 0, "expectancy": 0,
        "trade_list": [],
    }
    if not trades:
        return empty

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

    pnls = [t["pnl"] for t in trades]
    pnl_arr = np.array(pnls)
    mean_pnl = np.mean(pnl_arr)
    std_pnl = np.std(pnl_arr)
    sharpe = (mean_pnl / std_pnl * math.sqrt(252)) if std_pnl > 0 else 0

    downside = pnl_arr[pnl_arr < 0]
    downside_std = np.std(downside) if len(downside) > 0 else 1e-9
    sortino = (mean_pnl / downside_std * math.sqrt(252)) if downside_std > 0 else 0

    annual_return = (final_balance - cfg.initial_balance) / cfg.initial_balance * 100
    calmar = annual_return / max_dd if max_dd > 0 else 0

    max_cw, max_cl, cw, cl = 0, 0, 0, 0
    for t in trades:
        if t["pnl"] > 0:
            cw += 1
            cl = 0
        else:
            cl += 1
            cw = 0
        max_cw = max(max_cw, cw)
        max_cl = max(max_cl, cl)

    r_multiples = []
    for t in trades:
        rd = t.get("risk_dist", 0)
        if rd > 0:
            r_multiples.append(t["pnl"] / (rd * t["volume"] * cfg.money_per_price_unit_per_lot))
    avg_r = np.mean(r_multiples) if r_multiples else 0

    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = np.mean([abs(t["pnl"]) for t in losses]) if losses else 0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

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
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_consecutive_wins": max_cw,
        "max_consecutive_losses": max_cl,
        "avg_r_per_trade": round(float(avg_r), 3),
        "expectancy": round(float(expectancy), 2),
        "trade_list": trades,
    }


# ---- Walk-Forward Validation ----

def walk_forward(m5_frame, m15_frame, h1_frame=None, cfg=None, n_windows=None):
    """Split data into windows, run in-sample + out-of-sample for each pair."""
    if cfg is None:
        cfg = SMCBacktestConfig()
    if n_windows is None:
        n_windows = config.SMC_BT_WALK_FORWARD_WINDOWS

    total = len(m5_frame)
    window_size = total // n_windows
    if window_size < 200:
        return {"error": "not enough data for walk-forward", "windows": 0}

    results = []
    for i in range(n_windows - 1):
        is_start = i * window_size
        is_end = (i + 1) * window_size
        oos_start = is_end
        oos_end = min((i + 2) * window_size, total)

        is_m5 = m5_frame.iloc[is_start:is_end].reset_index(drop=True)
        oos_m5 = m5_frame.iloc[oos_start:oos_end].reset_index(drop=True)

        is_report = run(is_m5, m15_frame, h1_frame, cfg)
        oos_report = run(oos_m5, m15_frame, h1_frame, cfg)

        results.append({
            "window": i + 1,
            "is_trades": is_report["trades"],
            "is_win_rate": is_report["win_rate"],
            "is_pf": is_report["profit_factor"],
            "oos_trades": oos_report["trades"],
            "oos_win_rate": oos_report["win_rate"],
            "oos_pf": oos_report["profit_factor"],
            "oos_pnl": oos_report["total_pnl"],
            "oos_max_dd": oos_report["max_drawdown_pct"],
        })

    oos_pfs = [r["oos_pf"] for r in results if r["oos_trades"] > 0]
    oos_wrs = [r["oos_win_rate"] for r in results if r["oos_trades"] > 0]
    avg_oos_pf = sum(oos_pfs) / len(oos_pfs) if oos_pfs else 0
    avg_oos_wr = sum(oos_wrs) / len(oos_wrs) if oos_wrs else 0

    return {
        "windows": len(results),
        "per_window": results,
        "avg_oos_profit_factor": round(avg_oos_pf, 3),
        "avg_oos_win_rate": round(avg_oos_wr, 1),
        "pass": avg_oos_pf > 1.0 and avg_oos_wr > 45,
    }


# ---- Parameter Sensitivity Analysis ----

def sensitivity_analysis(m5_frame, m15_frame, h1_frame=None, cfg=None, params=None):
    """Vary key params ±10%/±20% and measure stability."""
    if cfg is None:
        cfg = SMCBacktestConfig()

    if params is None:
        params = ["SMC_MIN_SCORE", "SMC_TP1_R", "SMC_TP2_R", "SMC_SL_ATR_BUFFER",
                  "SMC_DISPLACEMENT_ATR", "SMC_BODY_FRAC", "SMC_COOLDOWN_BARS"]

    pct_levels = config.SMC_BT_SENSITIVITY_PCT
    baseline = run(m5_frame, m15_frame, h1_frame, cfg)
    results = {"baseline": {
        "pf": baseline["profit_factor"], "wr": baseline["win_rate"],
        "pnl": baseline["total_pnl"], "trades": baseline["trades"],
    }, "params": {}}

    for param_name in params:
        original = getattr(config, param_name, None)
        if original is None or not isinstance(original, (int, float)):
            continue

        param_results = {}
        for pct in pct_levels:
            for direction in [-1, 1]:
                mult = 1 + direction * pct / 100
                new_val = type(original)(original * mult)
                setattr(config, param_name, new_val)
                try:
                    report = run(m5_frame, m15_frame, h1_frame, cfg)
                    label = f"{'+' if direction > 0 else '-'}{pct}%"
                    param_results[label] = {
                        "value": round(new_val, 4) if isinstance(new_val, float) else new_val,
                        "pf": report["profit_factor"],
                        "wr": report["win_rate"],
                        "pnl": report["total_pnl"],
                        "trades": report["trades"],
                    }
                finally:
                    setattr(config, param_name, original)

        fragile = any(r["pf"] < 1.0 for r in param_results.values()) if param_results else False
        results["params"][param_name] = {"variations": param_results, "fragile": fragile}

    return results


# ---- Monte Carlo Simulation ----

def monte_carlo(trades, n_simulations=None, cfg=None):
    """Shuffle trade order and replay equity curve to measure robustness."""
    if cfg is None:
        cfg = SMCBacktestConfig()
    if n_simulations is None:
        n_simulations = config.SMC_BT_MONTE_CARLO_RUNS

    pnls = [t["pnl"] for t in trades]
    if len(pnls) < 5:
        return {"error": "not enough trades", "simulations": 0}

    max_dds = []
    final_bals = []

    for _ in range(n_simulations):
        shuffled = pnls.copy()
        random.shuffle(shuffled)
        bal = cfg.initial_balance
        peak = bal
        max_dd = 0.0
        for p in shuffled:
            bal += p
            peak = max(peak, bal)
            dd = (peak - bal) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        max_dds.append(max_dd)
        final_bals.append(bal)

    max_dds_arr = np.array(max_dds)
    final_bals_arr = np.array(final_bals)

    return {
        "simulations": n_simulations,
        "dd_p50": round(float(np.percentile(max_dds_arr, 50)), 2),
        "dd_p95": round(float(np.percentile(max_dds_arr, 95)), 2),
        "dd_p99": round(float(np.percentile(max_dds_arr, 99)), 2),
        "bal_p5": round(float(np.percentile(final_bals_arr, 5)), 2),
        "bal_p50": round(float(np.percentile(final_bals_arr, 50)), 2),
        "bal_p95": round(float(np.percentile(final_bals_arr, 95)), 2),
        "prob_positive": round(float((final_bals_arr > cfg.initial_balance).mean() * 100), 1),
        "prob_ruin": round(float((final_bals_arr < cfg.initial_balance * 0.5).mean() * 100), 1),
    }


# ---- CSV Export ----

def export_trades_csv(trades, path):
    """Write trade list to CSV."""
    if not trades:
        return
    fieldnames = ["side", "entry", "exit", "pnl", "reason", "volume", "bar", "time", "risk_dist"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)


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
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward validation")
    parser.add_argument("--sensitivity", action="store_true", help="Run parameter sensitivity analysis")
    parser.add_argument("--monte-carlo", action="store_true", help="Run Monte Carlo simulation")
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
        if k == "trade_list":
            continue
        print(f"  {k:25s}: {v}")

    if report.get("trade_list"):
        export_trades_csv(report["trade_list"], args.output)
        print(f"\n  Trades exported to: {args.output}")

    if args.walk_forward:
        print("\n=== Walk-Forward Validation ===")
        wf = walk_forward(m5, m15, h1, cfg)
        for k, v in wf.items():
            if k == "per_window":
                for w in v:
                    print(f"  Window {w['window']}: IS pf={w['is_pf']} wr={w['is_win_rate']}% | OOS pf={w['oos_pf']} wr={w['oos_win_rate']}%")
            else:
                print(f"  {k:25s}: {v}")

    if args.monte_carlo and report.get("trade_list"):
        print("\n=== Monte Carlo Simulation ===")
        mc = monte_carlo(report["trade_list"], cfg=cfg)
        for k, v in mc.items():
            print(f"  {k:25s}: {v}")

    if args.sensitivity:
        print("\n=== Parameter Sensitivity ===")
        sa = sensitivity_analysis(m5, m15, h1, cfg)
        print(f"  Baseline: pf={sa['baseline']['pf']} wr={sa['baseline']['wr']}%")
        for pname, pdata in sa["params"].items():
            fragile_tag = " [FRAGILE]" if pdata["fragile"] else ""
            print(f"  {pname}{fragile_tag}:")
            for level, vals in pdata["variations"].items():
                print(f"    {level}: val={vals['value']} pf={vals['pf']} wr={vals['wr']}% trades={vals['trades']}")

    print()


if __name__ == "__main__":
    main()
