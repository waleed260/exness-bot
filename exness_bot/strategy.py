"""Decide what to do on a closed candle.

Two engines:
  * rule-based  -- SMA(fast/slow) crossover filtered by RSI + trend. Always available, free.
  * llm         -- asks an OpenAI model for a JSON decision, but only when the
                   cost guardrails in exness_bot/llm_guard.py allow it. Falls back
                   to the rule-based result whenever the call is skipped or fails.

The public entry point is `decide(snapshot, position_side)` which returns:
    {"action": "buy"|"sell"|"close"|"hold", "confidence": float, "reason": str}
`position_side` is "buy", "sell" or None (no open position for the symbol).
"""

import json

from exness_bot.logger import log
from exness_bot import config
from exness_bot import prompts
from exness_bot import llm_guard

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
def _api_key():
    return getattr(settings, "OPENAI_API_KEY", "") if settings else ""


def _compact_snap(snap):
    """Small one-line JSON of just the fields the decision needs -> fewer input tokens."""
    keep = ("time", "close", "sma_fast", "sma_slow", "sma_fast_prev",
            "sma_slow_prev", "rsi", "atr", "trend_up", "trend_down")
    d = {k: snap[k] for k in keep if k in snap}
    for k in ("close", "sma_fast", "sma_slow", "sma_fast_prev", "sma_slow_prev", "atr"):
        if k in d:
            d[k] = round(float(d[k]), 5)
    if config.LLM_SEND_PRICE_HISTORY and "last_10_closes" in snap:
        d["last_10_closes"] = [round(float(c), 5) for c in snap["last_10_closes"]]
    return json.dumps(d, separators=(",", ":"))


def _build_prompt(snap, position_side):
    template = prompts.get(config.LLM_PROMPT_NAME)
    return template.format(
        symbol=config.SYMBOL,
        tf=str(config.TIMEFRAME),
        snap=_compact_snap(snap),
        pos=position_side or "none",
    )


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


def _call_openai(prompt):
    """Return the raw reply text, or None on any error."""
    import openai
    client = openai.OpenAI(api_key=_api_key())
    model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=config.LLM_MAX_OUTPUT_TOKENS,
    )
    try:
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except TypeError:
        # very old openai package without response_format
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def _llm(snap, position_side):
    """Return (decision, prompt_text, reply_text) or None to fall back to rules."""
    prompt = _build_prompt(snap, position_side)
    try:
        text = _call_openai(prompt)
    except Exception as e:  # network / auth / rate limit / bad request
        log.logger.warning(f"LLM call failed, using rule-based: {e}")
        return None

    decision = _validate(_extract_json(text), position_side)
    if decision is None:
        log.logger.warning(f"LLM returned unusable output, using rule-based: {text!r}")
        return None
    return decision, prompt, text


# --------------------------------------------------------------------------- #
def decide(snap, position_side):
    rule_decision = rule_based(snap, position_side)

    if not (config.USE_LLM and _api_key()):
        log.logger.info(f"Rule-based decision: {rule_decision}")
        return rule_decision

    cached = llm_guard.cached_for(snap, position_side)
    if cached is not None:
        log.logger.info(f"LLM decision (cached, no call): {cached}")
        return cached

    ok, why = llm_guard.should_call_llm(snap, position_side, rule_decision)
    if not ok:
        log.logger.info(f"Skipping LLM ({why}); using rule-based: {rule_decision}")
        return rule_decision

    result = _llm(snap, position_side)
    if result is None:
        return rule_decision
    decision, prompt_text, reply_text = result
    llm_guard.note_result(snap, position_side, decision, prompt_text, reply_text)
    log.logger.info(f"LLM decision: {decision}")
    return decision
