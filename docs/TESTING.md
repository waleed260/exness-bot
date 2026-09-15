# Testing and Validation

Run the dependency-free and dependency-backed tests with:

```bash
python3 -m unittest discover -s tests -v
# or, after installing dependencies in the project environment:
.venv/bin/python -m unittest discover -s tests -v
```

The test suite currently covers:

- valid and invalid BUY/SELL order geometry;
- emergency-stop and environment-mode rejection;
- spread, slippage, margin, stale-signal, lot-size, stop-distance, trade-count, and consecutive-loss protections;
- simulated BUY take-profit and SELL stop-loss;
- stop-loss tightening without loosening;
- simulator persistence and restart recovery;
- reconciliation of a missing external position;
- persistent risk-state, signal-ledger, and cross-day loss recovery;
- invalid strategy data becoming `hold`;
- malformed, stale, duplicated, and non-monotonic candle rejection;
- BUY, SELL, and strategy-close decisions;
- indicator snapshot construction;
- historical backtest execution.

A successful unit test run is not proof of profitability or broker compatibility. MT5 order submission is intentionally not exercised here. It must be validated only against a disposable demo account after separate operational review, with live mode still disabled.

Historical performance is also not a promise of future performance. Backtests should use multiple instruments, long histories, out-of-sample data, realistic spread/commission/swap assumptions, and walk-forward validation.
