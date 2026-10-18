# Testing and Validation

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Test Suite — 84 tests

### SMC Strategy (`tests/test_smc_strategy.py` — 30 tests)
- Insufficient candles, session filter, cooldown, spread filter
- M15 bullish/bearish bias detection
- Swing detection, ATR computation, FVG edge cases, equilibrium math
- VP confluence, session boundaries (London/NY/Asian)
- Regime filter (ADX-based ranging market detection)
- News/volatility spike filter
- Volume confirmation scoring
- Decision contract: required keys, confidence bounds, SL/TP presence

### SMC Backtester (`tests/test_smc_backtest.py` — 7 tests)
- Run on synthetic data, report schema completeness
- Stop-first conservative exit (buy and sell)
- No exit when price stays in range
- Sample status detection

### VP Breakout (`tests/test_phase_b.py` — 18 tests)
- Volume profile session reset, no previous-day leakage
- Close above/below VAH/VAL triggers, wick-only rejection
- Next-candle confirmation, expiry, duplicate blocking
- Fixed 30/40 pip SL/TP, pip validation, lot sizing, daily/consecutive guards

### VP Backtester (`tests/test_vp_backtest.py` — 5 tests)
- Phase B path and volume sizing, report schema
- Stop-first ambiguity, gap exits, level/confidence tiers

### V2 Candidate Filters (`tests/test_v2_candidate.py` — 7 tests)
- H1 trend with strictly prior candles, neutral/insufficient blocking
- Volatility band, breakout strength, independent toggles
- Trailing stop monotonicity (buy and sell)

### Safety and Execution (`tests/test_safety_simulator.py` — 8 tests, `tests/test_execution_safety.py` — 4 tests)
- Environment guard, order validation, state persistence
- Simulation never calls order_send, live gate blocks, timeout no-retry, requote retry

### Legacy Strategy (`tests/test_strategy_backtest.py` — 5 tests)
- Invalid snapshot, SMA crossover contract, indicator fields, data validation, backtest execution

## Important

Tests verify code correctness, not profitability. Always backtest on real historical data and forward-test on demo before any live consideration.
