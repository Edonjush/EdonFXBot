"""Confluence-based signal generation; all filters must agree."""
import math
from services.feature_engine import build_features
from services.ml_predictor import predict_signal
from services.market_regime import detect_market_regime
from services.volatility_filter import volatility_safe
from services.news_filter import session_risk_window
from services.spread_guard import SpreadGuard
from config.settings import MIN_ML_CONFIDENCE

_SPREAD_GUARD = SpreadGuard()


def trend_confirmation(df):
    if df is None or len(df) < 3:
        return None
    latest, previous = df.iloc[-1], df.iloc[-3]
    try:
        ema20_now, ema20_prev = float(latest["EMA20"]), float(previous["EMA20"])
        ema50, close = float(latest["EMA50"]), float(latest["close"])
        slope, separation = ema20_now - ema20_prev, ema20_now - ema50
        if not all(math.isfinite(x) for x in (slope, separation, ema50, close)) or ema50 <= 0:
            return None
        if abs(separation) < close * 0.0002:
            return None
        if separation > 0 and slope > 0:
            return "BUY"
        if separation < 0 and slope < 0:
            return "SELL"
        return None
    except (TypeError, ValueError, KeyError):
        return None


def breakout_signal(df):
    if df is None or len(df) < 25 or "ATR" not in df:
        return None
    try:
        close = float(df["close"].iloc[-1])
        high = float(df["high"].iloc[-21:-1].max())
        low = float(df["low"].iloc[-21:-1].min())
        atr = float(df["ATR"].iloc[-1])
        if not all(math.isfinite(x) for x in (close, high, low, atr)) or atr <= 0:
            return None
        buffer = atr * 0.2
        if close > high + buffer:
            return "BUY"
        if close < low - buffer:
            return "SELL"
        return None
    except (TypeError, ValueError):
        return None


def generate_signal(m5_df, h1_df, symbol, spread=None):
    try:
        if session_risk_window():
            return {"status": "blocked", "reason": "UTC session-risk blackout window"}
        m5 = build_features(m5_df)
        h1 = build_features(h1_df)
        if len(m5) < 30 or len(h1) < 30:
            return {"status": "blocked", "reason": "Insufficient feature history"}
        latest = m5.iloc[-1]
        atr, close = float(latest["ATR"]), float(latest["close"])
        if not volatility_safe(atr, close, symbol):
            return {"status": "blocked", "reason": "Unsafe normalized volatility"}
        if spread is None:
            return {"status": "blocked", "reason": "Live broker spread is unavailable"}
        if not _SPREAD_GUARD.safe(symbol, spread):
            return {"status": "blocked", "reason": "Spread too high"}
        regime = detect_market_regime(m5, symbol=symbol)
        if regime != "NORMAL":
            return {"status": "blocked", "reason": f"Market regime not tradable: {regime}"}
        m5_trend = trend_confirmation(m5)
        h1_trend = trend_confirmation(h1)
        if m5_trend is None or h1_trend is None:
            return {"status": "blocked", "reason": "Trend confirmation unavailable"}
        if m5_trend != h1_trend:
            return {"status": "blocked", "reason": "M5 and H1 trends disagree"}
        breakout = breakout_signal(m5)
        if breakout is not None and breakout != m5_trend:
            return {"status": "blocked", "reason": "Breakout and trend disagree"}
        # The production model and historical training dataset are H1 candles.
        # Predict on H1 features; use M5 as execution-timing confirmation only.
        ml = predict_signal(h1)
        if not isinstance(ml, dict) or not ml.get("success"):
            return {"status": "blocked", "reason": ml.get("message", "ML prediction failed") if isinstance(ml, dict) else "Invalid ML output"}
        confidence = float(ml.get("confidence", 0))
        if not math.isfinite(confidence) or confidence < MIN_ML_CONFIDENCE:
            return {"status": "blocked", "reason": "ML confidence below configured threshold"}
        if ml.get("signal") != m5_trend:
            return {"status": "blocked", "reason": "ML prediction disagrees with M5/H1 trend"}
        sl_distance = atr * 2.0
        tp_distance = atr * 4.0
        signal = m5_trend
        return {
            "status": "signal", "symbol": symbol, "signal": signal,
            "entry": close,
            "stop_loss": close - sl_distance if signal == "BUY" else close + sl_distance,
            "take_profit": close + tp_distance if signal == "BUY" else close - tp_distance,
            "atr": atr, "market_regime": regime,
            "ml_confidence": confidence,
            "probability": float(ml["buy_probability"] if signal == "BUY" else ml["sell_probability"]),
            "signal_bar_time": str(m5.index[-1]),
        }
    except Exception as exc:
        return {"status": "blocked", "reason": f"Signal Engine Error: {exc}"}
