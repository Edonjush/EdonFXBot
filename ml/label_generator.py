"""Binary directional labels with dimensionally consistent ATR scaling."""
import numpy as np
import pandas as pd


def generate_labels(df, lookahead=12, threshold=0.0015, reference_atr_pct=0.001, drop_unlabeled=True):
    """Label 1=BUY, 0=SELL; neutral rows remain NaN and are excluded.

    The adaptive threshold compares ATR/entry-price (a dimensionless return)
    with a reference ATR percentage. `threshold` is a minimum return hurdle.
    This preserves the binary target contract expected by existing artifacts.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if lookahead < 1 or threshold <= 0 or reference_atr_pct <= 0:
        raise ValueError("lookahead and threshold parameters must be positive")
    required = {"close", "ATR"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing label inputs: {sorted(missing)}")

    result = df.copy()
    close = pd.to_numeric(result["close"], errors="coerce").to_numpy(dtype=float)
    atr = pd.to_numeric(result["ATR"], errors="coerce").to_numpy(dtype=float)
    labels = np.full(len(result), np.nan, dtype=float)

    for i in range(max(0, len(result) - lookahead)):
        entry, future, current_atr = close[i], close[i + lookahead], atr[i]
        if not (np.isfinite(entry) and entry > 0 and np.isfinite(future)
                and np.isfinite(current_atr) and current_atr > 0):
            continue
        ret = (future - entry) / entry
        atr_pct = current_atr / entry
        adaptive_threshold = max(float(threshold),
                                 float(threshold) * (atr_pct / float(reference_atr_pct)))
        if ret > adaptive_threshold:
            labels[i] = 1
        elif ret < -adaptive_threshold:
            labels[i] = 0

    result["target"] = labels
    # Training validation must retain neutral rows until after chronological
    # splitting; otherwise a purge of N rows no longer means N market candles.
    if drop_unlabeled:
        return result.dropna(subset=["target"]).copy()
    return result
