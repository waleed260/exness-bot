# VP_BREAKOUT_M5_V2 — Amendment Implementation

This document implements the supplied `2nd exness .pdf` as a separate candidate layer. It does not modify the frozen legacy strategy or claim that V2 has an edge. The production promotion state remains **HOLD** until each ablation survives the V1 OOS, walk-forward, Monte Carlo, demo, and LIVE_SHADOW gates.

## Implemented module

`exness_bot/v2_candidate.py` is pure Python and broker-independent. It contains no MT5 calls and is safe to use from a backtester or adapter. `V2FilterConfig` makes each amendment independently toggleable and keeps the starting parameters explicit:

- H1 trend filter: EMA-50 and EMA-200 on the last fully closed H1 candle strictly before the M5 signal; bullish/bearish agreement is required.
- Volatility filter: current closed-candle ATR(14) must be strictly greater than `0.8 ×` and strictly less than `2.0 ×` the 20-value ATR average.
- Breakout-strength filter: close-to-VAH/VAL distance must be at least `MIN_BREAKOUT_STRENGTH × ATR(14)`, starting at `0.20`.
- ATR-trailing exit: immutable initial risk, breakeven at +1R, then highest/lowest-close trailing at `2.0 × ATR`; stops never move backward.

Blocked setups return auditable reasons: `trend_filter_block`, `volatility_filter_block`, and `weak_breakout_block`. A weak breakout never receives a `BREAKOUT_ID` at the caller boundary.

## Version and ablation matrix

| Version | Change | Candidate implementation |
|---|---|---|
| `VP_BREAKOUT_M5_V1` | Frozen control | Existing V1 specification; unchanged |
| `VP_BREAKOUT_M5_V1a` | H1 trend only | `V2FilterConfig(trend_enabled=True)` |
| `VP_BREAKOUT_M5_V1b` | Volatility only | `V2FilterConfig(volatility_enabled=True)` |
| `VP_BREAKOUT_M5_V1c` | Strength only | `V2FilterConfig(strength_enabled=True)` |
| `VP_BREAKOUT_M5_V1d` / `VP_BREAKOUT_M5_V2_TRAIL` | ATR trail only | `V2FilterConfig(trail_enabled=True)` plus `trailing_stop()` |
| `VP_BREAKOUT_M5_V2` | Only individually passed fixes combined | Must be selected from the experiment registry after OOS evidence |

The module does not silently combine filters or promote a failing variant. The current unit tests prove deterministic math and anti-lookahead behavior only; they are not OOS or profitability evidence.

## Remaining integration work

- Wire the candidate layer into a future shared XAUUSD profile/breakout engine and M1/tick backtester.
- Persist the selected strategy version, filter parameters, rejection reasons, and trailing state in the lifecycle ledger.
- Run the prescribed V1/V1a/V1b/V1c/V1d/V2 ablation matrix on frozen data, then walk-forward across at least two unseen windows.
- Validate demo execution and LIVE_SHADOW before any live consideration.

## Verification

`tests/test_v2_candidate.py` covers strict prior-H1 timestamps, neutral/insufficient trend history, ATR band edges, directional strength, independent toggles, immutable initial risk, breakeven, and monotonic buy/sell stops.
