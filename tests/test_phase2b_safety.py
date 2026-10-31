import asyncio
import numpy as np
import pandas as pd

from ml.label_generator import generate_labels
from ml.dataset_builder import prepare_dataset, FEATURE_COLUMNS
from services.risk_manager import RiskManager
from services.spread_guard import SpreadGuard
from services.volatility_filter import volatility_safe
from services.execution_engine import ExecutionEngine

from unittest.mock import patch

def test_label_atr_normalization_is_price_scale_independent():
    fx = pd.DataFrame({"close": [1.1000, 1.1033], "ATR": [0.0011, 0.0011]})
    gold = pd.DataFrame({"close": [4000.0, 4012.0], "ATR": [4.0, 4.0]})
    # use a one-bar horizon; both have the same relative ATR and return
    fx_labels = generate_labels(fx, lookahead=1)
    gold_labels = generate_labels(gold, lookahead=1)
    assert fx_labels["target"].tolist() == [1.0]
    assert gold_labels["target"].tolist() == [1.0]


def test_dataset_builder_rejects_invalid_targets_and_nonfinite_features():
    data = {name: [1.0, 2.0, 3.0, 4.0] for name in FEATURE_COLUMNS}
    data["target"] = [0, 1, 0, 1]
    data["MACD"] = [0.1, np.inf, 0.2, 0.3]
    X, y = prepare_dataset(pd.DataFrame(data))
    assert len(X) == 3 and set(y.unique()) == {0, 1}
    data["target"] = [0, 0, 0, 0]
    try:
        prepare_dataset(pd.DataFrame(data))
        assert False, "single-class dataset must be rejected"
    except ValueError:
        pass


def test_instrument_aware_volatility_and_single_spread_guard():
    assert volatility_safe(0.001, 1.1, "EURUSD")
    assert volatility_safe(3.0, 4000, "XAUUSD")
    assert not volatility_safe(0.01, 1.1, "EURUSD")
    guard = SpreadGuard()
    assert guard.safe("XAUUSDm", 0.4)
    assert not guard.safe("XAUUSDm", 5.1)
    assert not guard.safe("EURUSDm", float("nan"))


def test_risk_manager_disables_legacy_fixed_pip_sizing():
    assert RiskManager().calculate_lot_size(1000, 1, 20) == 0.0


def test_execution_blocks_non_demo_low_confidence_and_duplicate_symbol():
    class FakeService:
        def __init__(self, demo=True, positions=None):
            self.demo = demo
            self.positions = positions or []
            self.orders = 0

        async def get_account_info(self):
            return {"_is_demo": self.demo, "_risk_state_valid": True,
                    "daily_drawdown_pct": 0, "total_drawdown_pct": 0,
                    "tradeAllowed": True, "investorMode": False, "balance": 1000}

        async def get_positions(self):
            return self.positions

        async def get_symbol_risk_spec(self, symbol):
            return {"tickSize": 0.00001, "tickValueAccount": 1.0,
                    "volumeMin": 0.01, "volumeMax": 50.0, "volumeStep": 0.01,
                    "currentAsk": 1.10000, "currentBid": 1.09998}

        async def place_trade(self, **kwargs):
            self.orders += 1
            return {"success": True, "order_id": "o1", "position_id": "p1",
                    "string_code": "TRADE_RETCODE_DONE"}

    async def call(service, confidence=80):
        return await ExecutionEngine(service).execute_trade(
            "EURUSDm", "BUY", 1.1, 1.099, 1.102, 1000, 1, confidence, 0.3
        )

    non_demo = FakeService(demo=False)
    assert not asyncio.run(call(non_demo))["success"]
    assert non_demo.orders == 0

    weak = FakeService()
    assert not asyncio.run(call(weak, confidence=50))["success"]
    assert weak.orders == 0

    duplicate = FakeService(positions=[{"symbol": "EURUSDm"}])
    assert not asyncio.run(call(duplicate))["success"]
    assert duplicate.orders == 0


def test_execution_blocks_drawdown_and_unavailable_positions():
    class FakeService:
        async def get_account_info(self):
            return {"_is_demo": True, "_risk_state_valid": True,
                    "daily_drawdown_pct": 5.0, "total_drawdown_pct": 0.0,
                    "tradeAllowed": True, "investorMode": False, "balance": 1000}
        async def get_positions(self):
            return []
        async def get_symbol_risk_spec(self, symbol):
            raise AssertionError("must stop before sizing")
        async def place_trade(self, **kwargs):
            raise AssertionError("must not place")

    # result = asyncio.run(ExecutionEngine(FakeService()).execute_trade(
    #     "EURUSDm", "BUY", 1.1, 1.099, 1.102, 1000, 1, 80, 0.3
    # ))

    engine = ExecutionEngine(FakeService())

    # Temporarily bypass the kill switch for this isolated safety test.
    # This does not modify the actual production configuration.
    with patch("services.execution_engine.AUTO_TRADING_ALLOWED", True):
        result = asyncio.run(engine.execute_trade(
            "EURUSDm", "BUY", 1.1, 1.099, 1.102, 1000, 1, 80, 0.3
        ))
    assert not result["success"] and "drawdown" in result["message"].lower()



def test_cost_aware_backtester_enters_next_bar_and_charges_costs():
    from ml.cost_aware_backtester import backtest_signals
    candles = pd.DataFrame({
        "open": [1.1000, 1.1000, 1.1000, 1.1000],
        "high": [1.1005, 1.1025, 1.1010, 1.1010],
        "low": [1.0995, 1.0990, 1.0990, 1.0990],
        "close": [1.1000, 1.1020, 1.1000, 1.1000],
        "ATR": [0.0010, 0.0010, 0.0010, 0.0010],
    }, index=pd.date_range("2026-01-01", periods=4, freq="h"))
    signals = pd.Series([1, 0, 0, 0], index=candles.index)
    result = backtest_signals(candles, signals, round_trip_cost_price=0.0002, take_profit_atr_multiple=2.0,
                              max_holding_bars=2)
    assert result["trade_count"] == 1
    assert result["trades"][0]["entry_index"] == str(candles.index[1])
    assert result["trades"][0]["exit_reason"] == "take_profit"
    assert result["trades"][0]["net_r"] < result["trades"][0]["gross_r"]


def test_demo_account_detection_fails_closed():
    from services.account_policy import is_demo_account
    assert is_demo_account({}, "Exness-MT5Trial9") is True
    assert is_demo_account({}, "Exness-MT5Real9") is False
    assert is_demo_account({}, "") is False
    assert is_demo_account({"isDemo": False}, "Exness-MT5Trial9") is False


def test_persistent_drawdown_state_tracks_peak_equity(tmp_path, monkeypatch):
    from services import account_risk_state
    monkeypatch.setattr(account_risk_state, "STATE_PATH", tmp_path / "risk.json")
    first = account_risk_state.update_drawdown_metrics(1000)
    second = account_risk_state.update_drawdown_metrics(950)
    assert first["daily_drawdown_pct"] == 0
    assert round(second["daily_drawdown_pct"], 2) == 5.0
    assert round(second["total_drawdown_pct"], 2) == 5.0


def test_symbol_mapper_applies_broker_suffix_once():
    from services.symbol_mapper import to_broker_symbol
    assert to_broker_symbol("EUR/USD") == "EURUSDm"
    assert to_broker_symbol("EURUSDm") == "EURUSDm"
    assert to_broker_symbol("XAU/USD") == "XAUUSDm"


def test_twelvedata_fetch_preserves_candle_time_and_requests_ema_history(monkeypatch):
    from services import twelvedata_service

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"values": [
                {"datetime": "2026-01-01 02:00:00", "open": "1.2", "high": "1.3", "low": "1.1", "close": "1.25"},
                {"datetime": "2026-01-01 01:00:00", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"},
            ]}

    captured = {}
    def fake_get(url, params, timeout):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr(twelvedata_service.requests, "get", fake_get)
    frame = twelvedata_service.fetch_market_data("EUR/USD", "1h")
    assert captured["outputsize"] == 300
    assert frame.index.is_monotonic_increasing
    assert str(frame.index[0]).startswith("2026-01-01 01:00:00")
