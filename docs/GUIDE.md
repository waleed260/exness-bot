# Exness Bot — Step-by-Step Operator Guide

This guide is deliberately honest about the current boundary: Phase B and Phase D are implemented and tested; Phase C execution hardening and real Phase E validation are not complete.

## 1. Choose the path

### Research path — VP_BREAKOUT_M5_V1

Use these modules:

- `exness_bot/volume_profile.py`
- `exness_bot/vp_breakout_strategy.py`
- `exness_bot/vp_risk.py`
- `exness_bot/vp_backtest.py`

This path implements the profile → breakout → next-candle trigger → fixed-risk lifecycle and is covered by Phase B/Phase D tests. It is not wired into `runner.py`.

### MT5 demo path — legacy control

`python -m exness_bot.runner` currently runs the legacy SMA/RSI/ATR strategy from `strategy.py`. It is useful for controlled demo plumbing only. It is not a demo deployment of the Phase B XAUUSD strategy.

## 2. Install and configure MT5 demo access

1. Install Exness MT5 on Windows.
2. Log into a separate demo account.
3. Enable **Allow algorithmic trading** in MT5.
4. Create the private credential file:

```bat
copy exness_bot\settings.example.py exness_bot\settings.py
```

5. Edit `exness_bot/settings.py`:

```python
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 12345678
MT5_PASSWORD = "your-demo-password"
MT5_SERVER = "your-demo-server"
```

6. Edit `exness_bot/config.py`:

```python
SYMBOL = "EURUSD"             # exact symbol/base name available in MT5
MAGIC = 20240601              # unique bot identifier
DEMO_ONLY = True
EXECUTION_MODE = "demo"
DRY_RUN = True
LIVE_TRADING_ENABLED = False
```

`DEMO_ONLY` is checked against the MT5 account mode before the main loop. A real account is rejected. The current source does not make the constant immutable: it is a configuration flag with additional live gates. Treat it as mandatory and do not change it.

## 3. Run a no-order dry run

```bat
python -m exness_bot.runner
```

With `DRY_RUN=True`, the runner may calculate and log a legacy signal, but the executor must not call `order_send`.

Review:

- `exness_bot/logs/bot.log`
- `exness_bot/logs/trades.csv`
- symbol resolution
- demo account identity
- spread and rejected-entry reasons

Stop with `Ctrl+C` or create `exness_bot/STOP_TRADING`.

## 4. Allow demo orders only after review

Change only:

```python
EXECUTION_MODE = "demo"
DRY_RUN = False
DEMO_ONLY = True
LIVE_TRADING_ENABLED = False
```

Then confirm MT5 is still logged into the demo account and restart the process. The current runner will submit legacy strategy orders if its SMA/RSI/ATR signal and safety checks approve them. It will not submit Phase B volume-profile orders.

## 5. Actual Phase B strategy flow

The implemented Phase B modules work as follows:

1. A new volume-profile session starts at 03:00 UTC.
2. Prior closed candles build the 70% profile.
3. VAH becomes GREEN and VAL becomes RED.
4. A close strictly above GREEN creates a BUY setup; a close strictly below RED creates a SELL setup.
5. The breakout high/low and deterministic ID are frozen.
6. Only the next candle is watched for an intrabar trigger.
7. A trigger creates one trade; no trigger expires the setup.
8. The risk module creates exactly 30-pip SL and 40-pip TP.
9. Sizing targets 0.5% of balance and quantizes downward.
10. A minimum lot that exceeds the budget rejects the trade.
11. Two consecutive losses or 2% daily realized loss blocks new entries.

This is currently Phase B research/backtest behavior, not the behavior of the MT5 runner.

## 6. Phase D backtesting

Use real XAUUSD history only for Phase E:

```bash
python -m exness_bot.vp_backtest --csv path/to/XAUUSD_M5.csv
```

Expected columns:

```text
time,open,high,low,close,volume
```

Preferred resolution is tick or M1. M5 OHLC runs at Level 2 and has lower confidence because exact intrabar ordering is unavailable. The engine reports costs, sizing, drawdown, expectancy, trade count, rejection reasons, and `INSUFFICIENT SAMPLE` when fewer than 100 trades are available.

No genuine Phase E dataset is currently in this repository.

## 7. Safety boundary

This project is experimental and unvalidated:

- No proven backtest edge.
- No genuine XAUUSD baseline.
- No completed Phase C execution hardening.
- No production broker reconciliation guarantee.
- No demo result that proves future profitability.
- No live use authorized.

The latest mock behavior check confirmed:

```text
DEMO_GUARD: True ok
DEMO_ORDER_SEND_CALLS: 1
DEMO_RESULT_RETCODE: 10009
LIVE_WITH_DEMO_ONLY: False live account rejected by DEMO_ONLY
```

That proves the current guard allows valid demo execution and rejects live execution while `DEMO_ONLY=True`; it does not prove the strategy is safe or profitable.
