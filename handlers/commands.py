# handlers/commands.py

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import platform
import datetime

from handlers.passcode_handler import start_auth

 #================================
# START COMMAND
# ===============================

async def welcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # FIX: gate on the passcode before showing the welcome menu. If the
    # user isn't verified yet, start_auth() sends either a passcode prompt
    # or a lockout notice and returns False -- stop here in that case.
    authorized = await start_auth(update, context)

    if not authorized:
        return

    user = update.effective_user.first_name

    message = (

        f"🤖 Welcome {user}!\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀ForexNezora__AI__Bot \n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"Advanced AI-powered Forex Trading Bot\n\n"

        f"✅ Machine Learning Signals\n"
        f"✅ Multi-Timeframe Analysis\n"
        f"✅ Breakout Detection\n"
        f"✅ Prop-Firm Risk Protection\n"
        f"✅ Dynamic SL/TP Engine\n"
        f"✅ Volatility Filtering\n"
        f"✅ AI Confidence Scoring\n"
        f"✅ Smart Risk Management\n"
        f"✅ MetaAPI Trade Execution\n\n"

        f"📌 Available Commands:\n\n"

        f"/signal EUR/USD || Generate AI trade signal\n\n"

        f"/trade || Start manual trade flow\n\n"

        f"/menu || Control panel (data, training, auto-trading)\n\n"

        f"/status || View AI engine status\n\n"

        f"/help || Full command guide\n\n"

        f"/cancel || Cancel current operation\n\n"

        # f"/EON_AI_OS || Chat with 'Eon' AI model (Coming Soon)\n"
    )

    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML
    )

# ===============================
# HELP COMMAND
# ===============================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = (

        f"📘 <b>ForexNezora__AI__Bot HELP</b>\n\n"

        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ SIGNAL COMMANDS  \n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"

        f"<b>/signal EUR/USD</b>\n"
        f"Generate AI-powered signal using:\n\n"

        f"• ML probability engine\n"
        f"• Multi-timeframe confirmation\n"
        f"• ATR volatility filtering\n"
        f"• Breakout confirmation\n"
        f"• Prop-firm safe filters\n"
        f"• Market regime detection\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"💰 TRADE COMMANDS\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"<b>/trade</b>\n"
        f"Start manual trade workflow:\n\n"

        f"1. Enter pair\n"
        f"2. Enter balance\n"
        f"3. Enter risk %\n"
        f"4. Select direction\n"
        f"5. Enter stoploss\n\n"

        f"Bot calculates:\n"
        f"• Position size\n"
        f"• Risk exposure\n"
        f"• Safe lot size\n\n"

        # f"━━━━━━━━━━━━━━━\n"
        # f"⚙️ CONTROL PANEL (admin/owner only)\n"
        # f"━━━━━━━━━━━━━━━\n\n"

        # f"<b>/menu</b>\n"
        # f"• 📥 Download historical data\n"
        # f"• 🧠 Retrain the ML model\n"
        # f"• ▶️ Toggle auto-trading from live signals\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"🛡 RISK PROTECTION\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"Bot automatically blocks:\n\n"

        f"❌ High spread trades\n"
        f"❌ High volatility trades\n"
        f"❌ Weak ML confidence setups\n"
        f"❌ Trend mismatch entries\n"
        f"❌ Unsafe market conditions\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"📊 AI ENGINE FEATURES\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"✅ XGBoost ML Model\n"
        f"✅ Walk-forward validated\n"
        f"✅ Probability scoring\n"
        f"✅ Smart execution filtering\n"
        f"✅ Adaptive market regime logic\n"
        f"✅ Execution optimization\n"
        f"✅ Slippage protection\n\n"


        f"━━━━━━━━━━━━━━━\n"
        f"⚠ DISCLAIMER\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"Trading carries financial risk.\n"
        f"No system guarantees profits.\n"
        f"Always use proper risk management.\n"
        f"Eon AI is still under development....coming soon!!."
    )

    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML
    )

# ===============================
# STATUS COMMAND
# ===============================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    current_time = datetime.datetime.now()

    auto_trading_on = bool(context.bot_data.get("auto_trading"))

    message = (

        f"🟢 <b>ForexNezora__AI__Bot STATUS</b>\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"🤖 SYSTEM STATUS\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"AI Engine: ✅ ONLINE\n"
        f"ML Predictor: ✅ ACTIVE\n"
        f"Signal Engine: ✅ ACTIVE\n"
        f"Risk Engine: ✅ ACTIVE\n"
        f"Execution Filters: ✅ ACTIVE\n"
        f"TickerAll: ✅ CONNECTED\n"
        f"Auto-Trading: {'🟢 ON' if auto_trading_on else '🔴 OFF'}\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"📊 ANALYSIS SYSTEMS\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"✅ Multi-Timeframe Analysis\n"
        f"✅ Breakout Detection\n"
        f"✅ ATR Volatility Filter\n"
        f"✅ Market Regime Detection\n"
        f"✅ AI Probability Scoring\n"
        f"✅ Smart Risk Control\n\n"

        f"━━━━━━━━━━━━━━━\n"
        f"⚡ EXECUTION SYSTEMS\n"
        f"━━━━━━━━━━━━━━━\n\n"

        f"✅ Spread Protection\n"
        f"✅ Slippage Monitoring\n"
        f"✅ Smart Execution Engine\n"
        f"✅ Prop-Firm Safe Filters\n\n"
    )

    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML
    )

# ===============================
# CANCEL COMMAND
# ===============================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "❌ Operation cancelled.\n\n"
        "All pending workflows stopped."

    )

# ===============================
# UNKNOWN COMMAND HANDLER
# ===============================

async def unknown_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "❌ Unknown command.\n\n"

        "Use:\n"
        "/help → View command guide\n"
        "/signal EUR/USD → AI signal\n"
        "/trade → Manual trade flow\n"
        "/menu → Control panel"

    )
