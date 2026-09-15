# Automated Trading System Implementation Plan

## Objective

Prepare the Exness bot for reliable automated operation in simulation and demo
environments while keeping real-money automatic trading disabled. The existing
SMA/RSI/trend strategy remains the source of trade signals; this work improves
validation, risk controls, execution safety, state handling, testing, and
documentation around it.

## Non-negotiable safety rules

- `DRY_RUN` remains enabled by default.
- Simulation is the default execution mode for local development.
- Live mode is rejected unless it is explicitly enabled in code and configuration;
  this task will not enable it.
- No live credentials, API keys, or account access are required for tests.
- Unsafe, stale, invalid, duplicate, or emergency-stopped trades become
  `NO-TRADE` and are logged with a reason.

## Existing architecture understood

`runner.py` polls MT5, `data.py` builds closed-candle data, `indicators.py`
calculates SMA/RSI/ATR/trend values, `strategy.py` produces buy/sell/close/hold,
`risk.py` sizes trades and manages stops, `executor.py` sends MT5 requests, and
`backtest.py` evaluates the rule strategy on historical candles. The LLM is an
optional signal reviewer guarded by `llm_guard.py`.

## Implementation phases

### Phase 1 — Safety and configuration

- Add explicit `simulation`, `demo`, and `live` execution modes.
- Keep simulation and dry-run as defaults.
- Add a global emergency-stop mechanism.
- Add configurable trade-count, consecutive-loss, margin, exposure, slippage,
  signal-age, and data-quality protections.
- Ensure live execution is hard-disabled by default and clearly reported at startup.

### Phase 2 — Validation and execution

- Add reusable order validation and duplicate-signal protection.
- Add a deterministic simulator for opening, monitoring, SL/TP, strategy exits,
  and restart/reconciliation tests.
- Keep the existing MT5 executor behind the same safety boundary.
- Make rejected orders and retries distinguishable from successful fills.

### Phase 3 — Recovery and observability

- Persist simulation state safely and reconcile it on restart.
- Log structured decision, validation, risk, execution, position, recovery, and
  safety events without secrets.
- Make critical failures fail closed: no new trades until recovery succeeds.

### Phase 4 — Tests and validation

- Add dependency-light unit tests for strategy contracts, safety, sizing,
  execution, simulator behavior, duplicate protection, and recovery.
- Run syntax checks and the complete test suite in this repository.
- Fix failures before documenting results.

### Phase 5 — Documentation and handoff

- Update the README and add focused setup, architecture, strategy, risk,
  testing, troubleshooting, and future-live-readiness documentation.
- Record actual test results and known limitations; never invent performance data.
- Review the final diff for secrets and generated artifacts before any commit or push.

## Acceptance criteria

- The project can make existing-strategy decisions and safely reject poor or
  unsafe trades.
- Local simulation can open, monitor, modify, and close positions automatically.
- A restart can recover and reconcile simulated state without duplicate entries.
- Critical risk limits and emergency stop block new trades.
- Tests are run by the implementer and their result is reported honestly.
- Live auto-trading remains disabled throughout this task.

## Current implementation status

- [x] Repository and existing architecture reviewed.
- [x] Safety/configuration layer implemented.
- [x] Simulator and reconciliation implemented.
- [x] Automated tests added and executed.
- [x] Documentation updated from verified behavior.
- [x] Final diff and secret review completed.
- [x] GitHub push performed only after explicit repository/remote verification.
