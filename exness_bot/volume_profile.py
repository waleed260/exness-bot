"""Deterministic volume-profile primitives for VP_BREAKOUT_M5_V1.

This module is intentionally independent of the legacy SMA/RSI strategy and
backtester.  A profile snapshot only consumes candles strictly before the
candidate candle, which is the required anti-lookahead boundary.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Optional
import math

SESSION_START_HOUR_UTC = 3
VALUE_AREA_FRACTION = 0.70


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def profile_session_id(timestamp: datetime) -> str:
    """Return the UTC session date whose profile starts at 03:00 UTC."""
    ts = _utc(timestamp)
    session_date = ts.date() if ts.hour >= SESSION_START_HOUR_UTC else (ts - timedelta(days=1)).date()
    return session_date.isoformat()


def _value(candle: Mapping) -> float:
    if "price" in candle:
        return float(candle["price"])
    return (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3.0


def _time(candle: Mapping) -> datetime:
    value = candle["time"]
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(value)


@dataclass(frozen=True)
class ProfileSnapshot:
    session_id: str
    vah: float
    val: float
    poc: float
    total_volume: float
    included_candles: int
    bin_size: float


def _bin_price(price: float, bin_size: float) -> float:
    return math.floor(price / bin_size) * bin_size


def _levels(candles: list, bin_size: float, value_area_fraction: float) -> tuple[float, float, float, float]:
    bins: dict[float, float] = {}
    for candle in candles:
        volume = float(candle.get("volume", candle.get("tick_volume", 0.0)))
        if not math.isfinite(volume) or volume < 0:
            raise ValueError("volume must be finite and non-negative")
        price = _bin_price(_value(candle), bin_size)
        bins[price] = bins.get(price, 0.0) + volume
    if not bins or sum(bins.values()) <= 0:
        raise ValueError("profile requires positive volume")
    total = sum(bins.values())
    poc = max(bins, key=lambda price: (bins[price], -price))
    selected = {poc}
    covered = bins[poc]
    target = total * value_area_fraction
    while covered < target and len(selected) < len(bins):
        candidates = []
        for price in (poc - bin_size, poc + bin_size):
            if price in bins and price not in selected:
                candidates.append(price)
        if not candidates:
            candidates = [price for price in bins if price not in selected]
        chosen = max(candidates, key=lambda price: (bins[price], -price))
        selected.add(chosen)
        covered += bins[chosen]
    return max(selected), min(selected), poc, total


def profile_snapshot(
    candles: Iterable[Mapping], evaluation_time: datetime, *, bin_size: float = 0.01,
    value_area_fraction: float = VALUE_AREA_FRACTION,
) -> ProfileSnapshot:
    """Build the active profile using only candles strictly before evaluation_time."""
    if bin_size <= 0 or not 0 < value_area_fraction <= 1:
        raise ValueError("invalid profile parameters")
    evaluation_time = _utc(evaluation_time)
    session_id = profile_session_id(evaluation_time)
    included = [
        candle for candle in candles
        if _time(candle) < evaluation_time and profile_session_id(_time(candle)) == session_id
    ]
    vah, val, poc, total = _levels(included, bin_size, value_area_fraction)
    return ProfileSnapshot(session_id, vah, val, poc, total, len(included), bin_size)


class VolumeProfile:
    """Small session-aware accumulator useful for streaming closed candles."""

    def __init__(self, *, bin_size: float = 0.01, value_area_fraction: float = VALUE_AREA_FRACTION):
        self.bin_size = bin_size
        self.value_area_fraction = value_area_fraction
        self.session_id: Optional[str] = None
        self._candles: list[Mapping] = []

    def add_closed_candle(self, candle: Mapping) -> None:
        session = profile_session_id(_time(candle))
        if self.session_id != session:
            self.session_id = session
            self._candles = []
        self._candles.append(dict(candle))

    def snapshot_before(self, evaluation_time: datetime) -> ProfileSnapshot:
        return profile_snapshot(self._candles, evaluation_time, bin_size=self.bin_size,
                                value_area_fraction=self.value_area_fraction)
