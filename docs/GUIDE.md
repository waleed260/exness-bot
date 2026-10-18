# Exness Bot — Step-by-Step Operator Guide

## 1. Choose your strategy

The bot supports three strategies via `config.ACTIVE_STRATEGY`:

| Strategy | Config value | Instrument | Description |
|---|---|---|---|
| **SMC (primary)** | `"smc"` | XAUUSD M5 | Smart Money Concepts: liquidity sweeps, BOS, order blocks, FVG, VP confluence, H1 trend, partial close at TP1 |
| VP Breakout | `"vp_breakout"` | XAUUSD M5 | Volume Profile breakout with next-candle confirmation |
| Legacy SMA | `"sma"` | EURUSD M15 | SMA 20/50 crossover + RSI + trend filter |

Default is `ACTIVE_STRATEGY = "smc"`. To switch, change it in `config.py`.

## 2. Install and configure MT5

1. Install Exness MT5 on Windows.
2. Log into a **demo** account.
3. Enable **Allow algorithmic trading** in MT5 (Tools > Options > Expert Advisors).
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

## 3. Backtest the SMC strategy

Before running live, backtest on historical data.

**Step 1** — Download XAUUSD M5, M15, and H1 CSV data (minimum 3-6 months). Each CSV needs columns:

```text
time,open,high,low,close,volume
```

You can export from MT5: Tools > History Center > XAUUSD > M5/M15/H1 > Export.

**Step 2** — Run the backtester:

```bash
.venv/bin/python -m exness_bot.smc_backtest \
    --m5-csv data/XAUUSD_M5.csv \
    --m15-csv data/XAUUSD_M15.csv \
    --h1-csv data/XAUUSD_H1.csv
```

**Options:**

```
--balance 10000      # starting balance (default 10000)
--risk 0.005         # risk fraction per trade (default 0.5%)
--no-vp              # disable VP confluence scoring
--no-h1              # disable H1 EMA trend scoring
--output path.csv    # trade log output file
```

**Step 3** — Review the report: win rate, profit factor, max drawdown, partial close stats. Target: win rate > 55%, profit factor > 1.5, max DD < 15%.

## 4. Run in simulation mode (no real orders)

```python
# config.py
ACTIVE_STRATEGY = "smc"
EXECUTION_MODE = "simulation"
DRY_RUN = True
DEMO_ONLY = True
LIVE_TRADING_ENABLED = False
```

```bat
python -m exness_bot.runner
```

Review logs:
- `exness_bot/logs/bot.log` — SMC decisions, scores, confluences
- `exness_bot/logs/trades.csv` — intended entries with SL/TP1/TP2

Stop with `Ctrl+C` or create `exness_bot/STOP_TRADING`.

## 5. Run on demo account (real demo orders)

Only after reviewing simulation logs:

```python
# config.py
ACTIVE_STRATEGY = "smc"
EXECUTION_MODE = "demo"
DRY_RUN = False
DEMO_ONLY = True
LIVE_TRADING_ENABLED = False
```

```bat
python -m exness_bot.runner
```

Monitor for 1-2 weeks:
- Partial close execution at TP1
- Breakeven SL modification after TP1
- Trailing stop on remaining position
- Session filter (London 7-11:30, NY 13-17:30 UTC)
- Spread filtering (max 40 points for XAUUSD)

## 6. How the SMC strategy works

The SMC engine runs every closed M5 candle during London/NY sessions:

1. **M15 Bias** — Higher highs + higher lows = bullish; lower highs + lower lows = bearish.
2. **Liquidity Sweep** — Price wicks below swing lows (buys) or above swing highs (sells).
3. **Break of Structure (BOS)** — Close breaks a previous swing point.
4. **Order Block (OB)** — Bearish candle followed by strong bullish move (for buys), inverse for sells.
5. **Fair Value Gap (FVG)** — Gap between candle 1 high and candle 3 low.
6. **Displacement** — Strong body candle >= 0.55 ATR.
7. **Price Action** — Strong close with body >= 55% of candle range.
8. **Premium/Discount** — Above/below equilibrium of recent swing range.
9. **VP Confluence** — Entry near VAL/POC (buys) or VAH/POC (sells) from volume profile.
10. **H1 EMA Trend** — EMA50 > EMA200 on H1 confirms bullish bias (triple timeframe).

**Scoring**: Each condition has weight (bias=2, sweep=2, BOS=2, OB=2, others=1). Minimum score: 9/14. Mandatory: bias + sweep + BOS + OB must all be true.

**Risk management**:
- SL at Order Block / liquidity level + ATR buffer
- TP1 = 1.5R (50% close + breakeven)
- TP2 = 2.5R (remaining 50% + ATR trailing stop)
- Cooldown: 8 bars between trades
- Safety: DailyGuard, emergency stop, signal deduplication, validate_order checks

## 7. VP Breakout backtesting (alternative strategy)

```bash
.venv/bin/python -m exness_bot.vp_backtest --csv path/to/XAUUSD_M5.csv
```

Level-2 OHLC with stop-first conservative exits, spread/commission/swap costs.

## 8. Run all tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Current: **61 tests** covering SMC strategy, SMC backtester, VP breakout, V2 candidate filters, safety/simulator, and execution.

## 9. Safety boundary

- `DRY_RUN = True` and `DEMO_ONLY = True` by default.
- Emergency stop: create `exness_bot/STOP_TRADING` to block all entries.
- DailyGuard: stops trading after 2% daily drawdown.
- Max consecutive losses, max exposure, max spread — all enforced.
- Live trading requires ALL five gates: `EXECUTION_MODE="live"`, `DRY_RUN=False`, `DEMO_ONLY=False`, `LIVE_TRADING_ENABLED=True`, `CONFIRM_LIVE_STRING="I ACCEPT THE RISK"`.
- See `docs/LIVE_TRADING.md` for the full live procedure.
