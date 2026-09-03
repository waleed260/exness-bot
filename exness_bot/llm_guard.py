"""Guardrails that keep the OpenAI bill as small as possible.

The single biggest saving is simply *not calling the model*. An LLM asked
"anything to do?" on a quiet candle will almost always say "hold" - the same
answer the free rule engine already gave. So this module blocks the call when:

  * we are outside the configured trading session      (LLM_SKIP_OUTSIDE_SESSION)
  * the rule engine sees no setup at all               (LLM_ONLY_ON_SIGNAL)
  * the market snapshot has not moved since last call  (LLM_CACHE_SNAPSHOT)
  * we called too recently                             (LLM_MIN_SECONDS_BETWEEN_CALLS)
  * we already used the day's call budget              (LLM_MAX_CALLS_PER_DAY)
  * the day's estimated spend hit the ceiling          (LLM_DAILY_COST_LIMIT_USD)

It also keeps a running dollar estimate and logs it, so the cost is visible in
``logs/bot.log`` without opening the OpenAI dashboard.

One process, one symbol, one loop -> module-level state is fine.
"""

import datetime
import hashlib
import json

from exness_bot.logger import log
from exness_bot import config


def _utcnow():
    return datetime.datetime.utcnow()


def _in_session(ts):
    """UTC `ts` inside config's trading day/hour window? (same rule as indicators.session_ok,
    inlined so this module stays free of the pandas import)."""
    if config.TRADE_DAYS and ts.weekday() not in config.TRADE_DAYS:
        return False
    hours = config.SESSION_UTC_HOURS
    if not hours:
        return True
    start, end = hours
    return start <= ts.hour < end


class _State:
    def __init__(self):
        self.day = None            # date of the current budget window (UTC)
        self.calls_today = 0
        self.spend_today = 0.0     # estimated USD
        self.last_call_ts = None
        self.cache_key = None      # fingerprint of the last snapshot we answered
        self.cache_decision = None

    def roll_day(self):
        today = _utcnow().date()
        if today == self.day:
            return
        if self.day is not None:
            log.logger.info(
                f"LLM guard: day rollover. {self.day} used {self.calls_today} calls, "
                f"est ${self.spend_today:.4f}."
            )
        self.day = today
        self.calls_today = 0
        self.spend_today = 0.0


_state = _State()


def _fingerprint(snap, position_side):
    """Coarse hash of the things the decision actually depends on.

    Rounded hard so tiny wiggles count as 'unchanged' and reuse the cache.
    """
    rough = {
        "pos": position_side or "none",
        "tu": bool(snap.get("trend_up")),
        "td": bool(snap.get("trend_down")),
        "rsi": round(float(snap.get("rsi", 0)), 1),
        "fast": round(float(snap.get("sma_fast", 0)), 5),
        "slow": round(float(snap.get("sma_slow", 0)), 5),
        "fast_p": round(float(snap.get("sma_fast_prev", 0)), 5),
        "slow_p": round(float(snap.get("sma_slow_prev", 0)), 5),
    }
    return hashlib.md5(json.dumps(rough, sort_keys=True).encode()).hexdigest()


def _rule_has_setup(rule_decision):
    return rule_decision.get("action") in ("buy", "sell", "close")


def cached_for(snap, position_side):
    """Return a previously computed decision if the snapshot is effectively
    unchanged (and caching is enabled), else None."""
    if not config.LLM_CACHE_SNAPSHOT:
        return None
    if _fingerprint(snap, position_side) == _state.cache_key and _state.cache_decision is not None:
        return dict(_state.cache_decision)
    return None


def should_call_llm(snap, position_side, rule_decision):
    """Return ``(ok: bool, reason: str)``. When ok is False the caller must use
    the rule-based decision (or the cached one)."""
    _state.roll_day()

    if config.LLM_SKIP_OUTSIDE_SESSION and not _in_session(_utcnow()):
        return False, "outside trading session"

    if (config.LLM_MAX_CALLS_PER_DAY
            and _state.calls_today >= config.LLM_MAX_CALLS_PER_DAY):
        return False, f"daily call budget spent ({config.LLM_MAX_CALLS_PER_DAY})"

    if (config.LLM_DAILY_COST_LIMIT_USD
            and _state.spend_today >= config.LLM_DAILY_COST_LIMIT_USD):
        return False, f"daily cost limit reached (~${_state.spend_today:.4f})"

    if _state.last_call_ts is not None:
        gap = (_utcnow() - _state.last_call_ts).total_seconds()
        if gap < config.LLM_MIN_SECONDS_BETWEEN_CALLS:
            return False, f"only {gap:.0f}s since last call"

    if config.LLM_ONLY_ON_SIGNAL and not _rule_has_setup(rule_decision):
        return False, "no rule-side setup (LLM would likely say hold too)"

    return True, "ok"


def estimate_cost(prompt_text, reply_text):
    """Rough USD estimate from character counts (~4 chars per token)."""
    in_tok = max(1, len(prompt_text or "") // 4)
    out_tok = max(1, len(reply_text or "") // 4)
    cost = ((in_tok / 1000.0) * config.LLM_COST_PER_1K_INPUT
            + (out_tok / 1000.0) * config.LLM_COST_PER_1K_OUTPUT)
    return cost, in_tok, out_tok


def note_result(snap, position_side, decision, prompt_text, reply_text):
    """Record a completed LLM call: bump the counters, update the cache, log spend."""
    _state.roll_day()
    _state.calls_today += 1
    _state.last_call_ts = _utcnow()
    _state.cache_key = _fingerprint(snap, position_side)
    _state.cache_decision = dict(decision) if decision else None

    cost, in_tok, out_tok = estimate_cost(prompt_text, reply_text)
    _state.spend_today += cost
    log.logger.info(
        f"LLM call {_state.calls_today}"
        f"{('/' + str(config.LLM_MAX_CALLS_PER_DAY)) if config.LLM_MAX_CALLS_PER_DAY else ''} "
        f"today | ~{in_tok} in / {out_tok} out tok | est ${cost:.5f} "
        f"| est day total ${_state.spend_today:.4f}"
    )


def stats():
    return {
        "day": str(_state.day),
        "calls_today": _state.calls_today,
        "est_spend_today_usd": round(_state.spend_today, 5),
    }
