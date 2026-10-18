# Exness Bot — XAUUSD SMC Trading Bot

## Overview

An automated XAUUSD trading bot powered by Smart Money Concepts (SMC) with multi-timeframe analysis, Volume Profile confluence, and institutional-grade risk management.

**Primary strategy**: SMC on M5 with M15 structure bias, H1 EMA trend, VP confluence, partial close at TP1, breakeven management, and ATR trailing stop.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Backtest on historical data
.venv/bin/python -m exness_bot.smc_backtest \
    --m5-csv data/XAUUSD_M5.csv \
    --m15-csv data/XAUUSD_M15.csv \
    --h1-csv data/XAUUSD_H1.csv

# 3. Run in simulation (no real orders)
python -m exness_bot.runner

# 4. Run tests
.venv/bin/python -m unittest discover -s tests -v
```

See `docs/GUIDE.md` for the full step-by-step operator guide.

## Strategies

| Strategy | Config | Instrument | Timeframe |
|---|---|---|---|
| **SMC (default)** | `ACTIVE_STRATEGY = "smc"` | XAUUSD | M5 + M15 + H1 |
| VP Breakout | `ACTIVE_STRATEGY = "vp_breakout"` | XAUUSD | M5 |
| Legacy SMA | `ACTIVE_STRATEGY = "sma"` | EURUSD | M15 |

## File Map

### SMC Strategy (primary)

- `exness_bot/smc_strategy.py` — Enhanced SMC engine: swings, BOS, OB, FVG, VP confluence, H1 trend, scoring
- `exness_bot/strategy_dispatch.py` — Routes to active strategy based on config
- `exness_bot/smc_backtest.py` — SMC backtester with partial close simulation

### Core Infrastructure

- `exness_bot/runner.py` — Main loop: candle detection, strategy dispatch, partial close/BE/trail management
- `exness_bot/executor.py` — MT5 order execution with retry, partial close support
- `exness_bot/data.py` — Single and multi-timeframe data loading (M5 + M15 + H1)
- `exness_bot/config.py` — All configuration with safe defaults
- `exness_bot/risk.py` — Position sizing, SL/TP, trailing stop, daily guard
- `exness_bot/safety.py` — Fail-closed order validation, emergency stop, signal deduplication
- `exness_bot/indicators.py` — RSI, ATR, SMA, H1 EMA trend, trailing SL math

### Volume Profile

- `exness_bot/volume_profile.py` — Session profile: VAH, VAL, POC computation
- `exness_bot/vp_breakout_strategy.py` — VP breakout state machine
- `exness_bot/vp_risk.py` — VP-specific risk (30/40 pip SL/TP, daily guards)
- `exness_bot/vp_backtest.py` — VP Level-2 OHLC backtester

### Other

- `exness_bot/strategy.py` — Legacy SMA/RSI/trend strategy
- `exness_bot/v2_candidate.py` — V2 filters: H1 trend, volatility, breakout strength, ATR trail
- `exness_bot/simulator.py` — Local broker simulator with partial close support
- `exness_bot/mt5_client.py` — MT5 API wrapper
- `exness_bot/settings.py` — Private credentials (never committed)

## Safety

- `DRY_RUN = True` and `DEMO_ONLY = True` by default
- Emergency stop: create `exness_bot/STOP_TRADING`
- DailyGuard: stops after 2% daily drawdown
- Signal deduplication prevents duplicate entries
- Live trading requires 5 explicit gates (see `docs/LIVE_TRADING.md`)

## Tests

61 tests covering SMC strategy, SMC backtester, VP breakout, V2 filters, safety, simulator, and execution.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Warnings

This is experimental trading software. No backtest result guarantees future profitability. Demo execution can lose money. Always backtest and forward-test on demo before any live consideration. See `docs/GUIDE.md` for the complete procedure.
