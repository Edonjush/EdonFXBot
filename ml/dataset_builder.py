"""Validated feature/target extraction for the binary BUY/SELL model."""
import numpy as np

FEATURE_COLUMNS = [
    "EMA20", "EMA50", "EMA200", "trend_strength", "RSI", "MACD",
    "ATR", "return", "body_strength", "vol_expansion",
]


def prepare_dataset(df, drop_unlabeled=True):
    required = FEATURE_COLUMNS + ["target"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    data = df[required].copy()
    for column in required:
        data[column] = __import__("pandas").to_numeric(data[column], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan)
    # Keep neutral target rows when preparing for temporal splitting so purge
    # windows are measured in original candles, not only non-neutral samples.
    data = data.dropna(subset=FEATURE_COLUMNS)
    if drop_unlabeled:
        data = data.dropna(subset=["target"])
    if data.empty:
        raise ValueError("No valid training observations remain")
    observed = data["target"].dropna()
    if not observed.isin([0, 1]).all():
        raise ValueError("Target must contain only binary labels 0 and 1 or NaN neutral rows")
    if observed.nunique() != 2:
        raise ValueError("Dataset must contain both BUY and SELL classes")
    y = data["target"].astype(float if not drop_unlabeled else int)
    return data[FEATURE_COLUMNS].astype(float), y
