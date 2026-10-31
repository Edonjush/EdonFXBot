import asyncio
import time
from datetime import datetime, timezone, timedelta

from services.risk_manager import RiskManager
from services.tickerall_service import TickerAllMarketData
from services.execution_engine import ExecutionEngine

from unittest.mock import patch

def test_fx_spread_normalization():
    raw_spread = 1.11345 - 1.11342
    spread_pips = round(raw_spread / 0.0001, 4)
    assert spread_pips == 0.3


def test_gold_spread_normalization():
    raw_spread = 4056.85 - 4056.72
    assert round(raw_spread, 4) == 0.13


def test_risk_sizing_uses_broker_spec():
    rm = RiskManager()
    spec = {
        "tickSize": 0.00001,
        "tickValueAccount": 1.0,
        "volumeMin": 0.01,
        "volumeMax": 50.0,
        "volumeStep": 0.01,
    }

    volume = rm.calculate_volume_from_spec(
        balance=1000,
        risk_percent=1,
        entry=1.10000,
        stop_loss=1.09800,
        spec=spec,
    )
    assert volume == 0.05


def test_minimum_lot_does_not_override_risk_limit():
    rm = RiskManager()
    spec = {
        "tickSize": 0.01,
        "tickValueAccount": 1.0,
        "volumeMin": 0.01,
        "volumeMax": 20.0,
        "volumeStep": 0.01,
    }

    volume = rm.calculate_volume_from_spec(
        balance=1000,
        risk_percent=0.5,
        entry=4000,
        stop_loss=3990,
        spec=spec,
    )
    assert volume == 0.0


def test_invalid_spec_fails_closed():
    rm = RiskManager()
    assert rm.calculate_volume_from_spec(
        balance=1000,
        risk_percent=1,
        entry=1.1,
        stop_loss=1.09,
        spec={},
    ) == 0.0


def test_broker_timestamp_validation():
    now = datetime.now(timezone.utc)
    fresh = now.isoformat()
    stale = (now - timedelta(seconds=60)).isoformat()
    future = (now + timedelta(seconds=30)).isoformat()

    assert TickerAllMarketData._broker_timestamp_age(fresh) is not None
    assert TickerAllMarketData._broker_timestamp_age(stale) > 15
    assert TickerAllMarketData._broker_timestamp_age(future) < -5
    assert TickerAllMarketData._broker_timestamp_age("invalid") is None
    assert TickerAllMarketData._broker_timestamp_age(None) is None
    assert TickerAllMarketData._broker_timestamp_age(
        "2026-10-27T19:03:35"
    ) is None


def test_execution_engine_rejects_error_response():
    class FakeService:
        def __init__(self, response):
            self.response = response

        async def get_account_info(self):
            return {
                "_is_demo": True,
                "_risk_state_valid": True,
                "daily_drawdown_pct": 0.0,
                "total_drawdown_pct": 0.0,
                "tradeAllowed": True,
                "investorMode": False,
                "balance": 1000,
            }

        async def get_positions(self):
            return []

        async def get_symbol_risk_spec(self, symbol):
            return {
                "tickSize": 0.00001,
                "tickValueAccount": 1.0,
                "volumeMin": 0.01,
                "volumeMax": 50.0,
                "volumeStep": 0.01,
                "currentAsk": 1.10000,
                "currentBid": 1.09998,
            }

        async def place_trade(self, **kwargs):
            return self.response

    async def run_case(response):
        engine = ExecutionEngine(FakeService(response))

        # Test-only override: allow this test to exercise the execution gates.
        with patch("services.execution_engine.AUTO_TRADING_ALLOWED", True):
            return await engine.execute_trade(
            symbol="EURUSD",
            signal="BUY",
            entry=1.10000,
            sl=1.09900,
            tp=1.10200,
            balance=1000,
            risk_percent=1,
            confidence=75,
            spread=0.3,
        )

    failed = asyncio.run(
        run_case("❌ Trade failed.\nInsufficient margin")
    )
    assert failed["success"] is False

    disconnected = asyncio.run(
        run_case("❌ Failed connecting to MT5.")
    )
    assert disconnected["success"] is False

    malformed = asyncio.run(run_case(None))
    assert malformed["success"] is False

    message_only = asyncio.run(
        run_case("✅ Trade placed successfully.\n\nSymbol: EURUSD")
    )
    assert message_only["success"] is False

    confirmed = asyncio.run(run_case({
        "success": True,
        "order_id": "12345",
        "position_id": "67890",
        "string_code": "TRADE_RETCODE_DONE",
        "numeric_code": 10009,
        "message": "Done",
    }))
    assert confirmed["success"] is True

    no_id = asyncio.run(run_case({
        "success": True,
        "order_id": None,
        "position_id": None,
        "string_code": "TRADE_RETCODE_DONE",
    }))
    assert no_id["success"] is False


def test_local_quote_age_is_monotonic():
    received = time.monotonic()
    assert time.monotonic() - received >= 0
