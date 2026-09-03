"""Exness (MT5) auto-trading adaptation of the StockAgent decision idea.

The simulated market from the research project is replaced with a live Exness
MetaTrader 5 connection. The only carried-over idea is "ask an LLM for a JSON
trade decision"; matching, pricing and settlement are done by the broker.

Safe by default: config.DRY_RUN = True and config.DEMO_ONLY = True.
"""
