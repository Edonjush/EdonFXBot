# tasks/signal_tasks.py

import asyncio
from core.celery_app import celery

from services.twelvedata_service import fetch_market_data
from services.signal_engine import generate_signal


@celery.task(name="tasks.generate_signal_task")
def generate_signal_task(symbol: str):

    m5 = fetch_market_data(symbol, "5min")
    h1 = fetch_market_data(symbol, "1h")

    if m5 is None or h1 is None:
        return {"status": "failed", "reason": "data fetch failed"}

    signal = generate_signal(m5, h1, symbol)

    return signal