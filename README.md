# exness_bot — Exness MT5 trading research and safety framework

> **Source of truth for the requested XAUUSD strategy:** [VP_BREAKOUT_M5_V1 specification](docs/STRATEGY_SPEC.md). The repository currently ships a safe legacy SMA/RSI/ATR EURUSD implementation and simulator; the XAUUSD volume-profile production candidate is documented and staged, not falsely presented as complete or profitable. See the [requirements traceability matrix](docs/REQUIREMENTS_TRACEABILITY.md).

A small, safe-by-default trading bot for an **Exness MT5** account. On every
closed candle it builds a market snapshot and applies its deterministic SMA/RSI/
trend rule set for a `buy / sell / close / hold` decision, sizes the trade by risk,
attaches an ATR stop/target, and manages the position with a break-even + ATR
trailing stop.

It ships with a **backtester** so you can check whether a strategy actually has
an edge before risking anything.

> **Risk warning.** Automated FX/CFD trading loses money for most retail
> traders. **No bot — this one included — can guarantee profit or "no losses".**
> The safe-by-default limits here (small size, daily loss cap, a total-loss kill
> switch, DRY-RUN, demo lock) only keep a bad run *small*; they do not make it
> profitable. This is a starting point, **not tested against a live account**, and
> not financial advice. Backtest it, then run it on a **demo account** for weeks
> before considering real funds. Algo trading is allowed by Exness;
> arbitrage / latency / tick-scalping style exploits are not — keep it "normal".

## Current safety and implementation status

The bot is prepared for automated simulation and demo testing, but **live
automatic trading is disabled**. The default execution mode is `simulation` and
`DRY_RUN=True`; the live path refuses to run unless `LIVE_TRADING_ENABLED` is
explicitly changed in a separately reviewed release. See
[the implementation plan](AUTOMATED_SYSTEM_PLAN.md) for the development scope.

The system now includes fail-closed order validation, an emergency stop file
(`exness_bot/STOP_TRADING`), daily trade limits, consecutive-loss protection,
margin/spread/slippage/stale-data checks, persistent risk and signal state, a
local simulator, restart reconciliation, and ambiguity-safe order retries. These controls reduce avoidable execution risk; they do
not eliminate market losses or guarantee profitability.
The supplied final specification defines a separate production candidate: XAUUSD M5 volume-profile breakout, closed-candle confirmation, next-candle intrabar trigger, exact 30-pip SL / 40-pip TP, and 0.5% account-balance risk. Those rules are written in `docs/STRATEGY_SPEC.md`; they must not be silently substituted with the legacy SMA/RSI/ATR rules. The honest current release state is **HOLD** until the production core, realistic backtests, out-of-sample tests, demo telemetry, and release gates have executable evidence.

The documentation/specification quality is rated **9.6/10**. This is an engineering-documentation rating, not a profitability rating.

The second reference amendment is implemented as a separate, independently testable candidate layer in [docs/STRATEGY_V2_AMENDMENT.md](docs/STRATEGY_V2_AMENDMENT.md) and `exness_bot/v2_candidate.py`. It does not change the frozen legacy strategy or claim an edge.

## How to use the bot

You do not need to start with automatic orders. Use these stages:

1. **Backtest:** test the existing strategy on historical candles. Do not continue
   if the result says `NO EDGE`.
2. **Local simulation:** run the bot automatically against a CSV. It makes
   decisions, opens simulated positions, applies SL/TP, trails stops, closes
   positions, and saves recovery state. It cannot contact a broker.
3. **Demo dry-run:** connect to a demo MT5 account with `DRY_RUN=True`. The bot
   reads live demo prices and logs what it would do, but sends no orders.
4. **Demo automatic execution:** only after dry-run review, set
   `EXECUTION_MODE = "demo"` and `DRY_RUN = False`, while keeping
   `DEMO_ONLY = True`. This is the only automatic-order mode described in this
   guide, and it must use a demo account.

The current defaults are safe: `EXECUTION_MODE = "simulation"`, `DRY_RUN = True`,
`DEMO_ONLY = True`, and `LIVE_TRADING_ENABLED = False`. A live account is rejected
by the environment gate, and live mode cannot run while the live gate is false.

### What “automatic trading” means

Once running, the bot repeatedly receives market data, waits for a closed candle,
calculates the existing SMA/RSI/ATR/trend indicators, chooses `BUY`, `SELL`, or
`NO-TRADE`, validates spread/session/data/risk conditions, and then either logs or
submits the permitted demo action. It monitors open positions every poll and can
automatically move the stop to break-even, trail it, close at SL/TP, or close
when the strategy says the trade thesis has changed.

Automatic trading does **not** mean guaranteed profit. It means the software can
make and manage decisions without a human clicking each order. You should still
review the logs and stop the process if behavior is unexpected.

### How to stop it

- Press `Ctrl+C` in the bot window for a normal shutdown.
- To stop new entries immediately, create `exness_bot/STOP_TRADING`. The bot will
  keep existing broker-side SL/TP management but will not open new positions.
- Remove the stop file only after reviewing `bot.log`; it is ignored by Git.
- Check `exness_bot/logs/bot.log` and `trades.csv` after every test session.


## What it does

| Area | Detail |
|------|--------|
| **Entry** | SMA(fast/slow) crossover filtered by RSI and a 200-SMA trend filter |
| **Sizing** | lot chosen so a stop-out loses ~`RISK_PER_TRADE_PCT` of balance |
| **Stop / target** | `SL = SL_ATR_MULT × ATR`, `TP = TP_ATR_MULT × ATR`, clamped to the broker minimum |
| **Position management** | move stop to break-even at +1R, then ATR-trail from +1.5R |
| **Entry filters** | max spread, trading-session window (UTC hours + weekdays), min ATR |
| **Guards** | one position at a time, daily max-loss cut-off, **total-loss kill switch**, `DRY_RUN`, demo-only lock |
| **Execution** | `mt5.order_send` with retry on requote/price-changed **and auto-fallback across FOK/IOC/RETURN filling modes**; broker symbol-suffix auto-resolved (`EURUSD` → `EURUSDm` …); a rejected order is logged, never recorded as a fill |
| **Logging** | `exness_bot/logs/bot.log` + every trade to `exness_bot/logs/trades.csv` |

## Files

```
exness_bot/
  config.py            all settings (DRY_RUN=True, DEMO_ONLY=True by default)
  settings.example.py  copy to settings.py -> MT5 login settings
  mt5_client.py        connect / account / positions / rates / symbol resolve
  indicators.py        indicator + trailing-stop + session math (no MT5 import)
  data.py              live rates -> indicator DataFrame
  strategy.py          deterministic SMA/RSI/trend rule strategy
  risk.py              lot sizing, SL/TP, trailing stop, daily-loss guard
  executor.py          open / close / modify-SL through MT5, honours DRY_RUN
  runner.py            main loop
  backtest.py          historical test + edge metrics
```

Full walkthrough: **[docs/Exness-Bot-Guide.pdf](docs/Exness-Bot-Guide.pdf)**
(source: [docs/GUIDE.md](docs/GUIDE.md)). The PDF opens with a **non-developer
"easy way"** section — install Python, download the ZIP, double-click
`install.bat`, then `run.bat`.

Runs on **Windows 7, 10 and 11** (64-bit). On **Windows 7** use **Python 3.8.10**
(the last version that installs on Win 7); on Windows 10/11 use the latest
Python 3. Backtesting runs on **any OS** (Windows, macOS, Linux).

## Requirements (full list)

**To backtest only** (any OS, no broker needed):

| Need | Detail |
|------|--------|
| OS | Windows, macOS or Linux |
| Python | 3.8–3.12, 64-bit (`Add Python to PATH` during install) |
| Python packages | `pandas`, `numpy` (`pip install pandas`) |
| Data | one CSV of candles with columns `time,open,high,low,close` |

**To trade (demo or live):**

| Need | Detail |
|------|--------|
| OS | **Windows 7 SP1 / 10 / 11, 64-bit** — the `MetaTrader5` package is Windows-only. A Windows VPS counts. |
| Python | **Windows 7 → Python 3.8.10** (last version that installs on Win 7); **Windows 10 / 11 → latest Python 3**. 64-bit, `Add Python to PATH`. |
| Python packages | `MetaTrader5>=5.0.37`, `pandas>=1.3.5`, and `numpy>=1.21` via `pip install -r requirements.txt` |
| Broker terminal | **Exness MetaTrader 5** desktop terminal installed and logged in |
| Exness account | a **demo** account first: login number, password, server (e.g. `Exness-MT5Trial`) |
| Terminal setting | **Tools → Options → Expert Advisors → Allow algorithmic trading** ticked |
| Network | a stable internet connection; the PC/VPS must stay on while the bot runs |
| Disk / RAM | ~1 GB free disk (Python + MT5), 2 GB+ RAM |

Hardware is light: the bot polls every few seconds and holds one position at a
time. Any machine that runs the MT5 terminal comfortably will run the bot.

## Easy way (no coding)

1. Install Python (tick *Add Python to PATH*).
2. Download this repo: green **Code** button → **Download ZIP** → extract.
3. Install Exness MetaTrader 5, log into a **demo** account, enable
   *Allow algorithmic trading*.
4. Double-click **`install.bat`** — it installs everything and opens a settings
   file; paste your demo login/password/server, save.
5. Double-click **`run.bat`** — the bot starts in safe DRY-RUN (no real orders).
6. Results appear in `exness_bot\logs\` (`bot.log`, `trades.csv`).
7. To test on past data: double-click **`backtest.bat`**.

## Quick start (command line)

### 1. Backtest (any OS, no MT5 needed) — do this first

1. `pip install pandas`
2. Get candles as a CSV with columns `time, open, high, low, close`. From the MT5
   terminal: **View → Symbols → (pair) → Bars → M15 → Request → Export Bars**.
   Save to `data/EURUSD_M15.csv`.
3. `python -m exness_bot.backtest --csv data/EURUSD_M15.csv`
   (or, on Windows with MT5 open: `python -m exness_bot.backtest --mt5 180`)
4. Read the verdict. **PASS** = `expectancy > 0` **and** `profit factor > 1.15`
   **and** enough trades (≥ ~100) → forward-test on demo. Anything else = **FAIL**,
   don't trade it — change **one** setting in `config.py` and re-run.
5. Validate a PASS: re-run on another pair, and walk-forward (tune on the first
   half of the data, test on the untouched second half).

Per-trade detail lands in `exness_bot/logs/backtest_trades.csv`. Full step-by-step
with screenshots-worth of detail is **Part 4 of the PDF guide**.
**Do not forward-test a strategy the backtest says has no edge.**

### 2. Local simulation (any OS, no account needed)

To run the existing rule strategy as an automated local simulation:

```
python -m exness_bot.simulate --csv data/EURUSD_M15.csv
```

This uses the persistent simulator, applies simulated SL/TP and strategy exits,
and writes restart state under `exness_bot/logs/`. It never submits an external
order and reports `external orders: 0`.

### 3. Demo automatic test (Windows only — MT5 is Windows-only)

1. Install the Exness MT5 terminal, log into a **demo** account, and enable
   **Tools → Options → Expert Advisors → Allow algorithmic trading**.
2. Install dependencies and create your private settings file:

   ```
   pip install -r requirements.txt
   copy exness_bot\settings.example.py exness_bot\settings.py
   ```

3. Start with these values in `exness_bot/config.py`:

   ```python
   EXECUTION_MODE = "simulation"
   DRY_RUN = True
   DEMO_ONLY = True
   LIVE_TRADING_ENABLED = False
   ```

   Run `python -m exness_bot.runner`. This reads demo prices but sends no order.
4. After reviewing several sessions of logs, change only these two settings for
   automatic **demo** orders:

   ```python
   EXECUTION_MODE = "demo"
   DRY_RUN = False
   ```

   Keep `DEMO_ONLY = True`. Confirm the startup log says `mode=demo`, and confirm
   the MT5 terminal is logged into the demo account before leaving it running.
5. Stop with `Ctrl+C`. If anything looks wrong, create
   `exness_bot\STOP_TRADING` and then stop the process.

The bot will automatically manage demo positions using broker-side SL/TP and its
trailing logic. Review `exness_bot\logs\bot.log` and `trades.csv` daily.

### 4. Live preparation (disabled)

For the complete beginner-level Exness/MT5 procedure, see [LIVE_TRADING.md](docs/LIVE_TRADING.md).

Live automatic trading is not enabled by this project setup. Do not change
`LIVE_TRADING_ENABLED`, `DEMO_ONLY`, or the live confirmation gate as part of
normal use. A future live release would require a separate review, fresh tests,
and explicit authorization.

The future LIVE path is implemented but disabled by default. It requires explicit live mode, DRY_RUN disabled, DEMO_ONLY disabled, the live gate enabled, the confirmation string, and verified real-account MT5 connection. This project has not performed real-money execution testing.

## Run it in VS Code

1. Install **VS Code** and its **Python extension** (Microsoft).
2. **File → Open Folder…** → pick the extracted `exness-bot` folder.
3. Open a terminal in VS Code: **Terminal → New Terminal**.
4. (Recommended) make a virtual environment so packages stay local to the project:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # macOS / Linux (backtest only)
   ```
   Bottom-right of VS Code, click the Python version and pick the `.venv` one.
5. Install packages:
   ```
   pip install -r requirements.txt      # trading  (Windows)
   pip install pandas                   # backtest only (any OS)
   ```
6. Create your settings file once:
   ```
   copy exness_bot\settings.example.py exness_bot\settings.py    # Windows
   ```
   Open `exness_bot/settings.py` in VS Code and fill in your demo login /
   password / server.
7. Run:
   - **Backtest:** `python -m exness_bot.backtest --csv data/EURUSD_M15.csv`
   - **Bot (DRY-RUN):** `python -m exness_bot.runner`
   - Or press **F5** with `exness_bot/runner.py` open to run it under the debugger.
8. Stop the bot with **Ctrl+C** in the terminal.

Everything it does is written to `exness_bot/logs/bot.log` and
`exness_bot/logs/trades.csv`.

## Deploy (keep it running 24/5)

The bot must stay running while the market is open, so it needs a machine that is
always on with the **Exness MT5 terminal open and logged in**.

**Option A — your own PC (simplest).** Leave the PC on, MT5 running, and
`run.bat` (or `python -m exness_bot.runner`) going in a window. Disable sleep:
*Settings → Power & sleep → Sleep = Never*.

**Option B — a Windows VPS (recommended for real use).**
1. Rent a small **Windows Server VPS** (any provider; ~2 vCPU / 4 GB RAM is
   plenty). Many brokers and hosts offer "Forex VPS" plans.
2. Connect with **Remote Desktop** (`mstsc` on Windows).
3. On the VPS: install Python (same version rule as above), install the **Exness
   MT5** terminal, log into your account, tick *Allow algorithmic trading*.
4. Copy the `exness-bot` folder over, run `install.bat`, fill in `settings.py`.
5. Start it with `run.bat`. It keeps running after you disconnect RDP (don't log
   out — just close the RDP window).
6. To auto-start after a reboot: put a shortcut to `run.bat` in
   `shell:startup`, and set the MT5 terminal to start with Windows.

**Keeping it alive.** For unattended use, run the bot with a supervisor that
restarts it if it exits — e.g. **NSSM** (`nssm install exness-bot`) to register
`python -m exness_bot.runner` as a Windows service, or Task Scheduler with
*Restart on failure*. Watch `logs/bot.log` for the first few days.

> There is **no cloud/Docker deploy** — `MetaTrader5` needs a real Windows
> session with the terminal running, so a Linux container will not work for
> trading. (A Linux box is fine for backtesting only.)

## How good is it for Exness, really?

- **Will it run correctly on Exness?** After a day or two of demo debugging
  (server name, symbol suffix, terminal path): likely yes.
- **Will the built-in strategy make real money?** Unlikely as-is. A basic SMA
  crossover has no proven edge, and spread + swap +
  commission make the expected value negative. The value here is the
  **framework**: safe execution, risk control, and a backtester to find and
  verify an edge you bring yourself.

## Licence

MIT — see `LICENSE`.
