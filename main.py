# ==============================
# ForexNezoraBot - MAIN ENTRY POINT
# ==============================

from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

from config import settings

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

import logging

from config.settings import TOKEN

from auth.auth_manager import AuthManager

from handlers.commands import (
    welcome,
    help_command,
    status_command,
    unknown_command,
    cancel
)

from handlers.signal_handler import (
    signal_command
)

from handlers.trade_handlers import (
    trade_start,
    receive_symbol,
    receive_balance,
    receive_risk,
    receive_direction,
    receive_stoploss,
    cancel_trade
)

from handlers.passcode_handler import (
    handle_passcode_message
)

from handlers.menu_handlers import (
    menu_command,
    menu_callback
)

from handlers.error_handlers import error

from states.conversation_states import (
    TRADE,
    CALCULATE,
    DECISION,
    DIRECTION,
    STOPLOSS
)


logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Reduce noisy logs
logging.getLogger(
    "httpx"
).setLevel(logging.WARNING)

logging.getLogger(
    "telegram"
).setLevel(logging.WARNING)

# ===============================
# BUILD APPLICATION
# ===============================

def build_application():

    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # ==============================
    # AUTH MANAGER
    # ==============================
    # FIX: previously built but never wired in -- auth.decorators relies
    # on context.bot_data["auth"] existing, and nothing ever set it.
    app.bot_data["auth"] = AuthManager()
    app.bot_data["auto_trading"] = False

    # ==============================
    # PASSCODE LISTENER
    # ==============================
    # Registered in its own group (-1) so it runs before other text
    # handlers but doesn't swallow updates it isn't meant to handle: it's
    # a no-op unless context.user_data['awaiting_passcode'] is set, and
    # groups in python-telegram-bot are processed independently (each
    # group gets a chance to handle the same update), so the /trade
    # conversation in group 0 still works normally.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_passcode_message
        ),
        group=-1
    )

    # ==============================
    # BASIC COMMANDS
    # ==============================

    app.add_handler(
        CommandHandler(
            "start",
            welcome
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status_command
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    # ==============================
    # AI SIGNAL ENGINE
    # ==============================

    app.add_handler(
        CommandHandler(
            "signal",
            signal_command
        )
    )

    # ==============================
    # CONTROL PANEL (data / training / auto-trading)
    # ==============================

    app.add_handler(
        CommandHandler(
            "menu",
            menu_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern=r"^menu:"
        )
    )

    # ==============================
    # TRADE CONVERSATION FLOW
    # ==============================

    trade_handler = ConversationHandler(

        entry_points=[

            CommandHandler(
                "trade",
                trade_start
            )

        ],

        states={

            # ==========================
            # RECEIVE SYMBOL
            # ==========================

            TRADE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    receive_symbol
                )

            ],

            # ==========================
            # RECEIVE ACCOUNT BALANCE
            # ==========================

            CALCULATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    receive_balance
                )

            ],

            # ==========================
            # RECEIVE RISK %
            # ==========================

            DECISION: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    receive_risk
                )

            ],

            # ==========================
            # RECEIVE DIRECTION
            # ==========================

            DIRECTION: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    receive_direction
                )

            ],

            # ==========================
            # RECEIVE STOPLOSS
            # ==========================

            STOPLOSS: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    receive_stoploss
                )

            ]
        },

        # ============================
        # FALLBACKS
        # ============================

        fallbacks=[

            CommandHandler(
                "cancel",
                cancel_trade
            )

        ],

        # ============================
        # CONVERSATION SETTINGS
        # ============================

        allow_reentry=True,

        per_chat=True,

        per_user=True,

        per_message=False

    )

    # ==============================
    # REGISTER CONVERSATION HANDLER
    # ==============================

    app.add_handler(trade_handler)

    # ==============================
    # UNKNOWN COMMAND HANDLER
    # ==============================

    app.add_handler(

        MessageHandler(
            filters.COMMAND,
            unknown_command
        )

    )

    # ==============================
    # ERROR HANDLER
    # ==============================

    app.add_error_handler(error)

    return app

# ===============================
# MAIN FUNCTION
# ===============================

def main():

    logger.info(
        "================================"
    )

    logger.info(
        "Starting ForexNezoraBot AI Engine..."
    )

    logger.info(
        "ML Signal System: ACTIVE"
    )

    logger.info(
        "Multi-Timeframe Engine: ACTIVE"
    )

    logger.info(
        "Risk Management System: ACTIVE"
    )

    logger.info(
        "Execution Filters: ACTIVE"
    )

    logger.info(
        "Auth System: ACTIVE"
    )

    logger.info(
        "================================"
    )

    app = build_application()

    # ==============================
    # START POLLING
    # ==============================

    app.run_polling(

        drop_pending_updates=True,

        allowed_updates=None,

        close_loop=False,

        stop_signals=None

    )

# ===============================
# START BOT
# ===============================
import asyncio

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main()
