"""VP_BREAKOUT_M5_V1 fixed geometry, broker-aware sizing, and daily guard."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from typing import Callable, Optional

STOP_LOSS_PIPS = 30
TAKE_PROFIT_PIPS = 40
RISK_FRACTION = 0.005
MAX_CONSECUTIVE_LOSSES = 2
MAX_DAILY_LOSS_FRACTION = 0.02


def _get(info, name, default=None):
    return getattr(info, name, default) if not isinstance(info, dict) else info.get(name, default)


def validate_pip_size(pip_size: float, symbol_info) -> bool:
    """Validate explicit pip size against point, digits, and tick size."""
    point = float(_get(symbol_info, "point", 0) or 0)
    tick_size = float(_get(symbol_info, "trade_tick_size", 0) or point)
    digits = _get(symbol_info, "digits", None)
    if not math.isfinite(pip_size) or pip_size <= 0 or point <= 0 or tick_size <= 0:
        return False
    if digits is not None and round(pip_size, int(digits)) <= 0:
        return False
    point_multiple = pip_size / point
    tick_multiple = pip_size / tick_size
    return (abs(point_multiple - round(point_multiple)) < 1e-9
            and abs(tick_multiple - round(tick_multiple)) < 1e-9)


def fixed_sl_tp(side: str, entry_price: float, pip_size: float, symbol_info=None) -> tuple[float, float]:
    if side not in {"buy", "sell"} or not math.isfinite(entry_price) or not validate_pip_size(pip_size, symbol_info):
        raise ValueError("invalid side, entry price, or pip configuration")
    sl_distance = STOP_LOSS_PIPS * pip_size
    tp_distance = TAKE_PROFIT_PIPS * pip_size
    if side == "buy":
        return entry_price - sl_distance, entry_price + tp_distance
    return entry_price + sl_distance, entry_price - tp_distance


def spread_allowed(bid: float, ask: float, pip_size: float, max_spread_pips: float) -> bool:
    if not all(math.isfinite(float(v)) for v in (bid, ask, pip_size, max_spread_pips)):
        return False
    if bid <= 0 or ask <= bid or pip_size <= 0 or max_spread_pips < 0:
        return False
    return (ask - bid) / pip_size <= max_spread_pips


@dataclass(frozen=True)
class SizingResult:
    approved: bool
    volume: float
    risk_budget: float
    reason: str


def _floor_step(value: float, step: float) -> float:
    return math.floor((value + 1e-12) / step) * step


def size_for_risk(balance: float, entry_price: float, stop_price: float, symbol_info,
                  order_calc_profit: Callable[[float, float, float], float],
                  *, commission_per_lot: float = 0.0) -> SizingResult:
    """Size with broker/account profit math; reject below-minimum instead of rounding up."""
    minimum = float(_get(symbol_info, "volume_min", 0) or 0)
    maximum = float(_get(symbol_info, "volume_max", 0) or 0)
    step = float(_get(symbol_info, "volume_step", 0) or 0)
    if balance <= 0 or minimum <= 0 or maximum < minimum or step <= 0:
        return SizingResult(False, 0.0, max(0.0, balance * RISK_FRACTION), "invalid broker volume constraints")
    risk_budget = balance * RISK_FRACTION
    loss_one_lot = abs(float(order_calc_profit(1.0, entry_price, stop_price)))
    if not math.isfinite(loss_one_lot) or loss_one_lot <= 0:
        return SizingResult(False, 0.0, risk_budget, "invalid order_calc_profit result")
    available = risk_budget - max(0.0, commission_per_lot)
    raw_volume = available / loss_one_lot
    quantized = min(maximum, _floor_step(raw_volume, step))
    if quantized < minimum:
        return SizingResult(False, 0.0, risk_budget, "minimum volume exceeds risk budget")
    quantized = _floor_step(quantized, step)
    actual_risk = quantized * loss_one_lot + max(0.0, commission_per_lot) * quantized
    if actual_risk > risk_budget + 1e-9:
        return SizingResult(False, 0.0, risk_budget, "quantized volume exceeds risk budget")
    return SizingResult(True, quantized, risk_budget, "approved")


@dataclass
class DailyGuard:
    day: date
    day_start_balance: float
    realized_loss: float = 0.0
    consecutive_losses: int = 0

    @classmethod
    def start(cls, day: Optional[date] = None, balance: float = 0.0):
        return cls(day or datetime.now(timezone.utc).date(), float(balance))

    def roll(self, day: date, balance: float) -> None:
        if day != self.day:
            self.day = day
            self.day_start_balance = float(balance)
            self.realized_loss = 0.0
            self.consecutive_losses = 0

    def record_close(self, pnl: float) -> None:
        if pnl < 0:
            self.realized_loss += -float(pnl)
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def can_trade(self) -> tuple[bool, str]:
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            return False, "consecutive-loss stop"
        if self.day_start_balance > 0 and self.realized_loss >= self.day_start_balance * MAX_DAILY_LOSS_FRACTION:
            return False, "daily-loss stop"
        return True, "approved"
