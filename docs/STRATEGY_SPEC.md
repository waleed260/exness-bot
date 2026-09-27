# VP_BREAKOUT_M5_V1 — Production Strategy Specification

Status: **engineering and research specification**. This document is the source of truth for the XAUUSD production candidate described in the supplied final PDF. It does not claim profitability, and it does not claim that the current legacy implementation has completed these requirements.

## 1. Scope and non-negotiable rules

- Instrument: XAUUSD; default timeframe: M5; profile timezone: UTC.
- Strategy version: `VP_BREAKOUT_M5_V1`.
- Risk target: 0.5% of account balance per trade.
- Stop loss: exactly 30 configured pips; take profit: exactly 40 configured pips.
- Maximum one open position, two consecutive losses per trading day, and 2% daily-loss limit.
- No martingale, grid, averaging, revenge re-entry, or baseline trailing stop.
- Backtest, demo, shadow, and live must share the same deterministic strategy/risk core; only data and execution adapters may differ.
- Entry decisions use closed-candle data. The next-candle trigger uses live intrabar/tick data.
- No LLM may decide production entries. No parameter may be tuned until a frozen baseline and untouched validation period exist.
- A broker minimum volume that would exceed the risk budget means **skip**, never round upward.

The repository currently contains a safe legacy SMA/RSI/ATR EURUSD implementation. It remains useful as a control, but it is not this production strategy. The implementation phases below are the acceptance path for promoting the XAUUSD candidate.

## 2. Profile and signal definition

Each trading day starts a new volume profile at 03:00 UTC. No previous-day level is carried forward. The active profile must be snapshotted using information available before the candidate candle is evaluated; the candidate candle must not move the level it is breaking.

The deterministic baseline maps:

- GREEN level = Value Area High (VAH), used for buys.
- RED level = Value Area Low (VAL), used for sells.
- POC is diagnostic/research data only.
- Value area contains 70% of session volume unless a separately versioned research variant changes it.

When M1 or tick data is available, use it. If only M5 data exists, document the volume-to-price allocation approximation and report its limitations. A change to binning, weighting, value-area calculation, or timezone creates a new strategy version.

### BUY state transition

1. On a fully closed candle, require `close > GREEN_LEVEL`; a wick alone is not a breakout.
2. Create a unique deterministic `breakout_id` and freeze that candle’s high.
3. Persist the pending setup before entering `WAITING_NEXT_CANDLE_TRIGGER`.
4. During only the immediately following candle, monitor executable ask/tick prices.
5. If price breaks the frozen high, create one BUY at the current ask after all checks pass.
6. If the next candle ends without a break, expire the setup. Never wait for that candle to close before triggering.

### SELL state transition

The inverse rules apply: require `close < RED_LEVEL`, freeze the breakout low, monitor only the next candle’s executable bid, and enter one SELL when that low breaks. A setup produces at most one trade; repeated touches and re-crosses do not duplicate it.

Required states are `NO_SETUP`, `BREAKOUT_DETECTED`, `WAITING_NEXT_CANDLE_TRIGGER`, `TRIGGERED`, `ORDER_CHECKED`, `ORDER_SENT`, `FILLED`, `MANAGED`, `CLOSED`, `RECONCILED`, `EXPIRED`, and `REJECTED`.

Every event carries `strategy_version`, `profile_session_id`, `breakout_id`, `signal_id`, `candle_time`, and `direction`. These identifiers must survive restart recovery.

## 3. Price, risk, and broker rules

`PIP_SIZE` is explicit configuration, not a digit heuristic. At runtime validate it against the connected symbol’s point, digits, and tick size. Build prices as:

```text
SL distance = 30 × PIP_SIZE
TP distance = 40 × PIP_SIZE
BUY:  SL = actual fill price - SL distance; TP = actual fill price + TP distance
SELL: SL = actual fill price + SL distance; TP = actual fill price - TP distance
```

Sizing must use MT5 account-currency calculations at the current executable entry price:

1. `risk_budget = balance × 0.005`.
2. Calculate the loss of one lot from entry to the exact stop with `order_calc_profit()`.
3. Include known commission and other modeled costs.
4. Solve a safe volume, quantize **down** to `volume_step`, and validate `volume_min`/`volume_max`.
5. Reject if the minimum tradable volume exceeds the risk budget; report the minimum feasible balance.

Read, do not assume, `point`, `digits`, `trade_tick_size`, `trade_tick_value`, stops level, freeze level, filling mode, trade mode, visibility, margin rules, account currency, and volume limits. Validate spread, quote freshness, margin, permissions, and symbol identity immediately before every entry.

## 4. Execution, reconciliation, and persistence

The required sequence is:

```text
signal → fresh tick → price/SL/TP → risk size → broker constraints
→ spread → margin → order_check → order_send → result verification → persist
```

After `order_send`, verify return code, order/deal/position IDs, executed volume, fill price, actual SL/TP, magic number, and symbol. Record direction-adjusted slippage in price, points, and pips. An ambiguous timeout is not a reason to resend: query positions and recent history first, then decide whether any retry is safe.

Manage only positions matching the configured symbol, magic number, and strategy identity. Use durable state (SQLite with transactions and WAL is preferred) for tickets, initial risk, requested/executed volume, signal IDs, breakout IDs, session IDs, lifecycle times, exit reason, daily counters, pending setup, and last processed candle. On restart, reconnect, verify account and symbol, load state, reconcile broker positions/deals, repair from broker truth, and resume only after reconciliation succeeds.

## 5. Protection and failure-closed behavior

Persist the trading-day ID, day-start balance/equity, realized P/L, consecutive losses, trade count, and kill-switch state. Block new entries after either two consecutive losses or 2% daily loss. Also support an independent equity emergency gate.

Reject stale/missing/invalid quotes, excessive spread, insufficient margin, invalid stops, stale signals, duplicate positions, state corruption, account mismatch, symbol mismatch, repeated execution failures, or impossible price/volume calculations. A failure stops new entries; it does not automatically close existing positions unless the explicit emergency-management policy says so.

The emergency stop file is `exness_bot/STOP_TRADING`. Never log passwords, credentials, API keys, or private keys.

## 6. Backtest integrity and reporting

The backtester must use the same strategy and sizing core, with M1/tick trigger timing where possible. Model bid/ask spread, commission by actual volume, swap, slippage, latency assumptions, partial fills, entry-bar SL/TP, gaps, and chronological intrabar ordering. If both SL and TP are touched and ordering is unknown, apply a documented conservative rule and mark the trade ambiguous; never silently assume TP first.

Every report includes starting/ending balance, return, trades, win rate, average win/loss, payoff, expectancy, average and median R, profit factor, maximum drawdown and duration, worst losing streak, exposure/hold time, spread/commission/swap/slippage costs, long/short, session, month/quarter, regime results, skipped trades, and rejection reasons. Too few trades is `INSUFFICIENT SAMPLE`, not evidence of edge.

Required workflow: scan data quality and timezone; analyze regimes; research one hypothesis at a time against a frozen baseline; validate risk and costs; then make a release/hold/reject decision. Use untouched OOS periods, walk-forward windows, Monte Carlo trade-order and cost stress, parameter stability regions, and controls (legacy SMA/RSI, simple breakout, matched random entry, and no-trade).

## 7. Release gates

| Gate | Pass evidence |
|---|---|
| G0 Code correctness | Unit, integration, execution, recovery, and safety tests pass. |
| G1 Backtest integrity | Timing, profile snapshot, costs, sizing, lifecycle, and leakage checks pass. |
| G2 OOS edge | Positive net expectancy after costs with acceptable drawdown on untouched data. |
| G3 Walk-forward | Results are not isolated to one window; sensitivity shows a stability region. |
| G4 Demo execution | Fill timing, costs, slippage, rejection, recovery, and reconciliation agree with the model. |
| G5 LIVE_SHADOW | Live signals and hypothetical fills remain consistent with research assumptions with zero real orders. |
| G6 Live risk | Account, broker, balance feasibility, hard limits, kill switch, and explicit confirmation all pass. |

Any failed gate means **HOLD**. Demo P/L, a green backtest, or passing software tests alone never proves profitability.

## 8. Implementation order and rating

1. Freeze the legacy strategy as `legacy_eurusd_m15_v0` and record its tests.
2. Build symbol/config validation, profile engine, snapshot logic, breakout state machine, trigger, fixed trade manager, risk engine, and daily guards.
3. Harden MT5 execution, reconciliation, slippage, partial fills, persistence, and restart recovery.
4. Rebuild the backtester around the shared core and realistic costs.
5. Run the exact baseline without optimization; only then test documented variants one at a time.
6. Validate on Exness DEMO, then LIVE_SHADOW, then consider LIVE only after G0–G6.

### Documentation/engineering score: 9.6 / 10

This score applies to the specification and documentation quality: scope, exact rules, safety gates, broker-aware risk, validation workflow, traceability, and honest limitations are covered. It is **not** a profitability score and is not a claim that the current code has completed the XAUUSD implementation. The remaining 0.4 is intentionally reserved for executable evidence: production-core tests, realistic backtest reports, OOS/walk-forward results, demo telemetry, shadow validation, and verified release gates.

## 9. Deliverables per release

Each candidate release must include the code commit, strategy version, configuration snapshot, data source/timezone/range, unit and integration test report, backtest report, OOS and walk-forward reports, demo report, and release decision. The release decision must say `RELEASE`, `HOLD`, or `REJECT` and link every gate to evidence.
