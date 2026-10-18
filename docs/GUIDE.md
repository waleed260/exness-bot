# Exness Bot — Step-by-Step Operator Guide

## 1. Choose your strategy

The bot supports three strategies via `config.ACTIVE_STRATEGY`:

| Strategy | Config value | Instrument | Description |
|---|---|---|---|
| **SMC (primary)** | `"smc"` | XAUUSD M5 | Smart Money Concepts: liquidity sweeps, BOS, order blocks, FVG, VP confluence, H1 trend, graduated volume, killzones, news calendar, regime filter, partial close at TP1 |
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

**Basic options:**

```
--balance 10000      # starting balance (default 10000)
--risk 0.005         # risk fraction per trade (default 0.5%)
--no-vp              # disable VP confluence scoring
--no-h1              # disable H1 EMA trend scoring
--output path.csv    # trade log CSV output file
```

**Advanced validation options:**

```
--walk-forward       # run walk-forward validation (split data into 6 windows,
                     # test in-sample vs out-of-sample stability)
--monte-carlo        # shuffle trade order 1000x, compute drawdown
                     # distribution at 50th/95th/99th percentile
--sensitivity        # vary key params ±10%/±20%, flag fragile parameters
```

**Step 3** — Review the report. Enhanced metrics include:

| Metric | Target |
|---|---|
| Win rate | > 55% |
| Profit factor | > 1.5 |
| Max drawdown | < 15% |
| Sharpe ratio | > 1.0 |
| Sortino ratio | > 1.5 |
| Calmar ratio | > 1.0 |
| Walk-forward OOS PF | > 1.0 |
| Monte Carlo P95 DD | < 20% |

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
- Session filter with killzones (London 7-9, NY 13-15, overlap 13-16 UTC)
- DST auto-adjustment (London/NY hours shift automatically)
- News blackout pauses (30min before, 15min after high-impact events)
- Regime filter holding during ranging markets
- Spread filtering (max 40 points for XAUUSD)

## 6. How the SMC strategy works

The SMC engine runs every closed M5 candle during London/NY sessions:

### Confluences (score up to 17)

1. **M15 Bias** (weight 2) — Higher highs + higher lows = bullish; lower = bearish.
2. **Liquidity Sweep** (weight 2) — Price wicks below swing lows (buys) or above swing highs (sells).
3. **Break of Structure** (weight 2) — Close breaks a previous swing point.
4. **Order Block** (weight 2) — Bearish candle + strong bullish follow-through (buys), inverse for sells. OB candle volume verified against 20-bar average.
5. **Displacement** (weight 1) — Strong body candle >= 0.55 ATR.
6. **Fair Value Gap** (weight 1) — Gap between candle 1 high and candle 3 low.
7. **Premium/Discount** (weight 1) — Above/below equilibrium of recent swing range.
8. **Price Action** (weight 1) — Strong close with body >= 55% of candle range.
9. **H1 EMA Trend** (weight 1) — EMA50 > EMA200 on H1 confirms bullish bias (triple timeframe).
10. **VP Confluence** (weight 1) — Entry near VAL/POC (buys) or VAH/POC (sells).
11. **Volume Score** (weight 0/1/2) — Graduated: 0 = no confirmation, 1 = entry or OB volume above average, 2 = volume + directional delta aligns.
12. **Session Quality** (weight 1) — +1 if in killzone or session overlap window.

**Minimum score**: 9/17. **Mandatory**: bias + sweep + BOS + OB must all be true.

### Filters (gate before scoring)

- **Regime filter (multi-indicator)**: Wilder ADX + Bollinger Band squeeze + ATR compression. 2 of 3 indicators agree "ranging" = hold. Uses proper Wilder exponential smoothing.
- **News calendar**: Three-tier detection:
  1. MT5 economic calendar (primary, when available)
  2. Static recurring schedule (NFP, CPI, FOMC, PPI — auto-computed dates)
  3. ATR volatility spike (reactive backup)
  - Pre-event blackout: 30 minutes before high-impact USD events
  - Post-event cooldown: 15 minutes after
- **Session filter**: London (7-11:30) + NY (13-17:30) UTC with automatic DST adjustment. Killzones: London 7-9, NY 13-15, overlap 13-16.
- **Asian session**: Optional (23-05 UTC), disabled by default.

### Risk management

- SL at Order Block / liquidity level + ATR buffer
- TP1 = 1.5R (50% close + breakeven)
- TP2 = 2.5R (remaining 50% + ATR trailing stop)
- Cooldown: 8 bars between trades
- Safety: DailyGuard, emergency stop, signal deduplication, validate_order checks

## 7. Key config parameters

All SMC parameters are in `config.py` under the `SMC_*` prefix:

```python
# ---- Volume (graduated 0/1/2) ----
SMC_VOLUME_DELTA_LOOKBACK = 20     # bars for volume delta calculation
SMC_VOLUME_OB_MULTIPLIER = 1.0    # OB candle volume threshold vs avg

# ---- Session quality / killzones ----
SMC_KILLZONE_LONDON = (7, 9)      # highest-probability London window
SMC_KILLZONE_NY = (13, 15)        # highest-probability NY window
SMC_KILLZONE_OVERLAP = (13, 16)   # London-NY overlap (peak liquidity)
SMC_USE_DST_ADJUST = True         # auto-detect UK/US daylight saving

# ---- News calendar ----
SMC_NEWS_BLACKOUT_BEFORE_MIN = 30  # pause trading 30min before event
SMC_NEWS_BLACKOUT_AFTER_MIN = 15   # pause trading 15min after event
SMC_NEWS_USE_MT5_CALENDAR = True   # try MT5 calendar first
SMC_NEWS_USE_STATIC_SCHEDULE = True # fallback to computed schedule
SMC_FOMC_DATES_2026 = [...]        # update yearly

# ---- Regime detection (multi-indicator) ----
SMC_REGIME_BB_PERIOD = 20          # Bollinger Band period
SMC_REGIME_BB_SQUEEZE_PCT = 20     # squeeze = width below 20th percentile
SMC_REGIME_ATR_FAST = 7            # fast ATR for compression check
SMC_REGIME_ATR_SLOW = 50           # slow ATR for compression check
SMC_REGIME_MIN_RANGING_SIGNALS = 2 # need 2 of 3 indicators to confirm range

# ---- Backtest validation ----
SMC_BT_WALK_FORWARD_WINDOWS = 6   # number of walk-forward splits
SMC_BT_SENSITIVITY_PCT = [10, 20] # param variation percentages
SMC_BT_MONTE_CARLO_RUNS = 1000    # Monte Carlo simulations
```

## 8. VP Breakout backtesting (alternative strategy)

```bash
.venv/bin/python -m exness_bot.vp_backtest --csv path/to/XAUUSD_M5.csv
```

Level-2 OHLC with stop-first conservative exits, spread/commission/swap costs.

## 9. Run all tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Current: **153 tests** covering:
- SMC strategy (regime, news blackout, graduated volume, killzones, DST, sessions)
- Regime module (Wilder ADX, BB squeeze, ATR compression, combined detection)
- News calendar (static schedule, MT5 mock, blackout windows)
- SMC backtester (exit logic, report schema, walk-forward, Monte Carlo)
- VP breakout, V2 candidate filters, safety/simulator, execution

## 10. Safety boundary

- `DRY_RUN = True` and `DEMO_ONLY = True` by default.
- Emergency stop: create `exness_bot/STOP_TRADING` to block all entries.
- DailyGuard: stops trading after 2% daily drawdown.
- Max consecutive losses, max exposure, max spread — all enforced.
- Live trading requires ALL five gates: `EXECUTION_MODE="live"`, `DRY_RUN=False`, `DEMO_ONLY=False`, `LIVE_TRADING_ENABLED=True`, `CONFIRM_LIVE_STRING="I ACCEPT THE RISK"`.
- See `docs/LIVE_TRADING.md` for the full live procedure.
