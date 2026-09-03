"""exness_bot — an LLM + rule-based auto-trading bot for Exness (MetaTrader 5).

On each closed candle it builds a market snapshot, gets a buy/sell/close/hold
decision (LLM or a built-in rule set), sizes the trade by risk, attaches an
ATR stop/target, and manages the position with a break-even + ATR trailing stop.

Safe by default: config.DRY_RUN = True and config.DEMO_ONLY = True.
"""
