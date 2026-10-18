# System Architecture

## SMC Strategy Data Flow (primary)

```text
MT5 closed M5 candle detected
            |
            v
   data.load_multi_frame()
   ├── M5  (500 bars)  ── primary entries
   ├── M15 (200 bars)  ── structure bias
   ├── H1  (300 bars)  ── EMA trend
   └── VP snapshot     ── VAH/VAL/POC confluence
            |
            v
   strategy_dispatch.decide() -> smc_strategy.decide()
   ├── Gate: Regime filter (ADX < 20 = ranging → hold)
   ├── Gate: News filter (ATR spike > 2.5x avg → hold)
   ├── M15 bias (HH/HL or LH/LL)
   ├── Liquidity sweep + BOS + Order Block + FVG
   ├── Displacement + Price Action + Premium/Discount
   ├── VP Confluence (near VAL/POC or VAH/POC)
   ├── H1 EMA Trend (EMA50 vs EMA200)
   ├── Volume confirmation (tick_volume > 1.2x avg)
   └── Score >= 9/15 + 4 mandatory conditions
            |
            v
   {action, entry, sl, tp1, tp2, confidence}
            |
            v
   safety.validate_order() -> risk.smc_sl_tp() -> risk.position_size()
            |
            v
   executor.open_position() -> MT5
            |
            v
   _manage_open() every poll:
   ├── Price hits TP1 -> executor.partial_close(50%) + modify_sl(breakeven)
   └── After TP1 -> v2_candidate.trailing_stop() on remaining 50%
```

## Legacy SMA Data Flow

```text
MT5 closed M15 candle -> data.load_frame() -> indicators -> strategy.decide()
   -> safety.validate_order() -> risk.sl_tp() -> executor.open_position()
   -> trailing_sl() every poll
```

## VP Breakout Flow

```text
M5 candles -> volume_profile (03:00 UTC sessions) -> VAH=GREEN, VAL=RED
   -> close > GREEN = BUY setup / close < RED = SELL setup
   -> next-candle trigger -> fixed 30-pip SL, 40-pip TP
```

## Components

| Module | Purpose |
|---|---|
| `smc_strategy.py` | SMC engine: swings, BOS, OB, FVG, VP, H1 trend, ADX regime, news filter, volume, scoring |
| `strategy_dispatch.py` | Routes to active strategy via `config.ACTIVE_STRATEGY` |
| `data.py` | Single-frame and multi-frame (M5+M15+H1+VP) data loading |
| `runner.py` | Main loop: candle detection, strategy dispatch, partial close/BE/trail |
| `executor.py` | MT5 orders: open, close, partial_close, modify_sl with retry |
| `safety.py` | Fail-closed validation, emergency stop, signal deduplication |
| `risk.py` | Position sizing, SL/TP (ATR-based and SMC passthrough), daily guard |
| `indicators.py` | SMA, RSI, ATR, H1 EMA trend, trailing SL, session filter |
| `volume_profile.py` | Session profile: VAH, VAL, POC from volume bins |
| `simulator.py` | Local broker sim with partial close and BE support |
| `recovery.py` | Bounded exponential reconnect backoff |

## Execution Modes

| Mode | Orders sent | Default |
|---|---|---|
| `simulation` | No (logged only) | Yes |
| `demo` | Demo account only (if `DRY_RUN=False`) | No |
| `live` | Requires 5 explicit gates | No |

## State and Recovery

The runner uses the broker as source of truth. Disappeared positions are reconciled with conservative loss assumption. The simulator persists state atomically via temp-file replacement. SMC position metadata (`_smc_meta`) tracks TP1/TP2/BE state per ticket and cleans up when positions close.
