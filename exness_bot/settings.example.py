"""Copy this file to settings.py and fill in your Exness MT5 credentials.

settings.py is git-ignored. NEVER commit real credentials or API keys.
"""

# ---- Exness MT5 terminal / account ----
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"  # path to terminal64.exe
MT5_LOGIN = 12345678          # your MT5 account number (int)
MT5_PASSWORD = "your-password"
MT5_SERVER = "Exness-MT5Trial"  # e.g. Exness-MT5Trial for demo, Exness-MT5Real for live

# ---- LLM (OPTIONAL - it costs money per decision) ----
# Leave OPENAI_API_KEY = "" to run the built-in rule-based strategy only. That
# path is free and never contacts OpenAI.
#
# To enable LLM decisions:
#   1. Create a key:  https://platform.openai.com/api-keys
#   2. Paste it below, keeping the quotes:  OPENAI_API_KEY = "sk-..."
#   3. Set a hard spend cap and turn OFF auto-recharge:
#        https://platform.openai.com/settings/organization/limits
#
# OPENAI_MODEL - pick one:
#   "gpt-4o-mini"  (default) cheapest, fine for this simple strategy   ~$0.00006 / decision
#   "gpt-4.1-mini"           a bit sharper, still cheap                ~$0.0002  / decision
#   "gpt-4o"                 best judgement on messy / borderline setups ~$0.001 / decision
#   "gpt-4.1"                strongest reasoning of these               ~$0.002  / decision
# Even "gpt-4o" stays at cents/month because the guardrails in config.py
# (only-on-signal, entries-only, per-day cap, daily $ limit, caching) keep the
# number of calls tiny. llm_guard auto-uses the right price for the log estimate.
#
# How often the model is called is controlled by the "LLM cost guardrails" block
# in exness_bot/config.py.
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4o-mini"
