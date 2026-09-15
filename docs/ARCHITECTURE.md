# Automated System Architecture

The project is split into a live-data path and a broker-independent validation/testing path. Live automatic trading is disabled by default.

```text
MT5 closed candles
        |
        v
 data.py -> indicators.py -> strategy.py
        |                         |
        |                   BUY / SELL / HOLD / CLOSE
        v                         v
   session/spread          safety.py validation
                                  |
                       reject -> log NO-TRADE
                                  |
                         risk.py sizing + SL/TP
                                  |
                 simulation / DRY_RUN / demo executor
                                  |
                 position monitoring + trailing stop
                                  |
                    closure + trade log + recovery
```

## Components

- `data.py`: fetches rates and removes the forming candle before analysis.
- `indicators.py`: calculates SMA, RSI, ATR, trend direction, session checks, and trailing-stop math.
- `strategy.py`: preserves the existing SMA crossover + RSI + 200-SMA trend strategy and returns a validated action contract. Invalid indicator data becomes `hold`.
- `safety.py`: performs fail-closed order validation, emergency-stop checks, stale-signal checks, margin/spread checks, and process-level trade/loss limits.
- `risk.py`: calculates risk-based lot size, broker minimum stop distances, daily equity guard, and trailing stops.
- `executor.py`: isolates MT5 order requests and retries. It refuses live mode unless the explicit live gate is enabled; simulation and dry-run never call `order_send`.
- `simulator.py`: deterministic local broker substitute. It supports open, stop/target monitoring, monotonic stop changes, manual close, persistence, and restart reconciliation.
- `runner.py`: orchestrates startup, live data polling, position management, signal handling, validation, execution, and shutdown.
- `backtest.py`: evaluates the rule strategy on historical candles with spread and commission assumptions.

## State and recovery

The local simulator stores state through an atomic temporary-file replacement. A new simulator instance reloads open/closed positions and ticket numbering. `reconcile()` marks a locally open position as externally missing instead of opening a replacement, which is the safe recovery behavior.

The MT5 runner obtains broker positions on each decision and uses the broker as the source of truth. A future demo/live hardening pass should persist safety counters and add an explicit startup reconciliation report before enabling any external execution.

## Execution modes

| Mode | External order submission | Default |
|---|---:|---:|
| `simulation` | No | Yes |
| `demo` | Only if `DRY_RUN=False` and the account is demo | No |
| `live` | Refused while `LIVE_TRADING_ENABLED=False` | No |

`DRY_RUN=True` remains an additional no-order guard in every mode.
