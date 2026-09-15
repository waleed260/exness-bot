# Exness Bot: Beginner LIVE Trading Procedure

> LIVE trading is disabled by default. This guide explains the controlled procedure for a future authorized deployment. It does not enable live trading, and this project has not placed real-money orders.

## 1. Understand the risk

LIVE mode can send orders through MetaTrader 5 to a real Exness account. Losses can happen because of market movement, spread, slippage, gaps, rejected orders, disconnections, incorrect settings, or strategy errors. Never use money you cannot afford to lose.

## 2. Complete DEMO validation first

Before considering LIVE:

- Run the backtest on representative historical data.
- Run simulation mode and inspect decisions and rejected trades.
- Run automatic DEMO mode for several weeks.
- Review logs/trades.csv, bot.log, drawdown, spread, slippage, errors, and skipped-trade reasons.
- Confirm risk limits, stop-loss, take-profit, position sizing, and emergency-stop behavior.
- Do not treat passing software tests or a short profitable period as proof of future profitability.

## 3. Prepare the real Exness account

1. Confirm that the account is the intended professional/real account.
2. Record the exact MT5 login number, server name, symbol name, contract size, minimum lot, lot step, leverage, and trading permissions.
3. Install the supported 64-bit MT5 terminal on a reliable Windows computer or VPS.
4. Keep the real and demo terminals/accounts clearly separate.
5. Log into the real account manually and verify the balance, equity, free margin, symbol visibility, and live price feed.

## 4. Keep credentials private

Copy exness_bot/settings.example.py to exness_bot/settings.py. Put the real MT5 path, login, password, and server only in the private settings.py file. Never commit settings.py, passwords, tokens, or other secrets to GitHub. This bot does not require an LLM or AI API key.

## 5. LIVE configuration gates

The committed project keeps these safe defaults:

    EXECUTION_MODE = "simulation"
    DRY_RUN = True
    DEMO_ONLY = True
    LIVE_TRADING_ENABLED = False

Only an authorized operator, after DEMO validation and a separate review, may set all five LIVE requirements together in the private local config.py:

    EXECUTION_MODE = "live"
    DRY_RUN = False
    DEMO_ONLY = False
    LIVE_TRADING_ENABLED = True
    CONFIRM_LIVE_STRING = "I ACCEPT THE RISK"

Do not change only one setting. The runner fails closed when the account is a demo account, the selected mode is wrong, DEMO_ONLY is enabled, the live gate is disabled, or the confirmation string is missing.

## 6. First LIVE startup

1. Stop every other bot or worker that could trade the same account or symbol.
2. Confirm MT5 is connected to the real Exness account, algorithmic trading is enabled, and the correct symbol is selected.
3. Start from the project root with: python -m exness_bot.runner
4. Read the startup log before waiting for a signal. Verify mode=live, DRY_RUN=False, LIVE_TRADING_ENABLED=True, the expected symbol/timeframe, and the correct launch equity.
5. If the account, mode, symbol, price feed, permissions, or risk settings are wrong, press Ctrl+C immediately.
6. Begin with conservative risk and monitor the first decisions and orders continuously.

## 7. What the bot does automatically

The bot reads closed-candle market data, calculates the existing SMA/RSI/trend indicators, generates BUY/SELL/NO-TRADE decisions, checks signal and risk rules, sizes approved positions, sends permitted MT5 orders, applies SL/TP, manages trailing or break-even logic, closes positions, reconciles state, and records events.

Automatic operation does not mean guaranteed protection. Check the actual MT5 position and order state, not only the bot log.

## 8. Continuous monitoring

Monitor MT5 and these files together:

- exness_bot/logs/bot.log: decisions, validations, errors, connections, and safety events.
- exness_bot/logs/trades.csv: accepted/closed trade records.
- exness_bot/logs/safety_state.json: persisted risk state.
- exness_bot/logs/signal_ledger.json: duplicate-signal protection state.

Check direction, volume, entry, SL, TP, spread, slippage, balance, equity, drawdown, and reason for every trade. Investigate every rejection or connection warning.

## 9. Emergency stop and rollback

- Press Ctrl+C to stop the process.
- Create exness_bot/STOP_TRADING to block new entries. Existing positions may remain open; inspect and manage them in MT5.
- If behavior is unexpected, disconnect the bot and follow your manual emergency plan.
- To return to DEMO, set EXECUTION_MODE="demo", DRY_RUN=False, DEMO_ONLY=True, and verify MT5 is logged into a demo account.
- To return to safe simulation, set EXECUTION_MODE="simulation" and DRY_RUN=True.

## 10. What has not been verified

The project tests use mocks and simulation. They do not prove real broker execution, profitability, a particular win rate, or safe behavior under every market and network condition. Real-money execution must be considered unverified until it has been independently reviewed and carefully monitored under the operator's own controls.
