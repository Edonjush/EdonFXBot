"""Fail-closed TickerAll demo execution with fresh-quote and risk gates."""
import logging
import math
import time
import uuid

from config.settings import (DEMO_ONLY, AUTO_TRADING_ALLOWED, MIN_ML_CONFIDENCE, MAX_DAILY_DRAWDOWN,
                             MAX_TOTAL_DRAWDOWN, MAX_OPEN_TRADES,
                             MAX_RISK_PER_TRADE_PERCENT)
from services.risk_manager import RiskManager
from services.spread_guard import SpreadGuard

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, broker_service):
        self.broker = broker_service
        self.spread_guard = SpreadGuard()
        self.risk_manager = RiskManager(
            max_daily_drawdown=MAX_DAILY_DRAWDOWN,
            max_total_drawdown=MAX_TOTAL_DRAWDOWN,
            max_open_trades=MAX_OPEN_TRADES,
        )

    async def execute_trade(self, symbol, signal, entry, sl, tp, balance,
                            risk_percent, confidence, spread):
        try:
            if not AUTO_TRADING_ALLOWED:
                return {"success": False, "message": "Trade execution disabled by AUTO_TRADING_ALLOWED"}
            symbol_input = str(symbol).strip().replace("/", "").casefold()
            symbol = "EURUSDm" if symbol_input in {"eurusd", "eurusdm"} else None
            signal = str(signal).upper().strip()
            if symbol is None or signal not in {"BUY", "SELL"}:
                return {"success": False, "message": "Invalid symbol or trade direction"}
            try:
                entry, sl = float(entry), float(sl)
                balance, risk_percent, confidence, spread = map(float, (balance, risk_percent, confidence, spread))
                tp = None if tp is None else float(tp)
            except (TypeError, ValueError, OverflowError):
                return {"success": False, "message": "Invalid numeric trade parameters"}
            numbers = [entry, sl, balance, risk_percent, confidence, spread] + ([] if tp is None else [tp])
            if not all(math.isfinite(x) for x in numbers):
                return {"success": False, "message": "Non-finite trade parameter"}
            if entry <= 0 or sl <= 0 or balance <= 0 or not 0 < risk_percent <= MAX_RISK_PER_TRADE_PERCENT or spread < 0:
                return {"success": False, "message": "Trade parameters exceed configured risk limits"}
            if not MIN_ML_CONFIDENCE <= confidence <= 100:
                return {"success": False, "message": f"ML confidence below required {MIN_ML_CONFIDENCE:.1f}%"}
            if signal == "BUY" and sl >= entry:
                return {"success": False, "message": "BUY stop-loss must be below entry"}
            if signal == "SELL" and sl <= entry:
                return {"success": False, "message": "SELL stop-loss must be above entry"}
            if tp is not None and ((signal == "BUY" and tp <= entry) or (signal == "SELL" and tp >= entry)):
                return {"success": False, "message": "Take-profit is on the wrong side of entry"}
            if not self.spread_guard.safe(symbol, spread):
                return {"success": False, "message": "Signal-time spread too high"}

            account_method = getattr(self.broker, "get_account_info", None)
            positions_method = getattr(self.broker, "get_positions", None)
            if not callable(account_method) or not callable(positions_method):
                return {"success": False, "message": "TickerAll account/position services unavailable"}
            account = await account_method()
            if not isinstance(account, dict):
                return {"success": False, "message": "Could not verify TickerAll account"}
            if DEMO_ONLY and account.get("_is_demo") is not True:
                return {"success": False, "message": "Demo-only policy: TickerAll demo account not positively verified"}
            if account.get("_risk_state_valid") is not True:
                return {"success": False, "message": "Account drawdown state unavailable; execution blocked"}
            if account.get("tradeAllowed") is not True:
                return {"success": False, "message": "TickerAll account is offline or read-only"}
            try:
                fresh_balance = float(account.get("balance", 0))
            except (TypeError, ValueError, OverflowError):
                fresh_balance = 0.0
            if not math.isfinite(fresh_balance) or fresh_balance <= 0:
                return {"success": False, "message": "Fresh TickerAll balance unavailable"}
            balance = fresh_balance
            positions = await positions_method()
            if not isinstance(positions, list):
                return {"success": False, "message": "TickerAll open positions could not be verified"}
            if any(isinstance(p, dict) and str(p.get("symbol", "")).strip().casefold() == symbol.casefold() for p in positions):
                return {"success": False, "message": f"An open position already exists for {symbol}"}
            allowed, reason = self.risk_manager.trade_allowed(
                account.get("total_drawdown_pct"), account.get("daily_drawdown_pct"), len(positions)
            )
            if not allowed:
                return {"success": False, "message": reason}

            spec_method = getattr(self.broker, "get_symbol_risk_spec", None)
            if not callable(spec_method):
                return {"success": False, "message": "TickerAll symbol-specification service unavailable"}
            spec = await spec_method(symbol)
            if not isinstance(spec, dict):
                return {"success": False, "message": "TickerAll symbol specification or fresh quote unavailable"}
            bid, ask = float(spec["currentBid"]), float(spec["currentAsk"])
            if not all(math.isfinite(x) and x > 0 for x in (bid, ask)) or ask < bid:
                return {"success": False, "message": "TickerAll fresh bid/ask quote is invalid"}
            fresh_spread = ask - bid if "XAU" in symbol else (ask - bid) / 0.0001
            if not self.spread_guard.safe(symbol, fresh_spread):
                return {"success": False, "message": "Fresh TickerAll spread exceeds policy"}
            actual_entry = ask if signal == "BUY" else bid
            if signal == "BUY" and sl >= actual_entry:
                return {"success": False, "message": "BUY stop-loss must be below current ask"}
            if signal == "SELL" and sl <= actual_entry:
                return {"success": False, "message": "SELL stop-loss must be above current bid"}
            if tp is not None and ((signal == "BUY" and tp <= actual_entry) or (signal == "SELL" and tp >= actual_entry)):
                return {"success": False, "message": "Take-profit is on the wrong side of current market"}
            volume = self.risk_manager.calculate_volume_from_spec(
                balance=balance, risk_percent=risk_percent, entry=actual_entry,
                stop_loss=sl, spec=spec,
            )
            if not isinstance(volume, (int, float)) or not math.isfinite(float(volume)) or volume <= 0:
                return {"success": False, "message": "No safe volume fits requested risk budget"}

            started = time.monotonic()
            # Stable key for this one signal submission. No automatic retries.
            key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"EdonFXBot|{symbol}|{signal}|{entry}|{sl}|{tp}"))
            result = await self.broker.place_trade(
                symbol=symbol, direction=signal, volume=volume,
                stop_loss=sl, take_profit=tp, idempotency_key=key,
            )
            latency_ms = round((time.monotonic() - started) * 1000, 2)

# ==============================================================================================================================================================================================================================================================================================================================================================
            # if not isinstance(result, dict) or result.get("success") is not True or result.get("ticket") is None:
            #     return {"success": False, "message": (result or {}).get("message", "TickerAll order outcome unconfirmed") if isinstance(result, dict) else "TickerAll returned an unstructured response", "outcome_unknown": bool(isinstance(result, dict) and result.get("outcome_unknown")), "latency_ms": latency_ms, "result": result}
            # return {
            #     "success": True, "submitted": True, "filled": result.get("filled", False),
            #     "status": result.get("status", "unknown"), "ticket": result["ticket"],
            #     "symbol": symbol, "signal": signal, "volume": volume,
            #     "entry": actual_entry, "sl": sl, "tp": tp,
            #     "latency_ms": latency_ms, "confidence": confidence, "result": result,
            # }

            # Only a structured broker response with an order identifier
            # counts as an acknowledged submission.
            
            order_id = (
                result.get("order_id")
                if isinstance(result, dict)
                else None
            )

            if (
                not isinstance(result, dict)
                or result.get("success") is not True
                or order_id is None
                or not str(order_id).strip()
            ):
                return {
                    "success": False,
                    "submitted": (
                        result.get("submitted")
                        if isinstance(result, dict)
                        else False
                    ),
                    "message": (
                        result.get(
                            "message",
                            "TickerAll order outcome unconfirmed"
                        )
                        if isinstance(result, dict)
                        else "TickerAll returned an unstructured response"
                    ),
                    "outcome_unknown": bool(
                        isinstance(result, dict)
                        and result.get("outcome_unknown")
                    ),
                    "latency_ms": latency_ms,
                    "result": result,
                }

            return {
                "success": True,
                "submitted": True,

                # Do not claim execution/fill from an order acknowledgement.
                "filled": result.get("filled") is True,

                "status": result.get("status", "unknown"),
                "order_id": str(order_id),
                "ticket": result.get("ticket", str(order_id)),
                "position_id": result.get("position_id"),

                "symbol": symbol,
                "signal": signal,
                "volume": volume,
                "entry": actual_entry,
                "sl": sl,
                "tp": tp,
                "latency_ms": latency_ms,
                "confidence": confidence,
                "result": result,
            }
# ===============================================================================================================================================================================================================================================================================================================================================================
        except Exception as exc:
            logger.exception("TickerAll execution engine error")
            return {"success": False, "message": f"Execution error: {exc}"}
