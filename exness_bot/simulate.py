"""Run the existing rule strategy against CSV candles in local simulation.

Usage:
    python -m exness_bot.simulate --csv data/EURUSD_M15.csv

This command never imports MetaTrader5 and never submits external orders.
"""

import argparse
import os

import pandas as pd

from exness_bot import backtest
from exness_bot import config
from exness_bot import indicators
from exness_bot import safety
from exness_bot import simulator
from exness_bot import strategy


def run(df, state_path=None):
    df = indicators.add_indicators(df.copy())
    warmup = max(config.SMA_SLOW, config.TREND_SMA) + config.TREND_SLOPE_LOOKBACK + 2
    sim = simulator.Simulator(state_path)
    guard = safety.SafetyState(f"{state_path}.risk" if state_path else None)
    guard.reconcile_open_positions(len(sim.open_positions()), config.RISK_PER_TRADE_PCT)
    decisions = []

    for i in range(warmup, len(df)):
        bar = df.iloc[i]
        # Use the conservative order when a candle touches both levels: low first
        # for long positions and high first for short positions.
        for price in ((bar["low"], bar["high"]) if sim.open_positions() and sim.open_positions()[0].side == "buy"
                      else (bar["high"], bar["low"])):
            sim.on_price(price)
            if not sim.open_positions():
                break

        window = df.iloc[:i + 1]
        snap = indicators.snapshot(window)
        position = sim.open_positions()
        side = position[0].side if position else None
        decision = strategy.rule_based(snap, side)
        decisions.append(decision["action"])

        if decision["action"] == "close" and position:
            sim.close(position[0].ticket, float(bar["close"]), "strategy_exit")
            guard.record_close(position[0].pnl, config.RISK_PER_TRADE_PCT)
            continue

        if decision["action"] not in {"buy", "sell"} or position:
            continue
        if not indicators.session_ok(bar["time"]):
            continue
        atr_value = float(bar["atr"])
        if pd.isna(atr_value) or atr_value <= 0:
            continue
        entry = float(bar["close"])
        sl_distance = config.SL_ATR_MULT * atr_value
        tp_distance = config.TP_ATR_MULT * atr_value
        if decision["action"] == "buy":
            sl, tp = entry - sl_distance, entry + tp_distance
        else:
            sl, tp = entry + sl_distance, entry - tp_distance
        valid, _ = safety.validate_order(
            side=decision["action"], volume=config.FIXED_LOT_FALLBACK,
            price=entry, sl=sl, tp=tp, state=guard,
            existing_positions=len(sim.open_positions()), account_exposure_pct=config.RISK_PER_TRADE_PCT,
        )
        if valid:
            sim.open(decision["action"], config.FIXED_LOT_FALLBACK, entry, sl, tp, str(bar["time"]))
            guard.record_open(config.RISK_PER_TRADE_PCT)

    return sim, {"bars": len(df), "decisions": len(decisions),
                  "opens": decisions.count("buy") + decisions.count("sell"),
                  "open_positions": len(sim.open_positions())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="CSV with time,open,high,low,close columns")
    ap.add_argument("--state", default="exness_bot/logs/simulation_state.json")
    args = ap.parse_args()
    df = backtest._load_csv(args.csv)
    os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
    _, report = run(df, args.state)
    print("Local simulation complete")
    for key, value in report.items():
        print(f"{key}: {value}")
    print("external orders: 0")


if __name__ == "__main__":
    main()
