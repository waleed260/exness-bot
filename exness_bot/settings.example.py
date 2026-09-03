"""Copy this file to settings.py and fill in your Exness MT5 credentials.

settings.py is git-ignored. NEVER commit real credentials or API keys.
"""

# ---- Exness MT5 terminal / account ----
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"  # path to terminal64.exe
MT5_LOGIN = 12345678          # your MT5 account number (int)
MT5_PASSWORD = "your-password"
MT5_SERVER = "Exness-MT5Trial"  # e.g. Exness-MT5Trial for demo, Exness-MT5Real for live

# ---- LLM (optional) ----
# Leave OPENAI_API_KEY empty to run with the built-in rule-based strategy only.
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4o-mini"
