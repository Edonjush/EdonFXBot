from pathlib import Path
from datetime import datetime, timezone, timedelta
import unittest

ROOT = Path(__file__).resolve().parents[1]

ENGINE_FILE = ROOT / "services" / "execution_engine.py"
RISK_FILE = ROOT / "services" / "risk_manager.py"
TICKER_FILE = ROOT / "services" / "tickerall_service.py"


class RemainingSafetyTests(unittest.TestCase):

    def test_1_execution_requires_structured_broker_confirmation(self):
        """Reject message-only confirmation; require structured evidence."""
        source = ENGINE_FILE.read_text(encoding="utf-8")

        # A success phrase in a string is not proof that an order was executed.
        self.assertIn(
            "isinstance(result, dict)",
            source,
            "Execution should validate a structured broker response."
        )
        self.assertIn(
            "order_id",
            source,
            "Execution should verify a broker order identifier."
        )

    def test_2_execution_uses_broker_spec_risk_sizing(self):
        """Ensure execution uses the broker-spec-aware risk calculator."""
        engine = ENGINE_FILE.read_text(encoding="utf-8")
        risk = RISK_FILE.read_text(encoding="utf-8")

        self.assertIn(
            "calculate_volume_from_spec",
            risk,
            "Broker-spec risk-sizing method is missing."
        )
        self.assertIn(
            "calculate_volume_from_spec",
            engine,
            "Execution engine is not using broker-spec risk sizing."
        )
        self.assertNotIn(
            "calculate_lot_size(",
            engine,
            "Legacy lot sizing is still called by the execution engine."
        )

    def test_3_tickerall_quote_timestamp_validation(self):
        """Test timestamp parsing and check quote freshness enforcement."""
        from services.tickerall_service import TickerAllService

        now = datetime.now(timezone.utc)
        stamp = lambda dt: dt.isoformat()

        fresh_age = TickerAllService._broker_timestamp_age(stamp(now))
        self.assertIsNotNone(fresh_age)
        self.assertLess(abs(fresh_age), 5)

        stale_age = TickerAllService._broker_timestamp_age(
            stamp(now - timedelta(minutes=2))
        )
        self.assertIsNotNone(stale_age)
        self.assertGreater(stale_age, 60)

        self.assertIsNone(
            TickerAllService._broker_timestamp_age("not-a-timestamp")
        )
        self.assertIsNone(
            TickerAllService._broker_timestamp_age("2026-10-27T12:00:00")
        )

        future_age = TickerAllService._broker_timestamp_age(
            stamp(now + timedelta(minutes=1))
        )
        self.assertIsNotNone(future_age)
        self.assertLess(future_age, -5)

        source = TICKER_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "_broker_timestamp_age",
            source,
            "Quote handling must validate broker timestamps."
        )
        self.assertIn(
            "received_monotonic",
            source,
            "Quote handling must track local receipt time."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
