"""Exact VP_BREAKOUT_M5_V1 breakout confirmation and trigger state machine."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

NO_SETUP = "NO_SETUP"
BREAKOUT_DETECTED = "BREAKOUT_DETECTED"
WAITING_NEXT_CANDLE_TRIGGER = "WAITING_NEXT_CANDLE_TRIGGER"
TRIGGERED = "TRIGGERED"
EXPIRED = "EXPIRED"
REJECTED = "REJECTED"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _session_id(value: datetime) -> str:
    ts = _utc(value)
    d = ts.date() if ts.hour >= 3 else (ts - timedelta(days=1)).date()
    return d.isoformat()


@dataclass(frozen=True)
class BreakoutSetup:
    breakout_id: str
    signal_id: str
    direction: str
    candle_time: datetime
    breakout_high: float
    breakout_low: float
    trigger_candle_start: datetime
    trigger_candle_end: datetime
    state: str = WAITING_NEXT_CANDLE_TRIGGER


@dataclass(frozen=True)
class StrategyEvent:
    event: str
    breakout_id: Optional[str] = None
    direction: Optional[str] = None
    reason: Optional[str] = None
    price: Optional[float] = None


class VPBreakoutStrategy:
    def __init__(self, *, timeframe_minutes: int = 5):
        if timeframe_minutes <= 0:
            raise ValueError("timeframe_minutes must be positive")
        self.timeframe = timedelta(minutes=timeframe_minutes)
        self.state = NO_SETUP
        self.pending: Optional[BreakoutSetup] = None
        self.used_breakouts: set[str] = set()

    @staticmethod
    def _id(direction: str, candle_time: datetime) -> str:
        raw = f"VP_BREAKOUT_M5_V1|{_session_id(candle_time)}|{_utc(candle_time).isoformat()}|{direction}"
        return sha256(raw.encode("utf-8")).hexdigest()[:24]

    def on_closed_candle(self, candle_time: datetime, high: float, low: float, close: float,
                         green_level: float, red_level: float) -> StrategyEvent:
        candle_time = _utc(candle_time)
        if self.pending is not None and candle_time >= self.pending.trigger_candle_end:
            expired = self.pending
            self.pending = None
            self.state = EXPIRED
            expired_event = StrategyEvent("setup_expired", expired.breakout_id, expired.direction, "confirmation_expired")
        else:
            expired_event = None
        direction = "buy" if close > green_level else "sell" if close < red_level else None
        if direction is None:
            return expired_event or StrategyEvent("no_setup", reason="no_closed_breakout")
        breakout_id = self._id(direction, candle_time)
        if breakout_id in self.used_breakouts:
            self.state = REJECTED
            return StrategyEvent("setup_rejected", breakout_id, direction, "duplicate_breakout")
        setup = BreakoutSetup(
            breakout_id=breakout_id,
            signal_id=breakout_id,
            direction=direction,
            candle_time=candle_time,
            breakout_high=float(high),
            breakout_low=float(low),
            trigger_candle_start=candle_time + self.timeframe,
            trigger_candle_end=candle_time + 2 * self.timeframe,
        )
        self.pending = setup
        self.used_breakouts.add(breakout_id)
        self.state = BREAKOUT_DETECTED
        self.state = WAITING_NEXT_CANDLE_TRIGGER
        return StrategyEvent("breakout_detected", breakout_id, direction)

    def on_tick(self, timestamp: datetime, bid: float, ask: float) -> StrategyEvent:
        if self.pending is None:
            return StrategyEvent("no_setup", reason="no_pending_setup")
        timestamp = _utc(timestamp)
        setup = self.pending
        if timestamp < setup.trigger_candle_start:
            return StrategyEvent("waiting", setup.breakout_id, setup.direction, "before_next_candle")
        if timestamp >= setup.trigger_candle_end:
            self.pending = None
            self.state = EXPIRED
            return StrategyEvent("setup_expired", setup.breakout_id, setup.direction, "confirmation_expired")
        if setup.direction == "buy" and float(ask) > setup.breakout_high:
            self.pending = None
            self.state = TRIGGERED
            return StrategyEvent("buy_triggered", setup.breakout_id, "buy", price=float(ask))
        if setup.direction == "sell" and float(bid) < setup.breakout_low:
            self.pending = None
            self.state = TRIGGERED
            return StrategyEvent("sell_triggered", setup.breakout_id, "sell", price=float(bid))
        return StrategyEvent("waiting", setup.breakout_id, setup.direction, "trigger_not_reached")
