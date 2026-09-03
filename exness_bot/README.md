# exness_bot — Exness (MT5) auto-trading adaptation

Adapts the *decision idea* from StockAgent ("ask an LLM for a JSON trade
decision") to a **live Exness MetaTrader 5 account**. The simulated market, the
internal order-matching engine and the fake financial reports from the research
project are **not used** — pricing, matching and settlement are done by the
broker.

> **Risk warning.** Automated FX/CFD trading loses money for most retail
> traders. This code is a *starting point*, is **not tested against a live
> account**, and is not financial advice. Backtest it, then run it on a **demo
> account** for weeks before you consider real funds. Trading bots are allowed by
> Exness, but arbitrage / latency / tick-scalping style exploits are not — keep
> the strategy "normal".

## Honest expectations
- Getting it to run correctly on Exness (after some demo debugging): fairly likely.
- Getting *sustained real profit* from the built-in SMA-crossover / generic-LLM
  strategy: unlikely — after spread, swap and commission the edge is not there.
- Engineering makes the bot **robust and testable**. A profitable **edge** has to
  come from a strategy you validate yourself with `backtest.py` + demo.

## Files

| File | Job |
|------|-----|
| `config.py` | every knob. `DRY_RUN=True`, `DEMO_ONLY=True` by default |
| `settings.example.py` | copy to `settings.py`, add MT5 login + (optional) OpenAI key |
| `mt5_client.py` | connect, account, positions, rates; auto-resolves the broker symbol suffix (`EURUSD` → `EURUSDm` etc.), reports spread |
| `indicators.py` | MT5-free indicator math + trailing-stop + session logic, shared by bot and backtest |
| `data.py` | live rates → indicator DataFrame (drops the forming candle) |
| `strategy.py` | LLM decision with a rule-based fallback (SMA crossover + RSI + 200-SMA trend filter) |
| `risk.py` | lot sizing from risk %, ATR SL/TP, break-even + ATR trailing stop, daily-loss guard, session window |
| `executor.py` | `mt5.order_send` for open / close / modify-SL, retries on requote, obeys `DRY_RUN` |
| `runner.py` | loop: manage open position every poll; on each closed candle → data → strategy → filters → risk → execute; logs trades to `logs/trades.csv` |
| `backtest.py` | run the rule-based strategy over history, report edge metrics |

## 1. Backtest first (works anywhere, no Windows needed)

```
pip install pandas numpy
# CSV needs columns: time, open, high, low, close
python -m exness_bot.backtest --csv data/EURUSD_M15.csv
# or, on Windows with MT5 connected:
python -m exness_bot.backtest --mt5 180
```

Output is in **R multiples** (profit ÷ initial risk), plus a fixed-fractional
money curve, max drawdown, profit factor and expectancy, and a blunt
`EDGE / NO EDGE` verdict. Trades are written to `logs/backtest_trades.csv`.
Tune `config.py` and re-run. **Do not forward-test anything the backtest says has
no edge.**

## 2. Setup for live/demo (Windows only — `MetaTrader5` needs Windows)

1. Install **Exness MetaTrader 5**, log into a **demo** account.
2. Terminal → Tools → Options → Expert Advisors → *Allow algorithmic trading*.
3. `pip install -r exness_bot/requirements.txt`
4. `copy exness_bot\settings.example.py exness_bot\settings.py` and fill in
   `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` (e.g. `Exness-MT5Trial`), `MT5_PATH`.
   Leave `OPENAI_API_KEY` empty to use the rule-based strategy only.

## 3. Run

```
python -m exness_bot.runner
```

- `DRY_RUN=True` (default): logs the orders it *would* send, touches nothing.
  Watch `exness_bot/logs/bot.log` and `logs/trades.csv`.
- Happy with the dry run on demo? Set `DRY_RUN=False` to trade the **demo** account.
- Going live is deliberately awkward: `DEMO_ONLY=False` **and**
  `CONFIRM_LIVE_STRING="I ACCEPT THE RISK"`. Start at `MAX_LOT=0.01`.

## Key config knobs

`SYMBOL`, `TIMEFRAME`, `RISK_PER_TRADE_PCT`, `SL_ATR_MULT`/`TP_ATR_MULT`,
`BREAKEVEN_AT_R`/`TRAIL_AT_R`/`TRAIL_ATR_MULT`, `MAX_SPREAD_POINTS`,
`USE_TREND_FILTER`, `SESSION_UTC_HOURS`/`TRADE_DAYS`, `DAILY_MAX_LOSS_PCT`,
`MIN_CONFIDENCE`, `MAX_OPEN_POSITIONS`, and the SMA/RSI/trend periods.
Backtest every change before running it forward.
