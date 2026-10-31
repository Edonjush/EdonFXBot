# handlers/error_handlers.py

from utils.logger import logger

async def error(update, context):

    logger.warning(
        'Update "%s" caused error "%s"',
        update,
        context.error
    )