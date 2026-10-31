# handlers/menu_handlers.py

"""
The /menu control panel: three buttons -- Download Data, Train Model,
and toggle Auto-Trading. Restricted to admin/owner (see auth.decorators
.admin_required) since training and live auto-trading are higher-stakes
than just checking a signal.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from auth.decorators import admin_required
from ml.download_data import download_historical_data
from services.model_retrainer import ModelRetrainer
from services.auto_trader import auto_trade_job, WATCHLIST
from config.settings import AUTO_TRADING_ALLOWED, DEMO_ONLY

logger = logging.getLogger(__name__)

AUTO_TRADE_JOB_NAME = "auto_trade_job"
AUTO_TRADE_INTERVAL_SECONDS = 300  # 5 minutes


def _watchlist_label() -> str:
    return ", ".join(broker_symbol for _, broker_symbol in WATCHLIST)


def _menu_keyboard(auto_trading_on: bool) -> InlineKeyboardMarkup:

    toggle_label = (
        "🛑 Disable Auto-Trading" if auto_trading_on else "▶️ Enable Auto-Trading"
    )

    buttons = [
        [InlineKeyboardButton("📥 Download Data", callback_data="menu:download_data")],
        [InlineKeyboardButton("🧠 Train Model", callback_data="menu:train_model")],
        [InlineKeyboardButton(toggle_label, callback_data="menu:toggle_auto_trade")],
    ]

    return InlineKeyboardMarkup(buttons)


@admin_required
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    auto_trading_on = bool(context.bot_data.get("auto_trading"))

    await update.effective_message.reply_text(
        "⚙️ ForexNezora__AI__Bot Control Panel\n\n"
        f"Auto-Trading: {'🟢 ON' if auto_trading_on else ('🔴 OFF (locked)' if not AUTO_TRADING_ALLOWED else '🔴 OFF')}\n"
        f"Execution mode: {'DEMO ONLY' if DEMO_ONLY else 'BLOCKED'}\n"
        f"Watchlist: {_watchlist_label()}",
        reply_markup=_menu_keyboard(auto_trading_on)
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    # NOTE: can't reuse the admin_required/requires_auth decorators here --
    # they call update.message.reply_text(), but update.message is None on
    # a callback-query update (it's update.callback_query.message instead).
    auth = context.bot_data["auth"]
    user_id = query.from_user.id

    if not auth.is_admin(user_id):
        await query.edit_message_text("⛔ Administrator access required.")
        return

    action = query.data.split(":", 1)[1]

    if action == "download_data":

        await query.edit_message_text(
            "📥 Downloading historical data... this can take a moment."
        )

        try:
            rows = await asyncio.to_thread(download_historical_data)
            await query.message.reply_text(f"✅ Download complete: {rows} rows saved.")
        except Exception as e:
            logger.exception("Download data failed")
            await query.message.reply_text(f"❌ Download failed: {e}")

    elif action == "train_model":

        await query.edit_message_text(
            "🧠 Training model... this can take a few minutes."
        )

        try:
            result = await asyncio.to_thread(ModelRetrainer().retrain)

            if result.get("success"):
                await query.message.reply_text(
                    "✅ Candidate training complete.\n"
                    f"Out-of-sample balanced accuracy: {result.get('out_of_sample_balanced_accuracy')}\n"
                    f"Candidate: {result.get('candidate_dir')}\n"
                    "Production model unchanged; deployment is NOT approved."
                )
            else:
                await query.message.reply_text(
                    f"❌ Training failed: {result.get('message')}"
                )
        except Exception as e:
            logger.exception("Model training failed")
            await query.message.reply_text(f"❌ Training failed: {e}")

    elif action == "toggle_auto_trade":

        if not AUTO_TRADING_ALLOWED or not DEMO_ONLY:
            context.bot_data["auto_trading"] = False
            for job in context.job_queue.get_jobs_by_name(AUTO_TRADE_JOB_NAME):
                job.schedule_removal()
            await query.edit_message_text(
                "🔒 Automated trading is locked by configuration.\n"
                "It remains disabled until AUTO_TRADING_ALLOWED is explicitly enabled.\n"
                "This release is hard-locked to demo accounts."
            )
            return

        enabled = not bool(context.bot_data.get("auto_trading"))

        context.bot_data["auto_trading"] = enabled
        context.bot_data["owner_chat_id"] = query.message.chat_id

        existing_jobs = context.job_queue.get_jobs_by_name(AUTO_TRADE_JOB_NAME)

        if enabled:

            if not existing_jobs:
                context.job_queue.run_repeating(
                    auto_trade_job,
                    interval=AUTO_TRADE_INTERVAL_SECONDS,
                    first=10,
                    name=AUTO_TRADE_JOB_NAME
                )

            await query.message.reply_text(
                f"🟢 Auto-trading ENABLED.\n"
                f"Watching: {_watchlist_label()}\n"
                f"Checking every {AUTO_TRADE_INTERVAL_SECONDS // 60} minutes."
            )

        else:

            for job in existing_jobs:
                job.schedule_removal()

            await query.message.reply_text("🔴 Auto-trading DISABLED.")

        await query.edit_message_text(
            "⚙️ ForexNezora__AI__Bot Control Panel\n\n"
            f"Auto-Trading: {'🟢 ON' if enabled else '🔴 OFF'}\n"
            f"Watchlist: {_watchlist_label()}",
            reply_markup=_menu_keyboard(enabled)
        )
