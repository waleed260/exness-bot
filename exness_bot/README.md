# exness_bot — Exness (MT5) auto-trading adaptation

This folder adapts the *decision idea* from StockAgent ("ask an LLM for a JSON
trade decision") to a **live Exness MetaTrader 5 account**. The simulated market,
the internal order-matching engine and the fake financial reports from the
research project are **not used** — pricing, matching and settlement are done by
the broker.

> **Risk warning.** Automated FX/CFD trading can lose money fast. This code is
> provided as a starting point, is **not tested against a live account**, and is
> not financial advice. Run it on a **demo account** for a long time before you
> even think about real funds. Trading bots are allowed by Exness, but
> arbitrage / latency / tick-scalping style exploits are not — keep the strategy
> "normal".

## What's here

| File | Job |
|------|-----|
| `config.py` | all knobs. `DRY_RUN=True` and `DEMO_ONLY=True` by default |
| `settings.example.py` | copy to `settings.py`, add MT5 login + (optional) OpenAI key |
| `mt5_client.py` | connect / account / positions / rates |
| `data.py` | rates → DataFrame + SMA / RSI / ATR, drops the forming candle |
| `strategy.py` | LLM decision with a rule-based (SMA crossover + RSI) fallback |
| `risk.py` | lot sizing from risk %, ATR-based SL/TP, daily loss guard |
| `executor.py` | `mt5.order_send` for open / close, obeys `DRY_RUN` |
| `runner.py` | main loop: on each closed candle → data → strategy → risk → execute |

## Setup (Windows — `MetaTrader5` only runs on Windows)

1. Install the **Exness MetaTrader 5** terminal and log into a **demo** account.
2. In the terminal: *Tools → Options → Expert Advisors → Allow algorithmic trading*.
3. Python 3.10+:
   ```
   cd Stockagent
   pip install -r exness_bot/requirements.txt
   ```
4. Create the local config (git-ignored):
   ```
   copy exness_bot\settings.example.py exness_bot\settings.py
   ```
   Fill in `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` (e.g. `Exness-MT5Trial`),
   `MT5_PATH`. Leave `OPENAI_API_KEY` empty to use the rule-based strategy only.

## Run

```
python -m exness_bot.runner
```

- With `DRY_RUN=True` (default) it logs the orders it *would* send — nothing hits
  the account. Watch `exness_bot/logs/bot.log`.
- When the dry-run behaviour looks right on demo, set `DRY_RUN=False` in
  `config.py` to let it actually trade the **demo** account.
- Going live is deliberately awkward: set `DEMO_ONLY=False` **and**
  `CONFIRM_LIVE_STRING="I ACCEPT THE RISK"`. Start with `MAX_LOT=0.01`.

## Tuning

Everything is in `config.py`: `SYMBOL`, `TIMEFRAME`, `RISK_PER_TRADE_PCT`,
`SL_ATR_MULT` / `TP_ATR_MULT`, `DAILY_MAX_LOSS_PCT`, `MIN_CONFIDENCE`,
`MAX_OPEN_POSITIONS`, and the SMA/RSI periods. Backtest your changes before
running them forward.
