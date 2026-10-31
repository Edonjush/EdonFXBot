# ml/test_features.py

import pandas as pd
import ta

df = pd.read_csv("ml/historical_data.csv")

df["EMA20"] = ta.trend.ema_indicator(
    df["close"],
    window=20
)

df["EMA50"] = ta.trend.ema_indicator(
    df["close"],
    window=50
)

df["RSI"] = ta.momentum.rsi(
    df["close"],
    window=14
)

df["MACD"] = ta.trend.macd(
    df["close"]
)

df["ATR"] = ta.volatility.average_true_range(
    df["high"],
    df["low"],
    df["close"]
)

print(df.tail())