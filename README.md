# Exness Bot — Current Repository Guide

## 1. Current status — facts only

This repository contains two separate tracks:

- **Phase B: DONE and tested** — the VP_BREAKOUT_M5_V1 volume profile, breakout state machine, and fixed-risk module exist as independent modules.
- **Phase D: DONE and tested** — `vp_backtest.py` calls the Phase B modules directly and produces a Level-2 OHLC report.
- **Phase C: NOT DONE** — broker `order_check`, full broker-aware execution hardening, fill reconciliation, partial fills, slippage ledger, and durable V1 lifecycle persistence are not implemented.
- **Phase E: NOT DONE** — no genuine XAUUSD historical dataset has been supplied or validated. The only Phase E-like run was a synthetic engine smoke test and is not a baseline result.
- **V2 integration: NOT DONE** — V2 filters remain separate candidate code and are not wired into the V1 engine.
- **Demo/live production readiness: NOT DONE** — no production execution claim is made.

The latest verified repository state has 47 passing tests. The exact production strategy is not yet connected to the MT5 runner. The current MT5 runner still uses the legacy SMA/RSI/ATR strategy.

## 2. File map

Phase B modules:

- `exness_bot/volume_profile.py` — 03:00 UTC session reset, 70% VAH/VAL/POC profile, anti-lookahead snapshot.
- `exness_bot/vp_breakout_strategy.py` — closed breakout and next-candle trigger state machine.
- `exness_bot/vp_risk.py` — fixed 30/40 pip geometry, 0.5% risk sizing, daily guards, spread check.

Phase D:

- `exness_bot/vp_backtest.py` — VP_BREAKOUT_M5_V1 Level-2 OHLC backtester.

Legacy control/demo path:

- `exness_bot/runner.py` — current MT5 loop; uses the legacy strategy.
- `exness_bot/strategy.py` — legacy SMA/RSI/trend decisions.
- `exness_bot/risk.py` — legacy ATR-based stops, targets, and sizing.
- `exness_bot/executor.py` — legacy MT5 order submission.
- `exness_bot/config.py` — runtime configuration and safety defaults.
- `exness_bot/settings.py` — private credentials file created locally from `settings.example.py`; never commit it.

The Phase B modules are not silently substituted into the legacy runner. This distinction is intentional and currently unresolved.

## 3. Warnings

This is experimental, unvalidated trading code.

- There is no backtest-proven edge.
- There is no genuine Phase E XAUUSD baseline result.
- The synthetic smoke result is not evidence of profitability.
- Phase C execution hardening is incomplete.
- The current MT5 runner is the legacy SMA/RSI/ATR path, not the Phase B XAUUSD volume-profile path.
- Demo execution can lose money in a demo account and can expose operational bugs.
- No setting guarantees profit or prevents losses.
- Do not use a live account.

## 4. How the Phase B strategy is supposed to work

The Phase B research path is:

1. At **03:00 UTC**, start a new volume-profile session. Do not carry forward the previous session’s levels.
2. Build the profile from closed candles and calculate the 70% value area: VAH is GREEN and VAL is RED.
3. When a candle closes strictly above GREEN, freeze its high as a BUY breakout candle. A wick alone does nothing.
4. When a candle closes strictly below RED, freeze its low as a SELL breakout candle.
5. Persist one deterministic breakout identity and watch only the immediately following candle.
6. If the next candle breaks the frozen high/low intrabar, trigger one trade at the executable trigger price.
7. If that candle finishes without the trigger, expire the setup.
8. Apply fixed 30-pip SL and 40-pip TP from the actual entry price.
9. Size at 0.5% of balance using broker/account profit math, quantized down to the broker step. If the minimum lot exceeds the risk budget, reject the trade.
10. Stop new entries after two consecutive losses or 2% daily realized loss.

That flow is implemented and tested in the Phase B modules and used by `vp_backtest.py`. It is **not yet the flow executed by `runner.py`**.

## 5. MT5 demo setup for the current runner

This section is for the existing legacy MT5 runner only. It does not turn the Phase B strategy into a live MT5 strategy.

### 5.1 Requirements

- Windows with the Exness MT5 desktop terminal.
- 64-bit Python and project dependencies.
- A separate Exness demo account.
- MT5 logged into that demo account.
- **Tools → Options → Expert Advisors → Allow algorithmic trading** enabled.
- A symbol that exists and is visible in that demo account.

### 5.2 Private account settings

From the repository root:

```bat
copy exness_bot\settings.example.py exness_bot\settings.py
```

Edit `exness_bot/settings.py`:

```python
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 12345678
MT5_PASSWORD = "your-demo-password"
MT5_SERVER = "your-demo-server"
```

These are connection credentials, not strategy parameters. Keep the file private; it is ignored by Git.

### 5.3 Demo runtime configuration

Edit `exness_bot/config.py`.

For a no-order dry run first:

```python
SYMBOL = "EURUSD"             # use the exact base symbol available to the demo account
MAGIC = 20240601              # unique identifier for this bot
DEMO_ONLY = True              # reject a real account
EXECUTION_MODE = "demo"      # connect to MT5 in demo mode
DRY_RUN = True                # log intended orders; do not call order_send
LIVE_TRADING_ENABLED = False
```

Run:

```bat
python -m exness_bot.runner
```

After reviewing the logs, the current legacy runner can be configured to submit demo orders with:

```python
EXECUTION_MODE = "demo"
DRY_RUN = False
DEMO_ONLY = True
LIVE_TRADING_ENABLED = False
```

Do not change the symbol or magic number without reviewing position isolation and logs. The current runner’s actual legacy strategy uses the configured M15/SMA/RSI/ATR settings, not the Phase B profile engine.

### 5.4 Stop the demo run

- Press `Ctrl+C` for normal shutdown.
- Create `exness_bot/STOP_TRADING` to block new entries.
- Inspect `exness_bot/logs/bot.log` and `exness_bot/logs/trades.csv`.
- Remove the stop file only after reviewing why it was created.

## 6. What DEMO_ONLY actually does

When `DEMO_ONLY=True`, `runner.py` calls the environment guard before entering its loop. A real MT5 account is rejected with `live account rejected by DEMO_ONLY`. A demo account with `EXECUTION_MODE="demo"` is accepted.

Important implementation fact: **DEMO_ONLY is not hardcoded in the current source.** It defaults to `True` in `config.py` and is passed into `safety.environment_allows_execution()`. A local code/config change can set it to `False, subject to the separate live-mode, confirmation, and `LIVE_TRADING_ENABLED` gates. Therefore the current repository must not describe DEMO_ONLY as an immutable compile-time lock. Making that policy hardcoded would be a separate safety change, not part of Phase B or Phase D.

The explicit mock test produced:

```text
DEMO_GUARD: True ok
DEMO_ORDER_SEND_CALLS: 1
DEMO_RESULT_RETCODE: 10009
LIVE_WITH_DEMO_ONLY: False live account rejected by DEMO_ONLY
```

So valid DEMO mode is not unconditionally refused, and LIVE is refused when DEMO_ONLY is enabled.

## 7. Phase D backtester

Run it only with real historical data when performing Phase E:

```bash
python -m exness_bot.vp_backtest --csv path/to/XAUUSD_M5.csv
```

The engine currently supports **Level-2 OHLC** data. It does not claim tick-level chronology. It handles gaps, entry-bar exits, conservative stop-first ambiguity, actual risk-sized volume, spread, commission, swap, slippage fields, and the section 24 report. It prints `INSUFFICIENT SAMPLE` below 100 trades.

A genuine Phase E run requires real XAUUSD data. Preferred input is tick or M1; M5 is acceptable as a lower-confidence screening run. Synthetic data must not be used as a baseline.

## 8. Verification

Run all tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Current verified result: **47 tests passed**.

Passing tests prove code behavior covered by those tests. They do not prove profitability, broker compatibility, execution safety, or a production trading edge.
