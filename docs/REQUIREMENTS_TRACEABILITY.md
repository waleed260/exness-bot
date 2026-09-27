# Requirements Traceability and Current Status

This matrix reconciles the supplied final specification with the current repository. `Implemented` means verified in the current code; `Documented` means the required behavior is specified but not yet implemented; `Not yet evidenced` means the code or data needed to prove it is absent.

| Area | Current status | Evidence / next proof |
|---|---|---|
| Safe defaults and emergency stop | Implemented | `exness_bot/config.py`, `safety.py`, existing tests |
| Legacy deterministic strategy | Implemented | `strategy.py`, `tests/test_strategy_backtest.py` |
| Simulation, persistence, and recovery | Implemented for legacy simulator | `simulator.py`, `recovery.py`, simulator tests |
| XAUUSD M5 profile engine | Documented | Implement `volume_profile.py` and profile tests |
| Closed breakout + next-candle intrabar trigger | Documented | Implement state machine and trigger tests |
| Exact fixed 30-pip SL / 40-pip TP | Documented | Add explicit pip config, geometry tests, and fill-price tests |
| 0.5% MT5 account-aware sizing | Documented | Add `order_calc_profit` sizing and minimum-lot rejection tests |
| Broker constraints and order checks | Partially implemented | Extend current executor with full runtime symbol/freeze/filling validation |
| Ambiguous-order reconciliation | Partially implemented | Add broker-history query tests and no-blind-resend integration test |
| Durable SQLite lifecycle state | Not yet evidenced | Replace/augment JSON state with transactional schema and migration test |
| Realistic profile/backtest costs | Not yet evidenced | Build shared-core M1/tick backtester and cost ledger |
| OOS, walk-forward, Monte Carlo, controls | Not yet evidenced | Produce reproducible reports with frozen data ranges |
| DEMO telemetry | Not yet evidenced | Run a documented Exness demo campaign |
| LIVE_SHADOW and G0–G6 gates | Documented | Implement mode and attach release evidence |
| V2 H1 trend filter | Implemented as pure candidate module | Integrate into shared XAUUSD signal engine and run V1a OOS |
| V2 ATR volatility filter | Implemented as pure candidate module | Run V1b OOS and stability analysis |
| V2 breakout-strength filter | Implemented as pure candidate module | Run V1c OOS and record rejected setups |
| V2 ATR-trailing exit | Implemented as pure candidate module | Run V1d/V2_TRAIL OOS and drawdown comparison |
| V2 ablation matrix | Documented and unit-tested | Execute V1a–V1d independently before selecting V2 |

The repository should not call the XAUUSD candidate “implemented” or “profitable” until the missing evidence exists. The current honest release state is **HOLD — documentation complete, production strategy implementation and empirical validation pending**.
