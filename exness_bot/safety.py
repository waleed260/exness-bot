"""Fail-closed validation and stateful guards for automated trading."""

import datetime as _dt
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from exness_bot import config


def _utcnow():
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


@dataclass
class SafetyState:
    day: _dt.date = field(default_factory=lambda: _utcnow().date())
    trades_today: int = 0
    consecutive_losses: int = 0
    open_exposure_pct: float = 0.0
    state_path: Optional[str] = None

    def __post_init__(self):
        self._load()

    def _load(self):
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.day = _dt.date.fromisoformat(data["day"])
            self.trades_today = int(data.get("trades_today", 0))
            self.consecutive_losses = int(data.get("consecutive_losses", 0))
            self.open_exposure_pct = float(data.get("open_exposure_pct", 0.0))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            # Corrupt local state must not create permission to trade.
            self.trades_today = config.MAX_TRADES_PER_DAY
            self.consecutive_losses = config.MAX_CONSECUTIVE_LOSSES

    def _save(self):
        if not self.state_path:
            return
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="safety-", dir=directory or ".", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"day": self.day.isoformat(), "trades_today": self.trades_today,
                           "consecutive_losses": self.consecutive_losses,
                           "open_exposure_pct": self.open_exposure_pct}, f)
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def roll_day(self, now=None):
        day = (now or _utcnow()).date()
        if day != self.day:
            self.day = day
            self.trades_today = 0
            self._save()

    def record_open(self, exposure_pct, now=None):
        self.roll_day(now)
        self.trades_today += 1
        self.open_exposure_pct += max(0.0, float(exposure_pct))
        self._save()

    def record_close(self, pnl, exposure_pct=0.0, now=None):
        self.roll_day(now)
        self.open_exposure_pct = max(0.0, self.open_exposure_pct - max(0.0, float(exposure_pct)))
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0
        self._save()

    def reconcile_open_positions(self, count, exposure_pct):
        """Reset open exposure from the trusted broker position snapshot."""
        self.open_exposure_pct = max(0.0, float(count) * float(exposure_pct))
        self._save()


class SignalLedger:
    """Persistent idempotency ledger for signal execution claims."""

    def __init__(self, path=None):
        self.path = path
        self.claimed = set()
        self._load()

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.claimed = set(str(x) for x in data.get("claimed", []))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # An unreadable ledger fails closed: the caller must not claim new signals.
            self.claimed = {"__LEDGER_CORRUPT__"}

    def _save(self):
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="signals-", dir=directory or ".", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"claimed": sorted(self.claimed)}, f)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def claim(self, signal_id):
        signal_id = str(signal_id)
        if signal_id in self.claimed or "__LEDGER_CORRUPT__" in self.claimed:
            return False
        self.claimed.add(signal_id)
        self._save()
        return True


def environment_allows_execution(*, account_is_demo, mode, demo_only,
                                  live_trading_enabled, confirm_live_string):
    """Authorize an execution mode before the runner can submit anything."""
    if mode not in {"simulation", "demo", "live"}:
        return False, "unknown execution mode"
    if account_is_demo:
        if mode == "live":
            return False, "live mode is not valid for a demo account"
        return True, "ok"
    if demo_only:
        return False, "live account rejected by DEMO_ONLY"
    if mode != "live":
        return False, "live account requires live execution mode"
    if not live_trading_enabled:
        return False, "live trading gate is disabled"
    if confirm_live_string != "I ACCEPT THE RISK":
        return False, "live confirmation string is missing"
    return True, "ok"


def emergency_stop_active(path=None):
    return os.path.exists(path or config.EMERGENCY_STOP_FILE)


def validate_order(*, side, volume, price, sl, tp, spread_points=None,
                   slippage_points=None, free_margin_pct=None, signal_time=None, now=None,
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
    if float(volume) > config.MAX_LOT:
        return False, "volume exceeds maximum lot"
    sl_distance = abs(float(price) - float(sl))
    tp_distance = abs(float(tp) - float(price))
    if config.MIN_SL_DISTANCE and sl_distance < config.MIN_SL_DISTANCE:
        return False, "SL distance below minimum"
    if config.MAX_SL_DISTANCE and sl_distance > config.MAX_SL_DISTANCE:
        return False, "SL distance above maximum"
    if config.MIN_TP_DISTANCE and tp_distance < config.MIN_TP_DISTANCE:
        return False, "TP distance below minimum"
    if config.MAX_TP_DISTANCE and tp_distance > config.MAX_TP_DISTANCE:
        return False, "TP distance above maximum"
    if side == "buy" and not (sl < price < tp):
        return False, "buy requires SL < price < TP"
    if side == "sell" and not (tp < price < sl):
        return False, "sell requires TP < price < SL"
    if spread_points is not None and spread_points > config.MAX_SPREAD_POINTS:
        return False, "spread exceeds limit"
    if slippage_points is not None and slippage_points > config.MAX_SLIPPAGE_POINTS:
        return False, "slippage exceeds limit"
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
