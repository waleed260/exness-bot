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
| Python packages | `MetaTrader5>=5.0.37`, `pandas>=1.3.5`, `numpy>=1.21`, and `openai>=1.10,<2` if you use LLM mode — all via `pip install -r requirements.txt` |
| Broker terminal | **Exness MetaTrader 5** desktop terminal installed and logged in |
| Exness account | a **demo** account first: login number, password, server (e.g. `Exness-MT5Trial`) |
| Terminal setting | **Tools → Options → Expert Advisors → Allow algorithmic trading** ticked |
| Network | a stable internet connection; the PC/VPS must stay on while the bot runs |
| Disk / RAM | ~1 GB free disk (Python + MT5), 2 GB+ RAM |
| Optional | an **OpenAI API key** — only if `USE_LLM=True` and you want LLM decisions instead of the rule set |

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
  crossover / generic LLM prompt has no proven edge, and spread + swap +
  commission make the expected value negative. The value here is the
  **framework**: safe execution, risk control, and a backtester to find and
  verify an edge you bring yourself.

## Licence

MIT — see `LICENSE`.
