"""Decide what to do on a closed candle.

Two engines:
  * rule-based  -- SMA(fast/slow) crossover filtered by RSI. Always available.
  * llm         -- asks an OpenAI model for a JSON decision, falls back to the
                   rule-based result if the API call or the JSON check fails.

The public entry point is `decide(snapshot, position_side)` which returns:
    {"action": "buy"|"sell"|"close"|"hold", "confidence": float, "reason": str}
`position_side` is "buy", "sell" or None (no open position for the symbol).
"""

import json

from exness_bot.logger import log
from exness_bot import config

try:
    import settings
except Exception:  # pragma: no cover
    settings = None

VALID_ACTIONS = {"buy", "sell", "close", "hold"}


# --------------------------------------------------------------------------- #
# rule-based
# --------------------------------------------------------------------------- #
def rule_based(snap, position_side):
    crossed_up = (
        snap["sma_fast_prev"] <= snap["sma_slow_prev"]
        and snap["sma_fast"] > snap["sma_slow"]
    )
    crossed_down = (
        snap["sma_fast_prev"] >= snap["sma_slow_prev"]
        and snap["sma_fast"] < snap["sma_slow"]
    )
    rsi = snap["rsi"]

    if position_side == "buy" and crossed_down:
        return {"action": "close", "confidence": 0.7, "reason": "fast SMA crossed below slow SMA"}
    if position_side == "sell" and crossed_up:
        return {"action": "close", "confidence": 0.7, "reason": "fast SMA crossed above slow SMA"}

    trend_ok_long = (not config.USE_TREND_FILTER) or snap.get("trend_up")
    trend_ok_short = (not config.USE_TREND_FILTER) or snap.get("trend_down")

    if position_side is None:
        if crossed_up and rsi < 70 and trend_ok_long:
            return {"action": "buy", "confidence": 0.62, "reason": "bullish SMA crossover with trend, RSI ok"}
        if crossed_down and rsi > 30 and trend_ok_short:
            return {"action": "sell", "confidence": 0.62, "reason": "bearish SMA crossover with trend, RSI ok"}

    return {"action": "hold", "confidence": 0.5, "reason": "no aligned crossover"}


# --------------------------------------------------------------------------- #
# llm
# --------------------------------------------------------------------------- #
_PROMPT = """You are a disciplined intraday FX trader for {symbol} on the {tf} timeframe.
Only trade with a clear edge; when unsure, hold.

Market snapshot (latest CLOSED candle; trend_up/trend_down come from a 200-SMA slope):
{snap}

Current open position for {symbol}: {pos}

Reply with ONE json object and nothing else:
{{"action": "buy" | "sell" | "close" | "hold", "confidence": 0.0-1.0, "reason": "<=15 words"}}
Rules:
- "close" only makes sense if there is an open position.
- Do not propose "buy" if already long or "sell" if already short; use "hold".
- confidence is your probability the action is correct.
"""


def _extract_json(text):
    if not isinstance(text, str) or text.count("{") == 0 or text.count("}") == 0:
        return None
    frag = text[text.index("{"): text.rindex("}") + 1]
    try:
        return json.loads(frag)
    except json.JSONDecodeError:
        return None


def _validate(obj, position_side):
    if not isinstance(obj, dict):
        return None
    action = str(obj.get("action", "")).lower().strip()
    if action not in VALID_ACTIONS:
        return None
    try:
        conf = float(obj.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    conf = min(max(conf, 0.0), 1.0)
    reason = str(obj.get("reason", ""))[:200]

    if action == "close" and position_side is None:
        action = "hold"
    if action == "buy" and position_side == "buy":
        action = "hold"
    if action == "sell" and position_side == "sell":
        action = "hold"
    return {"action": action, "confidence": conf, "reason": reason}


def _llm(snap, position_side):
    api_key = getattr(settings, "OPENAI_API_KEY", "") if settings else ""
    if not api_key:
        return None
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        prompt = _PROMPT.format(
            symbol=config.SYMBOL,
            tf=str(config.TIMEFRAME),
            snap=json.dumps(snap, indent=2),
            pos=position_side or "none",
        )
        resp = client.chat.completions.create(
            model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = resp.choices[0].message.content
    except Exception as e:  # network / auth / rate limit
        log.logger.warning(f"LLM call failed, using rule-based: {e}")
        return None

    decision = _validate(_extract_json(text), position_side)
    if decision is None:
        log.logger.warning(f"LLM returned unusable output, using rule-based: {text!r}")
    return decision


# --------------------------------------------------------------------------- #
def decide(snap, position_side):
    use_llm = config.USE_LLM and settings and getattr(settings, "OPENAI_API_KEY", "")
    if use_llm:
        decision = _llm(snap, position_side)
        if decision is not None:
            log.logger.info(f"LLM decision: {decision}")
            return decision
    decision = rule_based(snap, position_side)
    log.logger.info(f"Rule-based decision: {decision}")
    return decision
