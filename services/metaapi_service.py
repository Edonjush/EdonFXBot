"""Cached MetaAPI RPC adapter with fail-closed demo and risk metadata."""
import asyncio
import logging
import math

from metaapi_cloud_sdk import MetaApi
from config.settings import API_KEY, ACCOUNT_ID, DEMO_ONLY
from services.account_risk_state import update_drawdown_metrics
from services.account_policy import is_demo_account

logger = logging.getLogger(__name__)
_api = None
_account = None
_connection = None
_connection_lock = asyncio.Lock()


def _account_server(account, info=None):
    info = info or {}
    candidates = [info.get("server"), info.get("brokerServer"),
                  getattr(account, "server", None), getattr(account, "broker", None)]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return ""



async def connect_account():
    """Return a synchronized cached RPC connection; reconnect after failures."""
    global _api, _account, _connection
    if not API_KEY or not ACCOUNT_ID:
        logger.error("MetaAPI API_KEY or ACCOUNT_ID is not configured")
        return None
    async with _connection_lock:
        try:
            if _connection is not None:
                return _connection
            _api = _api or MetaApi(API_KEY)
            _account = await _api.metatrader_account_api.get_account(ACCOUNT_ID)
            if getattr(_account, "state", None) != "DEPLOYED":
                await _account.deploy()
            await _account.wait_connected()
            connection = _account.get_rpc_connection()
            await connection.connect()
            await connection.wait_synchronized()
            _connection = connection
            logger.info("MetaAPI RPC connection synchronized (server=%s)", getattr(_account, "server", "unknown"))
            return _connection
        except Exception:
            _connection = None
            logger.exception("MetaAPI connection failed")
            return None


async def disconnect_account():
    global _connection
    async with _connection_lock:
        connection, _connection = _connection, None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                logger.exception("Error closing MetaAPI connection")


def _pip_size(symbol):
    symbol = str(symbol).upper()
    if "JPY" in symbol:
        return 0.01
    if "XAU" in symbol or any(x in symbol for x in ("BTC", "ETH")):
        raise ValueError("Pip conversion is undefined for this instrument; use absolute prices")
    return 0.0001


def _pip_multiplier(symbol):
    return 100 if "JPY" in str(symbol).upper() else 10000


async def place_trade(symbol, direction, volume, stop_loss=None, take_profit=None, sl_pips=None):
    """Submit only protected market orders and return normalized broker evidence."""
    try:
        direction = str(direction).upper().strip()
        volume = float(volume)
        if direction not in {"BUY", "SELL"} or not math.isfinite(volume) or volume <= 0:
            return {"success": False, "message": "Invalid direction or volume"}
        connection = await connect_account()
        if connection is None:
            return {"success": False, "message": "Failed connecting to MT5"}
        info = await get_account_info()
        if DEMO_ONLY and (not info or info.get("_is_demo") is not True):
            return {"success": False, "message": "Demo-only policy: account is not positively identified as demo/trial"}
        quote = await connection.get_symbol_price(symbol)
        ask, bid = float(quote["ask"]), float(quote["bid"])
        if not all(math.isfinite(x) and x > 0 for x in (ask, bid)) or ask < bid:
            return {"success": False, "message": "Invalid broker quote"}
        if stop_loss is None and sl_pips is not None:
            distance = float(sl_pips) * _pip_size(symbol)
            stop_loss = ask - distance if direction == "BUY" else bid + distance
        if stop_loss is None:
            return {"success": False, "message": "A protective stop-loss is mandatory"}
        stop_loss = float(stop_loss)
        take_profit = None if take_profit is None else float(take_profit)
        if not math.isfinite(stop_loss) or (take_profit is not None and not math.isfinite(take_profit)):
            return {"success": False, "message": "Non-finite protective price"}
        if direction == "BUY":
            if stop_loss >= ask or (take_profit is not None and take_profit <= ask):
                return {"success": False, "message": "BUY protection prices are on the wrong side of market"}
            result = await connection.create_market_buy_order(symbol=symbol, volume=volume,
                                                               stop_loss=stop_loss, take_profit=take_profit)
        else:
            if stop_loss <= bid or (take_profit is not None and take_profit >= bid):
                return {"success": False, "message": "SELL protection prices are on the wrong side of market"}
            result = await connection.create_market_sell_order(symbol=symbol, volume=volume,
                                                                 stop_loss=stop_loss, take_profit=take_profit)
        if not isinstance(result, dict):
            return {"success": False, "message": "MetaAPI returned an unexpected response type"}
        code = result.get("stringCode")
        success_codes = {"ERR_NO_ERROR", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE",
                         "TRADE_RETCODE_DONE_PARTIAL", "TRADE_RETCODE_NO_CHANGES"}
        order_id, position_id = result.get("orderId"), result.get("positionId")
        confirmed = code in success_codes and bool(order_id or position_id)
        return {
            "success": bool(confirmed), "order_id": str(order_id) if order_id else None,
            "position_id": str(position_id) if position_id else None,
            "numeric_code": result.get("numericCode"), "string_code": code,
            "message": result.get("message") or ("Broker accepted trade" if confirmed else "Broker did not confirm trade"),
            "symbol": symbol, "direction": direction, "volume": volume,
            "stop_loss": stop_loss, "take_profit": take_profit,
        }
    except Exception as exc:
        logger.exception("Trade submission failed")
        await disconnect_account()
        return {"success": False, "message": f"Trade submission failed: {exc}"}


async def get_account_info():
    global _account
    try:
        connection = await connect_account()
        if connection is None:
            return None
        info = await connection.get_account_information()
        if not isinstance(info, dict):
            return None
        server = _account_server(_account, info)
        enriched = dict(info)
        enriched["server"] = server or info.get("server")
        enriched["_is_demo"] = is_demo_account(info, server)
        try:
            equity = float(info.get("equity", 0))
            enriched.update(update_drawdown_metrics(equity))
        except Exception as exc:
            logger.error("Cannot establish account drawdown state: %s", exc)
            enriched["_risk_state_valid"] = False
        else:
            enriched["_risk_state_valid"] = True
        return enriched
    except Exception:
        logger.exception("Account info error")
        await disconnect_account()
        return None


async def get_positions():
    try:
        connection = await connect_account()
        if connection is None:
            return None
        positions = await connection.get_positions()
        return positions if isinstance(positions, list) else None
    except Exception:
        logger.exception("Could not retrieve open positions")
        await disconnect_account()
        return None


async def get_symbol_risk_spec(symbol):
    """Normalize broker sizing only when profit-currency valuation is exact."""
    try:
        connection = await connect_account()
        if connection is None:
            return None
        raw = await connection.get_symbol_specification(symbol)
        account = await connection.get_account_information()
        quote = await connection.get_symbol_price(symbol)
        if not all(isinstance(x, dict) for x in (raw, account, quote)):
            return None
        ask, bid = float(quote.get("ask", 0)), float(quote.get("bid", 0))
        tick_size = float(raw.get("tickSize", 0))
        contract_size = float(raw.get("contractSize", 0))
        account_currency = str(account.get("currency", "")).upper()
        profit_currency = str(raw.get("profitCurrency", "")).upper()
        min_volume = float(raw.get("minVolume", 0))
        max_volume = float(raw.get("maxVolume", 0))
        volume_step = float(raw.get("volumeStep", 0))
        values = (ask, bid, tick_size, contract_size, min_volume, max_volume, volume_step)
        if not all(math.isfinite(v) for v in values) or bid <= 0 or ask < bid:
            return None
        if (not account_currency or not profit_currency or account_currency != profit_currency
                or tick_size <= 0 or contract_size <= 0 or min_volume <= 0
                or max_volume < min_volume or volume_step <= 0):
            logger.warning("Cannot safely normalize risk specification for %s", symbol)
            return None
        if raw.get("tradeMode") in {"SYMBOL_TRADE_MODE_DISABLED", "SYMBOL_TRADE_MODE_CLOSEONLY"}:
            return None
        return {"tickSize": tick_size, "tickValueAccount": tick_size * contract_size,
                "volumeMin": min_volume, "volumeMax": max_volume, "volumeStep": volume_step,
                "accountCurrency": account_currency, "profitCurrency": profit_currency,
                "tradeMode": raw.get("tradeMode"), "currentAsk": ask, "currentBid": bid}
    except Exception:
        logger.exception("Could not retrieve valid broker risk specification for %s", symbol)
        await disconnect_account()
        return None


async def get_spread(symbol):
    try:
        connection = await connect_account()
        if connection is None:
            return None
        quote = await connection.get_symbol_price(symbol)
        ask, bid = float(quote["ask"]), float(quote["bid"])
        if not all(math.isfinite(x) and x > 0 for x in (ask, bid)) or ask < bid:
            return None
        if "XAU" in symbol.upper() or any(x in symbol.upper() for x in ("BTC", "ETH")):
            return round(ask - bid, 6)
        return round((ask - bid) * _pip_multiplier(symbol), 3)
    except Exception:
        logger.exception("Spread fetch error for %s", symbol)
        await disconnect_account()
        return None
