# handlers/passcode_handler.py

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from config.security import BOT_PASSCODE, MAX_LOGIN_ATTEMPTS, LOCK_DURATION
from config.settings import OWNER_TELEGRAM_ID

logger = logging.getLogger(__name__)


def _format_remaining(locked_until_iso: str) -> str:
    try:
        unlock = datetime.fromisoformat(locked_until_iso)
        remaining = unlock - datetime.utcnow()
        minutes = max(1, int(remaining.total_seconds() // 60) + 1)
        return f"{minutes} minute(s)"
    except Exception:
        return "a few minutes"


async def start_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Call this at the top of /start. Returns True if the user is already
    verified and the caller should proceed to show the normal welcome
    menu. Returns False if this function already handled the update
    (passcode prompt or lockout notice) and the caller should stop.
    """

    auth = context.bot_data["auth"]
    user_id = update.effective_user.id

    if auth.is_verified(user_id):
        auth.update_login(user_id)
        return True

    if auth.is_locked(user_id):
        user = auth.get_user(user_id)
        remaining = (
            _format_remaining(user.locked_until)
            if user and user.locked_until
            else "a few minutes"
        )
        await update.effective_message.reply_text(
            f"🔒 Too many failed attempts.\n\nTry again in {remaining}."
        )
        return False

    context.user_data["awaiting_passcode"] = True

    await update.effective_message.reply_text(
        "🔐 Welcome to ForexNezora__AI__Bot.\n\n"
        "This bot is passcode-protected. Please enter your access "
        "passcode to continue."
    )

    return False


async def handle_passcode_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Registered in main.py in a separate handler group (group=-1) so it
    runs before other text handlers but doesn't swallow updates it isn't
    meant to handle. It only acts when the user is mid passcode-entry
    (context.user_data['awaiting_passcode'] is True); otherwise it's a
    no-op and processing continues normally (e.g. to the /trade
    conversation).
    """

    if not context.user_data.get("awaiting_passcode"):
        return

    auth = context.bot_data["auth"]
    telegram_user = update.effective_user
    user_id = telegram_user.id

    if not auth.exists(user_id):
        auth.register(telegram_user, verified=False)

    if auth.is_locked(user_id):
        await update.effective_message.reply_text(
            "🔒 Account temporarily locked. Please try again later."
        )
        context.user_data["awaiting_passcode"] = False
        return

    entered = (update.effective_message.text or "").strip()

    if entered == BOT_PASSCODE:

        auth.verify_user(user_id)

        if OWNER_TELEGRAM_ID and user_id == OWNER_TELEGRAM_ID:
            auth.set_role(user_id, "owner")

        context.user_data["awaiting_passcode"] = False

        await update.effective_message.reply_text(
            "✅ Access granted. Welcome to ForexNezora__AI__Bot!\n\n"
            "Send /start to see the main menu."
        )

        logger.info(f"User {user_id} authenticated successfully.")

    else:

        auth.record_failed_attempt(user_id)

        if auth.is_locked(user_id):

            minutes = int(LOCK_DURATION.total_seconds() // 60)

            await update.effective_message.reply_text(
                f"❌ Incorrect passcode. Too many failed attempts — "
                f"locked out for {minutes} minutes."
            )

            context.user_data["awaiting_passcode"] = False

        else:

            user = auth.get_user(user_id)
            remaining = MAX_LOGIN_ATTEMPTS - (user.attempts if user else 0)

            await update.effective_message.reply_text(
                f"❌ Incorrect passcode. {remaining} attempt(s) remaining."
            )