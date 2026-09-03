"""Position sizing, stop-loss / take-profit levels and portfolio guards."""

import datetime

from exness_bot.logger import log
from exness_bot import config
from exness_bot import mt5_client
from exness_bot import indicators


def _round_lot(symbol_info, lot):
    step = symbol_info.volume_step or 0.01
    lot = round(round(lot / step) * step, 2)
    lot = max(symbol_info.volume_min, min(lot, config.MAX_LOT, symbol_info.volume_max))
    return lot


def position_size(symbol_info, sl_price_distance):
    """Lot size so that hitting the stop loses ~RISK_PER_TRADE_PCT of balance."""
    acc = mt5_client.account_info()
    if acc is None or sl_price_distance <= 0:
        return config.FIXED_LOT_FALLBACK

    risk_money = acc.balance * (config.RISK_PER_TRADE_PCT / 100.0)
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size or symbol_info.point
    if not tick_value or not tick_size:
        return config.FIXED_LOT_FALLBACK

    loss_per_lot = (sl_price_distance / tick_size) * tick_value
    if loss_per_lot <= 0:
        return config.FIXED_LOT_FALLBACK

    return _round_lot(symbol_info, risk_money / loss_per_lot)


def sl_tp(side, entry_price, atr, symbol_info):
    """Return (sl_price, tp_price) respecting the broker's minimum stop distance."""
    sl_dist = config.SL_ATR_MULT * atr
    tp_dist = config.TP_ATR_MULT * atr

    min_dist = (symbol_info.trade_stops_level or 0) * symbol_info.point
    sl_dist = max(sl_dist, min_dist)
    tp_dist = max(tp_dist, min_dist)

    if side == "buy":
        return entry_price - sl_dist, entry_price + tp_dist
    return entry_price + sl_dist, entry_price - tp_dist


def new_trailing_sl(pos, atr, symbol_info, price):
    """Improved SL price for an open MT5 position, or None to leave it."""
    import MetaTrader5 as mt5
    side = "buy" if pos.type == mt5.POSITION_TYPE_BUY else "sell"
    new_sl = indicators.trailing_sl(side, pos.price_open, pos.sl, atr, price)
    return round(new_sl, symbol_info.digits) if new_sl is not None else None


def within_session():
    """True if the current UTC time is inside the configured trading window."""
    return indicators.session_ok(datetime.datetime.utcnow())


class DailyGuard:
    """Blocks new trades once the day's equity drawdown exceeds the limit."""

    def __init__(self):
        acc = mt5_client.account_info()
        self.day = None
        self.start_equity = acc.equity if acc else 0.0
        self._roll(_today())

    def _roll(self, day):
        acc = mt5_client.account_info()
        self.day = day
        self.start_equity = acc.equity if acc else self.start_equity
        log.logger.info(f"Daily guard reset for {day}, start equity {self.start_equity}")

    def can_trade(self):
        today = _today()
        if today != self.day:
            self._roll(today)
        acc = mt5_client.account_info()
        if acc is None or self.start_equity <= 0:
            return True
        drawdown_pct = (self.start_equity - acc.equity) / self.start_equity * 100.0
        if drawdown_pct >= config.DAILY_MAX_LOSS_PCT:
            log.logger.warning(
                f"Daily loss limit hit ({drawdown_pct:.2f}% >= {config.DAILY_MAX_LOSS_PCT}%). "
                f"No new trades today."
            )
            return False
        return True


def _today():
    import datetime
    return datetime.datetime.utcnow().date()
