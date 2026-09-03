"""Send / close orders through MT5. Honours config.DRY_RUN (logs only)."""

import MetaTrader5 as mt5

from exness_bot.logger import log
from exness_bot import config
from exness_bot import mt5_client


def _filling_mode(symbol_info):
    mode = symbol_info.filling_mode
    if mode & mt5.SYMBOL_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    if mode & mt5.SYMBOL_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def open_position(side, lot, sl_price, tp_price, symbol_info):
    tick = mt5_client.tick(config.SYMBOL)
    price = tick.ask if side == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": config.SYMBOL,
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

    if config.DRY_RUN:
        log.logger.info(f"[DRY_RUN] would OPEN {side} {lot} {config.SYMBOL} @~{price} sl={request['sl']} tp={request['tp']}")
        return None

    result = mt5.order_send(request)
    _log_result("OPEN", result)
    return result


def close_position(pos, symbol_info):
    tick = mt5_client.tick(config.SYMBOL)
    if pos.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": config.SYMBOL,
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

    if config.DRY_RUN:
        log.logger.info(f"[DRY_RUN] would CLOSE ticket {pos.ticket} ({pos.volume} {config.SYMBOL}) @~{price}")
        return None

    result = mt5.order_send(request)
    _log_result("CLOSE", result)
    return result


def _log_result(tag, result):
    if result is None:
        log.logger.error(f"{tag} failed: order_send returned None ({mt5.last_error()})")
        return
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.logger.error(f"{tag} rejected: retcode={result.retcode} comment={result.comment}")
    else:
        log.logger.info(f"{tag} ok: deal={result.deal} order={result.order} price={result.price} vol={result.volume}")
