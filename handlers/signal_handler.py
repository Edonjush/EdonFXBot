# handlers/signal_handler.py

from telegram import Update
from telegram.ext import ContextTypes

import traceback
import asyncio

from services.twelvedata_service import fetch_market_data
from services.signal_engine import generate_signal
from services import tickerall_service
from services.tickerall_service import canonical_broker_symbol
from auth.decorators import requires_auth


@requires_auth
async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        if len(context.args) == 0:
            await update.message.reply_text("Usage:\n/signal BASE/QUOTE\nexample: /signal EUR/USD")
            return

        symbol = context.args[0]

        await update.message.reply_text(f"📡 Analyzing {symbol}...")

        # ============================
        # MULTI-TIMEFRAME DATA FETCH
        # ============================
        m5, h1 = await asyncio.gather(
            asyncio.to_thread(fetch_market_data, symbol, "5min"),
            asyncio.to_thread(fetch_market_data, symbol, "1h")
        )

        if m5 is None or h1 is None:
            await update.message.reply_text("❌ Failed to fetch market data.")
            return

        # Obtain the live broker spread; never substitute a hard-coded guess.
        broker_symbol = canonical_broker_symbol(symbol)
        if broker_symbol is None:
            await update.message.reply_text(
                "Stage 1 supports EUR/USD only."
            )
            return

        spread = await tickerall_service.get_spread(broker_symbol)
        if spread is None:
            await update.message.reply_text("❌ Live broker spread unavailable; signal blocked.")
            return

        # ============================
        # SIGNAL GENERATION (ML PIPELINE)
        # ============================
        try:
            signal = await asyncio.wait_for(
                asyncio.to_thread(generate_signal, m5, h1, broker_symbol, spread),
                timeout=20
            )

        except asyncio.TimeoutError:
            await update.message.reply_text("⏱ Signal timed out.")
            return

        # =====================================================
        # VALIDATION: NEW STANDARD FORMAT
        # =====================================================
        if not isinstance(signal, dict):
            await update.message.reply_text("❌ Invalid signal format returned.")
            return

        if signal.get("status") != "signal":
            await update.message.reply_text(
                f"❌ Signal Blocked\n\n"
                f"Reason: {signal.get('reason', 'Unknown')}"
            )
            return

        # =====================================================
        # SAFE EXTRACTION (ML-AWARE)
        # =====================================================
        entry = signal.get("entry")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        ml_conf = signal.get("ml_confidence")
        regime = signal.get("market_regime")
        model_signal = signal.get("signal")

        # ============================
        # MESSAGE BUILD (UPDATED FOR ML SYSTEM)
        #============================
        message = (
            f"📊 ForexNezora__AI__Bot SIGNAL ALERT\n\n"
            f"Pair: {symbol}\n"
            f"Type: {model_signal}\n\n"
            f"Entry: {entry if entry is not None else 'N/A'}\n"
            f"Stop Loss: {sl if sl is not None else 'N/A'}\n"
            f"Take Profit: {tp if tp is not None else 'N/A'}\n\n"
            f"ML Confidence: {ml_conf if ml_conf is not None else 'N/A'}%\n"
            f"Market Regime: {regime or 'UNKNOWN'}"
        )

        await update.message.reply_text(message)

    except Exception as e:
        print("\n===== FULL ERROR TRACEBACK =====")
        traceback.print_exc()

        await update.message.reply_text(
            f"Signal Engine Error:\n{e}"
        )
