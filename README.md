# exness_bot — LLM + rule-based auto-trading bot for Exness (MetaTrader 5)

A small, safe-by-default trading bot for an **Exness MT5** account. On every
closed candle it builds a market snapshot, asks either an LLM or a built-in
rule set for a `buy / sell / close / hold` decision, sizes the trade by risk,
attaches an ATR stop/target, and manages the position with a break-even + ATR
trailing stop.

It ships with a **backtester** so you can check whether a strategy actually has
an edge before risking anything.

> **Risk warning.** Automated FX/CFD trading loses money for most retail
> traders. This is a starting point, **not tested against a live account**, and
> not financial advice. Backtest it, then run it on a **demo account** for weeks
> before considering real funds. Algo trading is allowed by Exness;
> arbitrage / latency / tick-scalping style exploits are not — keep it "normal".

## What it does

| Area | Detail |
|------|--------|
| **Entry** | SMA(fast/slow) crossover, filtered by RSI and a 200-SMA trend filter; or an LLM decision (OpenAI) with the rule set as fallback |
| **Sizing** | lot chosen so a stop-out loses ~`RISK_PER_TRADE_PCT` of balance |
| **Stop / target** | `SL = SL_ATR_MULT × ATR`, `TP = TP_ATR_MULT × ATR`, clamped to the broker minimum |
| **Position management** | move stop to break-even at +1R, then ATR-trail from +1.5R |
| **Entry filters** | max spread, trading-session window (UTC hours + weekdays), min ATR |
| **Guards** | one position at a time, daily max-loss cut-off, `DRY_RUN`, demo-only lock |
| **Execution** | `mt5.order_send` with retry on requote/price-changed; broker symbol-suffix auto-resolved (`EURUSD` → `EURUSDm` …) |
| **Logging** | `exness_bot/logs/bot.log` + every trade to `exness_bot/logs/trades.csv` |

## Files

```
exness_bot/
  config.py            all settings (DRY_RUN=True, DEMO_ONLY=True by default)
  settings.example.py  copy to settings.py -> MT5 login + optional OpenAI key
  mt5_client.py        connect / account / positions / rates / symbol resolve
  indicators.py        indicator + trailing-stop + session math (no MT5 import)
  data.py              live rates -> indicator DataFrame
  strategy.py          LLM decision + rule-based fallback
  risk.py              lot sizing, SL/TP, trailing stop, daily-loss guard
  executor.py          open / close / modify-SL through MT5, honours DRY_RUN
  runner.py            main loop
  backtest.py          historical test + edge metrics
```

Full walkthrough: **[docs/StockAgent-Exness-Bot-Guide.pdf](docs/StockAgent-Exness-Bot-Guide.pdf)**
(source: [docs/GUIDE.md](docs/GUIDE.md)).

## Quick start

### 1. Backtest (any OS, no MT5 needed)

```
pip install pandas
# CSV columns: time, open, high, low, close
python -m exness_bot.backtest --csv data/EURUSD_M15.csv
```

You get win rate, profit factor, expectancy (in R), max drawdown and a blunt
`EDGE / NO EDGE` verdict, plus `exness_bot/logs/backtest_trades.csv`.
**Do not forward-test a strategy the backtest says has no edge.**

### 2. Demo (Windows only — the `MetaTrader5` package needs Windows)

```
pip install -r requirements.txt
copy exness_bot\settings.example.py exness_bot\settings.py   # then edit it
python -m exness_bot.runner
```

`DRY_RUN=True` logs the orders it *would* place without touching the account.
When it looks right on demo, set `DRY_RUN=False` (still a demo account).

### 3. Live

Deliberately awkward: in `config.py` set `DEMO_ONLY=False` **and**
`CONFIRM_LIVE_STRING="I ACCEPT THE RISK"`, keep `MAX_LOT=0.01`, and only after
weeks of profitable demo results.

## How good is it for Exness, really?

- **Will it run correctly on Exness?** After a day or two of demo debugging
  (server name, symbol suffix, terminal path): likely yes.
- **Will the built-in strategy make real money?** Unlikely as-is. A basic SMA
  crossover / generic LLM prompt has no proven edge, and spread + swap +
  commission make the expected value negative. The value here is the
  **framework**: safe execution, risk control, and a backtester to find and
  verify an edge you bring yourself.

## Licence

MIT — see `LICENSE`.
