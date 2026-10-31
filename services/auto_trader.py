"""Explicitly opt-in, demo-only scheduled trading with persistent deduplication."""
import json
import logging
import os
import asyncio
from pathlib import Path

from services.twelvedata_service import fetch_market_data
from services.signal_engine import generate_signal
from services.execution_engine import ExecutionEngine
from services import tickerall_service
from config.settings import (RISK_FACTOR, AUTO_TRADING_ALLOWED, DEMO_ONLY,
                             BROKER_SYMBOL_SUFFIX, MAX_RISK_PER_TRADE_PERCENT, DATA_DIR)

logger = logging.getLogger(__name__)
WATCHLIST = [("EUR/USD", "EURUSDm")]
engine = ExecutionEngine(tickerall_service)
_CYCLE_LOCK = asyncio.Lock()
_STATE_FILE = DATA_DIR / "auto_trade_dedup.json"


def _load_seen():
    if not _STATE_FILE.exists():
        return []
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        return list(dict.fromkeys(data.get("keys", [])))
    except (OSError, ValueError):
        raise RuntimeError("Auto-trade deduplication state is unreadable; refusing to trade")


def _save_seen(keys):
    # Retain a bounded recent history to prevent unbounded state growth.
    recent = list(dict.fromkeys(keys))[-2000:]
    temp = _STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"keys": recent}, indent=2), encoding="utf-8")
    os.replace(temp, _STATE_FILE)


async def _auto_trade_job_impl(context):
    bot_data = context.bot_data
    if not bot_data.get("auto_trading"):
        return
    if not AUTO_TRADING_ALLOWED:
        logger.warning("Auto-trading request ignored: AUTO_TRADING_ALLOWED is false")
        return
    if not DEMO_ONLY:
        logger.error("Automated trading blocked: DEMO_ONLY must remain enabled")
        return
    owner_chat_id = bot_data.get("owner_chat_id")
    if not owner_chat_id:
        logger.error("Auto-trade cycle blocked: owner notification chat is not configured")
        return
    account = await tickerall_service.get_account_info()
    if not isinstance(account, dict) or account.get("_is_demo") is not True:
        logger.error("Auto-trade cycle blocked: demo account could not be verified")
        return
    if account.get("_risk_state_valid") is not True:
        logger.error("Auto-trade cycle blocked: account risk state is unavailable")
        return
    try:
        seen = _load_seen()
    except RuntimeError:
        logger.exception("Auto-trade cycle blocked by deduplication state")
        return
    balance = float(account.get("balance", 0) or 0)
    if balance <= 0:
        logger.warning("Auto-trade cycle skipped: invalid balance")
        return
    risk_percent = min(float(RISK_FACTOR) * 100.0, MAX_RISK_PER_TRADE_PERCENT)
    for td_symbol, broker_symbol in WATCHLIST:
        try:
            m5 = fetch_market_data(td_symbol, "5min")
            h1 = fetch_market_data(td_symbol, "1h")
            if m5 is None or h1 is None:
                continue
            spread = await tickerall_service.get_spread(broker_symbol)
            if spread is None:
                continue
            result = generate_signal(m5, h1, broker_symbol, spread=spread)
            if result.get("status") != "signal":
                continue
            dedup_key = "|".join((broker_symbol, result["signal"], str(result.get("signal_bar_time", ""))))
            if dedup_key in seen:
                logger.info("Duplicate signal skipped: %s", dedup_key)
                continue
            # Record before submitting: a timeout can occur after broker acceptance.
            seen.append(dedup_key)
            _save_seen(seen)
            execution = await engine.execute_trade(
                symbol=broker_symbol, signal=result["signal"], entry=result["entry"],
                sl=result["stop_loss"], tp=result["take_profit"], balance=balance,
                risk_percent=risk_percent, confidence=result.get("ml_confidence", 0), spread=spread,
            )
            if execution.get("success"):
                message = ("DEMO order submitted — verify broker fill\n\n"
                           f"{result['signal']} {broker_symbol}\nEntry: {execution['entry']}\n"
                           f"SL: {result['stop_loss']}  TP: {result['take_profit']}\n"
                           f"Volume: {execution['volume']}\nTicket: {execution['ticket']}\n"
                           f"Broker status: {execution['status']}\nConfidence: {result['ml_confidence']}%")
            else:
                message = f"Auto-trade skipped for {broker_symbol}: {execution.get('message')}"
            await context.bot.send_message(owner_chat_id, message)
        except Exception:
            logger.exception("Auto-trade cycle failed for %s", broker_symbol)


async def auto_trade_job(context):
    """Prevent overlapping scheduled cycles from racing duplicate checks."""
    if _CYCLE_LOCK.locked():
        logger.warning("Previous auto-trade cycle is still running; skipping overlap")
        return
    async with _CYCLE_LOCK:
        await _auto_trade_job_impl(context)
