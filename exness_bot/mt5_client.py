"""Thin wrapper around the MetaTrader5 package for connecting to Exness."""

import MetaTrader5 as mt5

from exness_bot.logger import log

try:
    import settings
except Exception:  # pragma: no cover
    settings = None


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


def ensure_symbol(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol {symbol} not found on this account")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol {symbol}")
    return mt5.symbol_info(symbol)


def account_info():
    return mt5.account_info()


def positions(symbol=None):
    res = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return list(res) if res else []


def rates(symbol, timeframe, count):
    return mt5.copy_rates_from_pos(symbol, timeframe, 0, count)


def tick(symbol):
    return mt5.symbol_info_tick(symbol)


def shutdown():
    mt5.shutdown()
