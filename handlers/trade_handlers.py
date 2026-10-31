# handlers/trade_handlers.py

import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler
)

from states.conversation_states import (
    TRADE,
    CALCULATE,
    DECISION,
    DIRECTION,
    STOPLOSS
)


logger = logging.getLogger(__name__)


# =========================
# START TRADE
# =========================
async def trade_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    # NOTE: this is a ConversationHandler entry point, so it must return an
    # int state (or ConversationHandler.END) -- can't use the @requires_auth
    # decorator here, since an unauthorized call returning None would leave
    # the conversation in an undefined state for this user.
    auth = context.bot_data.get("auth")

    if auth and not auth.is_verified(update.effective_user.id):
        await update.effective_message.reply_text(
            "🔒 Please authenticate first using /start."
        )
        return ConversationHandler.END

    context.user_data["trade"] = {}

    await update.effective_message.reply_text(
        "📊 Enter trading pair.\n\n"
        "Example:\n"
        "EURUSD\n"
        "XAUUSD\n"
        "GBPJPY"
    )

    return TRADE


# =========================
# RECEIVE SYMBOL
# =========================
async def receive_symbol(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    symbol = update.effective_message.text.upper().strip()

    context.user_data["trade"]["symbol"] = symbol

    await update.effective_message.reply_text(
        "💰 Enter account balance:"
    )

    return CALCULATE


# =========================
# RECEIVE BALANCE
# =========================
async def receive_balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    try:

        balance = float(
            update.effective_message.text
        )

        context.user_data["trade"]["balance"] = balance

        await update.effective_message.reply_text(
            "⚠️ Enter risk percentage.\n\n"
            "Example: 2"
        )

        return DECISION

    except ValueError:

        await update.effective_message.reply_text(
            "❌ Invalid balance."
        )

        return CALCULATE


# =========================
# RECEIVE RISK
# =========================
async def receive_risk(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    try:

        risk = float(
            update.effective_message.text
        )

        context.user_data["trade"]["risk"] = risk

        await update.effective_message.reply_text(
            "📈 Enter direction:\n\n"
            "BUY or SELL"
        )

        return DIRECTION

    except ValueError:

        await update.effective_message.reply_text(
            "❌ Invalid risk percentage."
        )

        return DECISION


# =========================
# RECEIVE DIRECTION
# =========================
async def receive_direction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    direction = (
        update.effective_message.text.upper().strip()
    )

    if direction not in ["BUY", "SELL"]:

        await update.effective_message.reply_text(
            "❌ Enter BUY or SELL only."
        )

        return DIRECTION

    context.user_data["trade"]["direction"] = direction

    await update.effective_message.reply_text(
        "🛑 Enter Stop Loss in pips:"
    )

    return STOPLOSS


# =========================
# RECEIVE STOP LOSS
# =========================
async def receive_stoploss(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    try:

        sl_pips = float(
            update.effective_message.text
        )

        trade = context.user_data["trade"]

        trade["sl_pips"] = sl_pips

        balance = trade["balance"]
        risk_percent = trade["risk"]

        risk_amount = (
            balance * risk_percent / 100
        )

        # Basic forex lot formula
        # Assumes $10/pip per lot
        if sl_pips <= 0 or balance <= 0 or risk_percent <= 0:
            await update.effective_message.reply_text(
                "❌ Balance, risk and stop-loss distance must all be positive."
            )
            return STOPLOSS

        # Temporary display estimate only. It is NOT used as permission to
        # execute: execution must be migrated to broker-spec sizing next.
        lot_size = round(risk_amount / (sl_pips * 10), 2)
        if lot_size < 0.01:
            await update.effective_message.reply_text(
                "❌ Requested risk is too small for the estimated minimum lot. "
                "No trade was submitted."
            )
            return ConversationHandler.END

        trade["lot_size"] = lot_size

        result = (
            "📈 Trade Summary\n\n"
            f"Pair: {trade['symbol']}\n"
            f"Direction: {trade['direction']}\n"
            f"Balance: ${balance:.2f}\n"
            f"Risk: {risk_percent}%\n"
            f"SL: {sl_pips} pips\n"
            f"Lot Size: {lot_size}"
        )

        await update.effective_message.reply_text(
            result
        )

        # =========================
        # EXECUTE TRADE
        # =========================

        # Direct manual execution is intentionally disabled until this path
        # uses the same broker-spec risk sizing as ExecutionEngine. The old
        # fixed $10/pip estimate is not safe for all symbols/accounts.
        await update.effective_message.reply_text(
            "⛔ Manual order submission is temporarily disabled while broker-spec "
            "risk sizing is being integrated. No order was sent."
        )

        return ConversationHandler.END

    except ValueError:

        await update.effective_message.reply_text(
            "❌ Invalid Stop Loss."
        )

        return STOPLOSS


# =========================
# CANCEL TRADE
# =========================
async def cancel_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:

    context.user_data.clear()

    await update.effective_message.reply_text(
        "❌ Trade cancelled."
    )

    return ConversationHandler.END
