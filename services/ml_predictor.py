"""Fail-closed prediction adapter for the persisted binary BUY/SELL model."""
import logging
from pathlib import Path
import joblib
import numpy as np

from services.feature_engine import FEATURE_COLUMNS as LIVE_FEATURE_COLUMNS

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[1]

try:
    MODEL = joblib.load(BASE_DIR / "models" / "model.pkl")
    SCALER = joblib.load(BASE_DIR / "models" / "scaler.pkl")
    FEATURE_COLUMNS = list(joblib.load(BASE_DIR / "models" / "features.pkl"))
    if FEATURE_COLUMNS != LIVE_FEATURE_COLUMNS:
        raise ValueError("Saved model feature order does not match live feature engine")
    if list(getattr(MODEL, "classes_", [])) not in ([0, 1], [1, 0]):
        raise ValueError("Production model does not contain exactly binary classes 0 and 1")
    logger.info("ML model, scaler, and feature contract loaded successfully")
except Exception as exc:
    MODEL = SCALER = FEATURE_COLUMNS = None
    logger.error("ML loading error: %s", exc)


def predict_signal(df):
    try:
        if MODEL is None or SCALER is None or FEATURE_COLUMNS is None:
            return {"success": False, "message": "Model artifacts not loaded or feature contract invalid"}
        if df is None or len(df) == 0:
            return {"success": False, "message": "Empty dataframe"}
        missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
        if missing:
            return {"success": False, "message": f"Missing features: {missing}"}
        X = df[FEATURE_COLUMNS].iloc[[-1]].copy()
        X = X.replace([np.inf, -np.inf], np.nan)
        if X.isna().any().any():
            return {"success": False, "message": "Latest feature row contains missing or non-finite values"}
        X_scaled = SCALER.transform(X)
        prediction = int(MODEL.predict(X_scaled)[0])
        probabilities = MODEL.predict_proba(X_scaled)[0]
        classes = list(MODEL.classes_)
        if 0 not in classes or 1 not in classes or len(classes) != 2:
            return {"success": False, "message": "Unexpected model class contract"}
        buy_prob = float(probabilities[classes.index(1)])
        sell_prob = float(probabilities[classes.index(0)])
        if not np.isfinite([buy_prob, sell_prob]).all() or abs((buy_prob + sell_prob) - 1.0) > 1e-5:
            return {"success": False, "message": "Model returned invalid probabilities"}
        signal = "BUY" if prediction == 1 else "SELL"
        confidence = max(buy_prob, sell_prob) * 100.0
        return {
            "success": True, "signal": signal,
            "buy_probability": buy_prob, "sell_probability": sell_prob,
            "directional_probability": buy_prob if signal == "BUY" else sell_prob,
            "confidence": round(confidence, 2),
        }
    except Exception as exc:
        logger.exception("Prediction failed")
        return {"success": False, "message": str(exc)}
