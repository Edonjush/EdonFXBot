# ml/regime_filter.py

import pandas as pd
import ta
import numpy as np

def classify_regime(df):

    conditions = []

    atr_mean = df["ATR"].mean()

    for i in range(len(df)):

        ts = df["trend_strength"].iloc[i]
        atr = df["ATR"].iloc[i]

        if abs(ts) < 0.0003:
            regime = "RANGE"

        elif ts > 0:
            regime = "TREND_UP"

        else:
            regime = "TREND_DOWN"

        if atr > atr_mean * 1.5:
            regime = regime + "_VOL"

        conditions.append(regime)

    df["regime"] = conditions

    # ==============================
    # REGIME ENCODING
    # ==============================

    df["regime_code"] = df["regime"].map({
        "RANGE": 0,
        "RANGE_VOL": 1,
        "TREND_UP": 2,
        "TREND_UP_VOL": 3,
        "TREND_DOWN": 4,
        "TREND_DOWN_VOL": 5
    })

    return df