"""Send / modify / close orders through MT5. Honours config.DRY_RUN (logs only)."""

import time

import MetaTrader5 as mt5

from exness_bot.logger import log
from exness_bot import config
from exness_bot import mt5_client

_RETRY_RETCODES = {
    mt5.TRADE_RETCODE_REQUOTE,
    mt5.TRADE_RETCODE_PRICE_CHANGED,
    mt5.TRADE_RETCODE_PRICE_OFF,
    mt5.TRADE_RETCODE_TIMEOUT,
}


def _filling_mode(symbol_info):
    mode = symbol_info.filling_mode
    if mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _send_with_retry(build_request, tag):
    """build_request() -> dict, re-called each attempt so price is refreshed."""
    for attempt in range(1, config.ORDER_RETRIES + 1):
        request = build_request()
        if config.DRY_RUN:
            log.logger.info(f"[DRY_RUN] would {tag}: {request}")
            return None
        result = mt5.order_send(request)
        if result is None:
            log.logger.error(f"{tag} failed: order_send None ({mt5.last_error()})")
            return None
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            log.logger.info(
                f"{tag} ok: deal={result.deal} order={result.order} "
                f"price={result.price} vol={result.volume}"
            )
            return result
        if result.retcode in _RETRY_RETCODES and attempt < config.ORDER_RETRIES:
            log.logger.warning(f"{tag} retcode={result.retcode}, retry {attempt}/{config.ORDER_RETRIES}")
            time.sleep(0.5)
            continue
        log.logger.error(f"{tag} rejected: retcode={result.retcode} comment={result.comment}")
        return result
    return None


def open_position(side, lot, sl_price, tp_price, symbol_info):
    symbol = mt5_client.resolved_symbol()
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    def build():
        t = mt5_client.tick(symbol)
        price = t.ask if side == "buy" else t.bid
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "sl": round(sl_price, symbol_info.digits),
            "tp": round(tp_price, symbol_info.digits),
            "deviation": config.DEVIATION_POINTS,
            "magic": config.MAGIC,
            "comment": "exness_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": _filling_mode(symbol_info),
        }

    return _send_with_retry(build, f"OPEN {side} {lot} {symbol}")


def close_position(pos, symbol_info):
    symbol = mt5_client.resolved_symbol()
    if pos.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
    else:
        order_type = mt5.ORDER_TYPE_BUY

    def build():
        t = mt5_client.tick(symbol)
        price = t.bid if order_type == mt5.ORDER_TYPE_SELL else t.ask
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": config.DEVIATION_POINTS,
            "magic": config.MAGIC,
            "comment": "exness_bot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": _filling_mode(symbol_info),
        }

    return _send_with_retry(build, f"CLOSE ticket {pos.ticket}")


def modify_sl(pos, new_sl, symbol_info):
    def build():
        return {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": mt5_client.resolved_symbol(),
            "position": pos.ticket,
            "sl": round(new_sl, symbol_info.digits),
            "tp": pos.tp,
            "magic": config.MAGIC,
        }

    return _send_with_retry(build, f"MODIFY-SL ticket {pos.ticket} -> {new_sl}")
