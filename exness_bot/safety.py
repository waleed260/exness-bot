"""Fail-closed validation and stateful guards for automated trading."""

import datetime as _dt
import os
from dataclasses import dataclass, field

from exness_bot import config


def _utcnow():
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


@dataclass
class SafetyState:
    day: _dt.date = field(default_factory=lambda: _utcnow().date())
    trades_today: int = 0
    consecutive_losses: int = 0
    open_exposure_pct: float = 0.0

    def roll_day(self, now=None):
        day = (now or _utcnow()).date()
        if day != self.day:
            self.day = day
            self.trades_today = 0
            self.consecutive_losses = 0

    def record_open(self, exposure_pct, now=None):
        self.roll_day(now)
        self.trades_today += 1
        self.open_exposure_pct += max(0.0, float(exposure_pct))

    def record_close(self, pnl, exposure_pct=0.0, now=None):
        self.roll_day(now)
        self.open_exposure_pct = max(0.0, self.open_exposure_pct - max(0.0, float(exposure_pct)))
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0


def emergency_stop_active(path=None):
    return os.path.exists(path or config.EMERGENCY_STOP_FILE)


def validate_order(*, side, volume, price, sl, tp, spread_points=None,
                   free_margin_pct=None, signal_time=None, now=None,
                   state=None, existing_positions=0, account_exposure_pct=0.0,
                   emergency_stop=None):
    """Return (True, 'ok') or (False, reason) for a proposed order."""
    if emergency_stop is None:
        emergency_stop = emergency_stop_active()
    if emergency_stop:
        return False, "emergency stop is active"
    if side not in {"buy", "sell"}:
        return False, "invalid side"
    try:
        values = [float(volume), float(price), float(sl), float(tp)]
    except (TypeError, ValueError):
        return False, "non-numeric order parameters"
    if any(v <= 0 for v in values):
        return False, "volume and prices must be positive"
    if side == "buy" and not (sl < price < tp):
        return False, "buy requires SL < price < TP"
    if side == "sell" and not (tp < price < sl):
        return False, "sell requires TP < price < SL"
    if spread_points is not None and spread_points > config.MAX_SPREAD_POINTS:
        return False, "spread exceeds limit"
    if free_margin_pct is not None and free_margin_pct < config.MIN_FREE_MARGIN_PCT:
        return False, "free margin below limit"
    if existing_positions >= config.MAX_OPEN_POSITIONS:
        return False, "maximum open positions reached"
    if account_exposure_pct > config.MAX_ACCOUNT_EXPOSURE_PCT:
        return False, "account exposure exceeds limit"
    if state is not None:
        state.roll_day(now)
        if state.trades_today >= config.MAX_TRADES_PER_DAY:
            return False, "maximum trades per day reached"
        if state.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            return False, "consecutive-loss protection active"
        if state.open_exposure_pct + account_exposure_pct > config.MAX_ACCOUNT_EXPOSURE_PCT:
            return False, "combined exposure exceeds limit"
    if signal_time is not None:
        current = now or _utcnow()
        if current.tzinfo is not None:
            current = current.replace(tzinfo=None)
        if signal_time.tzinfo is not None:
            signal_time = signal_time.replace(tzinfo=None)
        age = (current - signal_time).total_seconds()
        if age < 0 or age > config.MAX_SIGNAL_AGE_SECONDS:
            return False, "signal is stale or from the future"
    return True, "ok"
