"""TickerAll MT5 broker adapter and read-only live quote feed.

REST requests use the documented TickerAll account, symbol-specs and orders
routes. Market quotes use the TickerAll WebSocket ticks channel. Order POSTs
are never automatically retried because a timeout may occur after acceptance.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
import websockets
from dotenv import load_dotenv

from services.account_risk_state import update_drawdown_metrics
from config.settings import AUTO_TRADING_ALLOWED

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

logger = logging.getLogger(__name__)
API_BASE = "https://api.tickerall.com"
STREAM_URL = "wss://api.tickerall.com/v1/stream"
BROKER_SYMBOLS = ("EURUSDm",)

def canonical_broker_symbol(value):
    """Return the exact broker symbol for supported Stage 1 instruments."""
    candidate = str(value or "").strip().replace("/", "").casefold()
    if candidate in {"eurusd", "eurusdm"}:
        return "EURUSDm"
    return None
REQUEST_TIMEOUT = 20


class TickerAllError(RuntimeError):
    """A TickerAll request or response could not be safely processed."""


class TickerAllMarketData:
    """Authenticated TickerAll tick stream; quotes only, no order submission."""

    def __init__(self, api_key: str, account_id: str):
        self.api_key = api_key
        self.account_id = account_id
        self.ws = None
        self.reader_task = None
        self.latest = {}
        self.events = {symbol: asyncio.Event() for symbol in BROKER_SYMBOLS}
        self.connected = False
        self.subscribed = False

    async def start(self):
        if self.connected and self.subscribed:
            return
        if not self.api_key or not self.account_id:
            raise TickerAllError("TickerAll API credentials are not configured")
        self.ws = await websockets.connect(
            STREAM_URL,
            additional_headers={"Authorization": f"Bearer {self.api_key}"},
            open_timeout=20,
            close_timeout=5,
            ping_interval=15,
            ping_timeout=15,
            proxy=None,
        )
        self.connected = True
        await self.ws.send(json.dumps({
            "type": "subscribe",
            "channels": [{"kind": "ticks", "accountId": self.account_id,
                          "symbols": list(BROKER_SYMBOLS)}],
            "correlationId": "edonfxbot-tickerall-market-data",
        }))
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(
                    self.ws.recv(), timeout=max(0.1, deadline - time.monotonic())
                )
                message = json.loads(raw)
                self._process_message(message)
                if message.get("type") == "subscribed":
                    rejected = message.get("rejected") or []
                    if rejected:
                        raise TickerAllError(f"TickerAll rejected tick subscriptions: {rejected}")
                    self.subscribed = True
                    break
            if not self.subscribed:
                raise TickerAllError("TickerAll did not acknowledge tick subscription")
            self.reader_task = asyncio.create_task(self._reader())
        except Exception:
            await self.close()
            raise

    def _process_message(self, message):
        stack = [message]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                raw_symbol = item.get("symbol") or item.get("s")
                symbol = canonical_broker_symbol(raw_symbol)
                bid, ask = item.get("bid", item.get("b")), item.get("ask", item.get("a"))
                if symbol is not None and bid is not None and ask is not None:
                    try:
                        bid, ask = float(bid), float(ask)
                        if math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask:
                            self.latest[symbol] = {
                                "symbol": symbol, "bid": bid, "ask": ask,
                                "timestamp": item.get("timestamp"),
                                "received_monotonic": time.monotonic(),
                            }
                            self.events[symbol].set()
                    except (TypeError, ValueError, OverflowError):
                        logger.warning("Invalid TickerAll tick for %s", symbol)
                stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
            elif isinstance(item, list):
                stack.extend(item)

    async def _reader(self):
        try:
            async for raw in self.ws:
                try:
                    self._process_message(json.loads(raw))
                except (ValueError, TypeError):
                    continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TickerAll WebSocket reader stopped")
        finally:
            self.connected = False
            self.subscribed = False

# ==============================================================================================================
    # @staticmethod
    # def _timestamp_age(timestamp):
    #     if not isinstance(timestamp, str):
    #         return None
    #     try:
    #         parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    #         if parsed.tzinfo is None:
    #             return None
    #         return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    #     except (ValueError, TypeError, OverflowError):
    #         return None

    @staticmethod
    def _broker_timestamp_age(timestamp):
        """Return broker timestamp age in seconds, or None if invalid."""
        if not isinstance(timestamp, str):
            return None

        try:
            parsed = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )

            # Reject timestamps without timezone information.
            if parsed.tzinfo is None:
                return None

            return (
                datetime.now(timezone.utc)
                - parsed.astimezone(timezone.utc)
            ).total_seconds()

        except (ValueError, TypeError, OverflowError):
            return None

    # Backward compatibility with existing callers.
    _timestamp_age = _broker_timestamp_age
# ==============================================================================================================

    async def get_quote(self, symbol, max_age_seconds=5, wait_timeout_seconds=8):
        symbol = canonical_broker_symbol(symbol)
        if symbol is None:
            raise ValueError("Stage 1 supports EURUSDm only")
        if not self.connected or not self.subscribed:
            await self.start()
        deadline = time.monotonic() + wait_timeout_seconds
        event = self.events[symbol]
        while True:
            quote = self.latest.get(symbol)
            if quote:
                receive_age = time.monotonic() - quote["received_monotonic"]
                # broker_age = self._timestamp_age(quote.get("timestamp"))
                broker_age = self._broker_timestamp_age(quote.get("timestamp"))
                if (receive_age <= max_age_seconds and broker_age is not None
                        and -5 <= broker_age <= max_age_seconds):
                    result = dict(quote)
                    result["age_seconds"] = round(receive_age, 3)
                    result["broker_age_seconds"] = round(broker_age, 3)
                    result.pop("received_monotonic", None)
                    return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return None

    async def close(self):
        task, self.reader_task = self.reader_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        ws, self.ws = self.ws, None
        if ws:
            try:
                await ws.close()
            except Exception:
                logger.debug("TickerAll WebSocket close failed", exc_info=True)
        self.connected = self.subscribed = False


class TickerAllBroker:
    """REST account/spec/order adapter backed by TickerAll live quotes."""

    def __init__(self, api_key=None, account_id=None, session=None, market_data=None):
        self.api_key = (api_key if api_key is not None else os.getenv("TICKERALL_API_KEY", "")).strip()
        self.account_id = (account_id if account_id is not None else os.getenv("TICKERALL_ACCOUNT_ID", "")).strip()
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.market_data = market_data or TickerAllMarketData(self.api_key, self.account_id)

    def _request_sync(self, method, path, *, json_body=None, idempotency_key=None):
        if not self.api_key or not self.account_id:
            raise TickerAllError("TickerAll API credentials are not configured")
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self.session.request(
                method, f"{API_BASE}{path}", headers=headers or None,
                json=json_body, timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            # In particular, never retry a POST whose acceptance is uncertain.
            raise TickerAllError(f"TickerAll network error: {type(exc).__name__}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise TickerAllError(f"TickerAll returned non-JSON HTTP {response.status_code}") from exc
        if not response.ok:
            if isinstance(data, dict):
                code = str(data.get("error", "API_ERROR"))
                message = str(data.get("message", "Request rejected"))
            else:
                code, message = "API_ERROR", "Request rejected"
            raise TickerAllError(f"TickerAll HTTP {response.status_code}: {code}: {message}")
        if not isinstance(data, dict):
            raise TickerAllError("TickerAll returned an unexpected response type")
        return data

    async def _request(self, method, path, *, json_body=None, idempotency_key=None):
        return await asyncio.to_thread(
            self._request_sync, method, path,
            json_body=json_body, idempotency_key=idempotency_key,
        )

    def _account_path(self):
        return f"/v1/accounts/{self.account_id}"

    async def get_account_info(self):
        try:
            raw = await self._request("GET", self._account_path())
            nested = raw.get("account")
            if not isinstance(nested, dict):
                return None
            status = str(raw.get("status", "")).lower()
            read_only = raw.get("readOnly")
            is_demo = raw.get("isDemo") is True and str(nested.get("accountType", "")).lower() == "demo"
            balance = float(nested.get("balance"))
            equity = float(nested.get("equity"))
            if not all(math.isfinite(x) and x > 0 for x in (balance, equity)):
                return None
            if not isinstance(raw.get("positions"), list):
                return None
            result = {
                "broker": raw.get("broker"), "server": raw.get("server"),
                "status": status, "isDemo": raw.get("isDemo"),
                "_is_demo": is_demo, "readOnly": read_only,
                "tradeAllowed": status == "online" and read_only is False,
                "accountType": nested.get("accountType"),
                "balance": balance, "equity": equity,
                "currency": nested.get("currency"),
                "leverage": nested.get("leverage"),
                "margin": nested.get("margin"),
                "freeMargin": nested.get("freeMargin"),
                "positions": raw["positions"],
            }
            if not result["currency"]:
                return None
            try:
                result.update(update_drawdown_metrics(equity))
                result["_risk_state_valid"] = True
            except Exception:
                logger.exception("TickerAll equity drawdown state is invalid")
                result["_risk_state_valid"] = False
            return result
        except Exception:
            logger.exception("TickerAll account lookup failed")
            return None

    async def get_positions(self):
        account = await self._request("GET", self._account_path())
        positions = account.get("positions")
        return positions if isinstance(positions, list) else None

    async def get_symbol_risk_spec(self, symbol):
        symbol = canonical_broker_symbol(symbol)
        if symbol is None:
            return None
        try:
            data = await self._request("GET", f"{self._account_path()}/symbol-specs")
            specs = data.get("specs")
            if not isinstance(specs, list):
                return None
            raw = next((s for s in specs if isinstance(s, dict) and s.get("name") == symbol), None)
            if raw is None:
                return None
            account = await self.get_account_info()
            quote = await self.market_data.get_quote(symbol)
            if not account or not quote:
                return None
            tick_size = float(raw["tickSize"])
            tick_value = float(raw["tickValueAccount"])
            minimum = float(raw["volumeMin"])
            maximum = float(raw["volumeMax"])
            step = float(raw["volumeStep"])
            bid, ask = float(quote["bid"]), float(quote["ask"])
            values = (tick_size, tick_value, minimum, maximum, step, bid, ask)
            if not all(math.isfinite(v) for v in values):
                return None
            if (tick_size <= 0 or tick_value <= 0 or minimum <= 0 or maximum < minimum
                    or step <= 0 or bid <= 0 or ask < bid):
                return None
            tick_currency = raw.get("tickValueCurrency")
            if isinstance(tick_currency, dict):
                tick_currency = tick_currency.get("code")
            if str(tick_currency or "").upper() != str(account["currency"]).upper():
                logger.error("TickerAll tick-value currency mismatch for %s", symbol)
                return None
            # MT5 tradeMode 4 is full trading. Other modes are rejected here.
            if raw.get("tradeMode") != 4:
                logger.warning("TickerAll symbol %s is not in full-trading mode", symbol)
                return None
            return {
                "tickSize": tick_size, "tickValueAccount": tick_value,
                "volumeMin": minimum, "volumeMax": maximum, "volumeStep": step,
                "accountCurrency": account["currency"], "profitCurrency": raw.get("profitCurrency"),
                "tradeMode": raw.get("tradeMode"), "currentBid": bid, "currentAsk": ask,
                "quoteTimestamp": quote.get("timestamp"),
                "spreadPrice": ask - bid,
            }
        except Exception:
            logger.exception("TickerAll symbol specification lookup failed for %s", symbol)
            return None

    async def get_spread(self, symbol):
        symbol = canonical_broker_symbol(symbol)
        if symbol is None:
            return None
        quote = await self.market_data.get_quote(symbol)
        if not quote:
            return None
        difference = quote["ask"] - quote["bid"]
        if symbol.startswith("XAU"):
            return round(difference, 6)
        return round(difference / 0.0001, 3)

    async def place_trade(self, symbol, direction, volume, stop_loss, take_profit, idempotency_key=None):
        """Submit exactly one order request. Never retry this POST automatically."""
        symbol = canonical_broker_symbol(symbol)
        direction = str(direction).upper().strip()
        if symbol is None or direction not in {"BUY", "SELL"}:
            return {"success": False, "message": "Invalid TickerAll symbol or side"}
        try:
            volume, stop_loss = float(volume), float(stop_loss)
            take_profit = None if take_profit is None else float(take_profit)
            values = [volume, stop_loss] + ([] if take_profit is None else [take_profit])
            if not all(math.isfinite(v) and v > 0 for v in values):
                return {"success": False, "message": "Invalid TickerAll order values"}
            payload = {
                "type": "market", "symbol": symbol, "side": direction,
                "volume": volume, "stopLoss": stop_loss,
                "comment": "EdonFXBot-demo",
            }
            if take_profit is not None:
                payload["takeProfit"] = take_profit
            # Independent final account gate at the broker adapter boundary.
            # Even callers bypassing ExecutionEngine cannot submit to a live or
            # read-only account through this development adapter.
            account = await self.get_account_info()
            if not AUTO_TRADING_ALLOWED:
                return {"success": False, "submitted": False,
                        "message": "TickerAll execution is disabled by AUTO_TRADING_ALLOWED; no order sent"}
            if (not isinstance(account, dict) or account.get("_is_demo") is not True
                    or account.get("tradeAllowed") is not True
                    or account.get("_risk_state_valid") is not True):
                return {"success": False, "submitted": False,
                        "message": "TickerAll final demo/account safety check failed; no order sent"}
            key = idempotency_key or str(uuid.uuid4())
            data = await self._request(
                "POST", f"{self._account_path()}/orders",
                json_body=payload, idempotency_key=key,
            )
# =====================================================================================================================
            # ticket = data.get("ticket")
            # if ticket is None:
            #     return {"success": False, "submitted": False,
            #             "message": "TickerAll response has no ticket; order state is unconfirmed",
            #             "response": data}
            # return {
            #     "success": True, "submitted": True, "filled": False,
            #     "ticket": ticket, "status": data.get("status", "unknown"),
            #     "symbol": data.get("symbol", symbol),
            #     "side": data.get("side", direction),
            #     "volume": data.get("volume", volume),
            #     "timestamp": data.get("timestamp"), "response": data,
            # }

                        # Normalize the broker's order identifier.
            order_id = (
                data.get("order_id")
                or data.get("orderId")
                or data.get("ticket")
            )

            if order_id is None or not str(order_id).strip():
                return {
                    "success": False,
                    "submitted": False,
                    "outcome_unknown": True,
                    "message": (
                        "TickerAll response has no order identifier; "
                        "order outcome is unconfirmed"
                    ),
                    "response": data,
                }

            return {
                "success": True,
                "submitted": True,

                # An acknowledgement is not proof of a fill.
                "filled": False,

                "order_id": str(order_id),
                "ticket": str(order_id),
                "position_id": data.get("position_id"),
                "status": data.get("status", "accepted"),
                "symbol": data.get("symbol", symbol),
                "side": data.get("side", direction),
                "volume": data.get("volume", volume),
                "timestamp": data.get("timestamp"),
                "response": data,
            }
# =================================================================================================================================
        except Exception as exc:
            # An exception after POST is an UNKNOWN outcome; caller must reconcile
            # account/order state and must not create a new idempotency key/retry.
            logger.exception("TickerAll order submission outcome may be unknown")
            return {"success": False, "submitted": None, "filled": False,
                    "outcome_unknown": True, "message": str(exc)}

# Compatibility alias for existing tests and integrations.
TickerAllService = TickerAllMarketData

# Module-level interface retained for the existing auto_trader call sites.
_broker = None

def _client():
    global _broker
    if _broker is None:
        _broker = TickerAllBroker()
    return _broker

async def get_account_info():
    return await _client().get_account_info()

async def get_positions():
    try:
        return await _client().get_positions()
    except Exception:
        logger.exception("TickerAll positions lookup failed")
        return None

async def get_symbol_risk_spec(symbol):
    return await _client().get_symbol_risk_spec(symbol)

async def get_spread(symbol):
    return await _client().get_spread(symbol)

async def place_trade(symbol, direction, volume, stop_loss, take_profit, idempotency_key=None):
    return await _client().place_trade(symbol, direction, volume, stop_loss, take_profit, idempotency_key)

async def close_market_data():
    if _broker is not None:
        await _broker.market_data.close()
