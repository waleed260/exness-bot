"""Thin wrapper around the MetaTrader5 package for connecting to Exness."""

import MetaTrader5 as mt5

from exness_bot.logger import log
from exness_bot import config

try:
    import settings
except Exception:  # pragma: no cover
    settings = None

# Exness lists the same instrument under different suffixes per account type
# (EURUSD, EURUSDm, EURUSD.z, ...). Resolved once at startup by resolve_symbol().
_SUFFIXES = ["", "m", "z", "c", ".", "._", "-", "_", ".r", ".raw", "pro", ".pro", "e"]
_RESOLVED = {"symbol": None}


def connect():
    """Initialise the MT5 terminal and log in to the Exness account."""
    if settings is None:
        raise RuntimeError("exness_bot/settings.py not found. Copy settings.example.py to settings.py first.")

    ok = mt5.initialize(
        path=settings.MT5_PATH,
        login=int(settings.MT5_LOGIN),
        password=settings.MT5_PASSWORD,
        server=settings.MT5_SERVER,
    )
    if not ok:
        raise RuntimeError(f"mt5.initialize failed: {mt5.last_error()}")

    acc = mt5.account_info()
    if acc is None:
        raise RuntimeError(f"mt5.account_info failed: {mt5.last_error()}")
    log.logger.info(
        f"Connected: login={acc.login} server={acc.server} "
        f"balance={acc.balance} {acc.currency} trade_mode={acc.trade_mode}"
    )
    return acc


def is_demo_account():
    acc = mt5.account_info()
    # 0 = ACCOUNT_TRADE_MODE_DEMO, 1 = CONTEST, 2 = REAL
    return acc is not None and acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_REAL


def resolve_symbol(base=None):
    """Find the real tradable symbol name for `base` on this account and cache it."""
    base = base or config.SYMBOL
    for suf in _SUFFIXES:
        name = base + suf
        info = mt5.symbol_info(name)
        if info is None:
            continue
        if not info.visible and not mt5.symbol_select(name, True):
            continue
        _RESOLVED["symbol"] = name
        if name != base:
            log.logger.info(f"Resolved symbol {base} -> {name}")
        return mt5.symbol_info(name)
    raise RuntimeError(f"Symbol {base}(+suffix) not found / not selectable on this account")


def resolved_symbol():
    return _RESOLVED["symbol"] or config.SYMBOL


def symbol_info():
    return mt5.symbol_info(resolved_symbol())


def spread_points():
    info = mt5.symbol_info(resolved_symbol())
    if info is None:
        return None
    if info.spread:  # broker-reported, in points
        return info.spread
    t = mt5.symbol_info_tick(resolved_symbol())
    if t and info.point:
        return round((t.ask - t.bid) / info.point)
    return None


def account_info():
    return mt5.account_info()


def positions(symbol=None):
    symbol = symbol or resolved_symbol()
    res = mt5.positions_get(symbol=symbol)
    return list(res) if res else []


def rates(symbol, timeframe, count):
    return mt5.copy_rates_from_pos(symbol, timeframe, 0, count)


def tick(symbol=None):
    return mt5.symbol_info_tick(symbol or resolved_symbol())


def shutdown():
    mt5.shutdown()
