# auth/decorators.py

from functools import wraps


def requires_auth(func):

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):

        auth = context.bot_data["auth"]

        if not auth.is_verified(update.effective_user.id):

            await update.message.reply_text(
                "🔒 Please authenticate first using /start."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_required(func):

    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):

        auth = context.bot_data["auth"]

        if not auth.is_admin(update.effective_user.id):

            await update.message.reply_text(
                "⛔ Administrator access required."
            )
            return

        return await func(update, context, *args, **kwargs)

    return wrapper