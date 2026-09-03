# exness_bot — LLM + rule-based auto-trading bot for Exness (MetaTrader 5)

A small, safe-by-default trading bot for an **Exness MT5** account. On every
closed candle it builds a market snapshot, asks either an LLM or a built-in
rule set for a `buy / sell / close / hold` decision, sizes the trade by risk,
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

## What it does

| Area | Detail |
|------|--------|
| **Entry** | SMA(fast/slow) crossover, filtered by RSI and a 200-SMA trend filter; or an LLM decision (OpenAI) with the rule set as fallback |
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
  settings.example.py  copy to settings.py -> MT5 login + optional OpenAI key
  mt5_client.py        connect / account / positions / rates / symbol resolve
  indicators.py        indicator + trailing-stop + session math (no MT5 import)
  data.py              live rates -> indicator DataFrame
  strategy.py          LLM decision + rule-based fallback
  prompts.py           named LLM prompt presets (conservative, trend_follow, ...)
  llm_guard.py         cost guardrails: only-on-signal, per-day cap, $ limit, caching
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

## LLM mode + keeping the OpenAI bill tiny

The bot works fully **without** OpenAI — the rule engine is the default and costs
**$0**. LLM mode just asks a model to sanity-check each *potential* trade.

### Add your API key (do it in VS Code)

1. Create a key: <https://platform.openai.com/api-keys>
2. **Set a hard spend limit** and turn **auto-recharge OFF**:
   <https://platform.openai.com/settings/organization/limits> (e.g. $5/month).
   This is your real safety net.
3. In VS Code open **`exness_bot/settings.py`** (you made it from
   `settings.example.py`) and paste the key:
   ```python
   OPENAI_API_KEY = "sk-...your key..."
   OPENAI_MODEL   = "gpt-4o-mini"
   ```
   Save. `settings.py` is git-ignored, so the key is never committed.
4. In `exness_bot/config.py` keep `USE_LLM = True`. Done — the guardrails below
   are already on.

### Which model? (`OPENAI_MODEL`)

| Model | When | ~cost / decision |
|---|---|---|
| `gpt-4o-mini` *(default)* | fine for this simple SMA/RSI strategy | ~$0.00006 |
| `gpt-4.1-mini` | a bit sharper, still cheap | ~$0.0002 |
| `gpt-4o` | best judgement on messy / borderline setups | ~$0.001 |
| `gpt-4.1` | strongest reasoning of these | ~$0.002 |

Even `gpt-4o` stays at **cents per month** because the guardrails below keep the
number of calls tiny. `llm_guard.py` auto-uses the right price for the log
estimate.

### The cost guardrails (in `config.py`)

| Setting | Default | What it saves |
|---|---|---|
| `LLM_ONLY_ON_SIGNAL` | `True` | **Biggest saver.** Calls the model *only* when the rule engine already sees a buy/sell/close setup. Quiet candles cost nothing. |
| `LLM_ENTRIES_ONLY` | `True` | Never spends a call on an exit — rules + SL/TP + trailing handle closing. Only entries go to the model. |
| `LLM_MIN_SECONDS_BETWEEN_CALLS` | `300` | Hard floor on call frequency, whatever the timeframe. |
| `LLM_MAX_CALLS_PER_DAY` | `20` | Hard cap per UTC day; after it, rules only. |
| `LLM_DAILY_COST_LIMIT_USD` | `0.15` | Stops calling once the day's *estimated* spend hits this. |
| `LLM_SKIP_OUTSIDE_SESSION` | `True` | No calls outside `SESSION_UTC_HOURS` / `TRADE_DAYS`. |
| `LLM_CACHE_SNAPSHOT` | `True` | Reuses the last decision when the market barely moved — no call. |
| `LLM_SEND_PRICE_HISTORY` | `False` | Keeps the last-10-closes array out of the prompt (fewer input tokens). |
| `LLM_MAX_OUTPUT_TOKENS` | `40` | The reply is a tiny JSON object; capped low. |

Every real call also uses `response_format=json_object` (no wasted retries) and a
compact one-line snapshot. `logs/bot.log` prints a running spend estimate:
`LLM call 3/20 today | ~256 in / 20 out tok | est $0.00005 | est day total $0.0002`.

**Rough cost:** with `gpt-4o-mini`, one decision ≈ **~$0.00006**. Even at the
20-calls/day cap that's **a few cents a month**; with *only-on-signal* +
*entries-only* it is usually a handful of calls a day. The dashboard limit in
step 2 is the ceiling that actually matters.

### Prompt presets (`config.py` → `LLM_PROMPT_NAME`)

`exness_bot/prompts.py` ships five ready-made prompts — set the name in `config.py`:

| Name | Style |
|---|---|
| `conservative` *(default)* | trend-aligned, textbook setups only, holds when unsure |
| `trend_follow` | rides the 200-SMA trend, lets winners run |
| `mean_reversion` | fades RSI extremes back to the slow SMA |
| `breakout` | momentum breakouts with expanding ATR, in trend direction |
| `swing` | rare, high-confluence entries; expects long holds |

Add your own by dropping another template into `PRESETS` in `prompts.py`.

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
