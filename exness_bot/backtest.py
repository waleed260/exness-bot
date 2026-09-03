"""Backtest the rule-based strategy on historical candles.

Why: you cannot know whether a strategy has an edge until you test it on data it
has never seen. Run this BEFORE forward-testing on demo, and again whenever you
change the strategy or its parameters.

Data source (pick one):
  --csv PATH     CSV with columns: time, open, high, low, close  (extra cols ok)
  --mt5 DAYS     pull the last DAYS days of config.TIMEFRAME candles from MT5

Results are in R multiples (profit / initial risk) so they do not depend on lot
size or account currency. A money curve is added using config.RISK_PER_TRADE_PCT
fixed-fractional compounding from config.BT_START_BALANCE. Spread cost
(config.BT_SPREAD_POINTS) is deducted from every trade.

  python -m exness_bot.backtest --csv data/EURUSD_M15.csv
  python -m exness_bot.backtest --mt5 180
"""

import argparse
import math

import pandas as pd

from exness_bot import config
from exness_bot import indicators
from exness_bot import strategy


# --------------------------------------------------------------------------- #
def _load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    rename = {"date": "time", "datetime": "time", "<date>": "time", "<open>": "open",
              "<high>": "high", "<low>": "low", "<close>": "close", "gmt time": "time"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    need = {"time", "open", "high", "low", "close"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing columns: {missing}")
    df["time"] = pd.to_datetime(df["time"])
    return df[["time", "open", "high", "low", "close"]].reset_index(drop=True)


def _load_mt5(days):
    import MetaTrader5 as mt5
    from exness_bot import mt5_client
    mt5_client.connect()
    sym_info = mt5_client.resolve_symbol()
    utc_to = pd.Timestamp.utcnow().to_pydatetime()
    utc_from = utc_to - pd.Timedelta(days=days).to_pytimedelta()
    raw = mt5.copy_rates_range(mt5_client.resolved_symbol(), config.TIMEFRAME, utc_from, utc_to)
    mt5_client.shutdown()
    if raw is None or len(raw) == 0:
        raise SystemExit("MT5 returned no data")
    df = pd.DataFrame(raw)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df[["time", "open", "high", "low", "close"]].reset_index(drop=True), sym_info.point


# --------------------------------------------------------------------------- #
def run(df, point):
    df = indicators.add_indicators(df.copy())
    warmup = max(config.SMA_SLOW, config.TREND_SMA) + config.TREND_SLOPE_LOOKBACK + 2
    spread_cost = config.BT_SPREAD_POINTS * point

    trades = []
    pos = None  # dict: side, entry, sl, tp, risk, atr, entry_i

    for i in range(warmup, len(df) - 1):
        window = df.iloc[: i + 1]
        snap = indicators.snapshot(window)
        bar = df.iloc[i]
        nxt = df.iloc[i + 1]  # fills happen on the next bar

        if pos is not None:
            hi, lo = nxt["high"], nxt["low"]
            exit_price = None
            if pos["side"] == "buy":
                if lo <= pos["sl"]:
                    exit_price = pos["sl"]
                elif hi >= pos["tp"]:
                    exit_price = pos["tp"]
            else:
                if hi >= pos["sl"]:
                    exit_price = pos["sl"]
                elif lo <= pos["tp"]:
                    exit_price = pos["tp"]

            if exit_price is None:
                decision = strategy.rule_based(snap, pos["side"])
                if decision["action"] == "close":
                    exit_price = nxt["open"]

            if exit_price is None:  # trail the stop for next bar
                cand = indicators.trailing_sl(pos["side"], pos["entry"], pos["sl"],
                                              bar["atr"], bar["close"])
                if cand is not None:
                    pos["sl"] = cand
                continue

            pnl_price = (exit_price - pos["entry"]) if pos["side"] == "buy" else (pos["entry"] - exit_price)
            pnl_price -= spread_cost
            r = pnl_price / pos["risk"]
            trades.append({"entry_time": df.iloc[pos["entry_i"]]["time"], "exit_time": nxt["time"],
                           "side": pos["side"], "entry": pos["entry"], "exit": exit_price, "r": r})
            pos = None
            continue

        # flat -> look for an entry (respect the same session filter as live)
        if not indicators.session_ok(nxt["time"]):
            continue
        decision = strategy.rule_based(snap, None)
        if decision["action"] in ("buy", "sell") and decision["confidence"] >= config.MIN_CONFIDENCE:
            atr = bar["atr"]
            if not atr or math.isnan(atr):
                continue
            side = decision["action"]
            entry = nxt["open"] + (spread_cost / 2 if side == "buy" else -spread_cost / 2)
            risk_dist = config.SL_ATR_MULT * atr
            if side == "buy":
                sl, tp = entry - risk_dist, entry + config.TP_ATR_MULT * atr
            else:
                sl, tp = entry + risk_dist, entry - config.TP_ATR_MULT * atr
            pos = {"side": side, "entry": entry, "sl": sl, "tp": tp,
                   "risk": risk_dist, "atr": atr, "entry_i": i + 1}

    return _report(trades, df)


# --------------------------------------------------------------------------- #
def _report(trades, df):
    if not trades:
        print("No trades generated. Loosen filters or use more data.")
        return {}

    rs = [t["r"] for t in trades]
    wins = [x for x in rs if x > 0]
    losses = [x for x in rs if x <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    total_r = sum(rs)
    expectancy = total_r / len(rs)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    bal = config.BT_START_BALANCE
    peak = bal
    max_dd = 0.0
    curve = []
    for r in rs:
        bal *= (1 + (config.RISK_PER_TRADE_PCT / 100.0) * r)
        peak = max(peak, bal)
        max_dd = max(max_dd, (peak - bal) / peak)
        curve.append(bal)

    span_days = (df.iloc[-1]["time"] - df.iloc[0]["time"]).days or 1
    years = span_days / 365.25
    cagr = (bal / config.BT_START_BALANCE) ** (1 / years) - 1 if years > 0 and bal > 0 else float("nan")

    out = pd.DataFrame(trades)
    out["balance_after"] = curve
    out.to_csv("exness_bot/logs/backtest_trades.csv", index=False)

    print("=" * 56)
    print(f" data span      : {df.iloc[0]['time'].date()} -> {df.iloc[-1]['time'].date()} ({span_days} days)")
    print(f" bars           : {len(df)}   timeframe: {config.TIMEFRAME}")
    print(f" trades         : {len(rs)}")
    print(f" win rate       : {len(wins) / len(rs) * 100:.1f}%")
    print(f" avg win / loss : +{(gross_win / len(wins)) if wins else 0:.2f}R / "
          f"-{(gross_loss / len(losses)) if losses else 0:.2f}R")
    print(f" expectancy     : {expectancy:+.3f}R per trade")
    print(f" profit factor  : {pf:.2f}")
    print(f" total          : {total_r:+.1f}R")
    print(f" max drawdown   : {max_dd * 100:.1f}%   (fixed-fractional, {config.RISK_PER_TRADE_PCT}% risk)")
    print(f" balance        : {config.BT_START_BALANCE:.0f} -> {bal:.0f}  ({(bal/config.BT_START_BALANCE-1)*100:+.0f}%)")
    print(f" approx CAGR    : {cagr * 100:.1f}%" if not math.isnan(cagr) else " approx CAGR    : n/a")
    print("=" * 56)
    verdict = "EDGE? maybe — forward test on demo" if expectancy > 0.02 and pf > 1.15 \
        else "NO EDGE — do not trade this as-is"
    print(f" verdict        : {verdict}")
    print(" trades csv     : exness_bot/logs/backtest_trades.csv")
    return {"expectancy_r": expectancy, "profit_factor": pf, "total_r": total_r,
            "max_dd": max_dd, "trades": len(rs)}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="CSV file with time,open,high,low,close")
    g.add_argument("--mt5", type=int, metavar="DAYS", help="pull last N days from MT5")
    args = ap.parse_args()

    import os
    os.makedirs("exness_bot/logs", exist_ok=True)

    if args.csv:
        df = _load_csv(args.csv)
        point = 0.0001 if df["close"].iloc[-1] < 50 else 0.01  # crude fallback for CSV
    else:
        df, point = _load_mt5(args.mt5)

    run(df, point)


if __name__ == "__main__":
    main()
