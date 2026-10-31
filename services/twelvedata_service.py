# services/twelvedata_service.py

import requests
import pandas as pd

from config.settings import TWELVEDATA_API_KEY

BASE_URL = "https://api.twelvedata.com/time_series"


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip()


def fetch_market_data(
    symbol="EUR/USD",
    interval="5min"
):

    symbol = normalize_symbol(symbol)

    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVEDATA_API_KEY,
        # EMA200 needs at least 200 completed candles plus warm-up headroom.
        "outputsize": 300,
        "format": "JSON"
    }

    try:

        response = requests.get(
            BASE_URL,
            params=params,
            timeout=10
        )

        if response.status_code != 200:
            print(
                f"HTTP Error: {response.status_code}"
            )
            print(response.text)
            return None

        data = response.json()

        if "values" not in data:
            print("TwelveData Error:", data)
            return None

        df = pd.DataFrame(data["values"])

        if df.empty:
            print("No market data returned")
            return None

        # TwelveData returns newest-first. Preserve actual candle timestamps so
        # signal de-duplication is keyed by candle identity, not row number.
        if "datetime" not in df.columns:
            print("TwelveData response is missing candle timestamps")
            return None
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
        df = df.dropna(subset=["datetime"]).sort_values("datetime")
        if df["datetime"].duplicated().any():
            df = df.drop_duplicates(subset=["datetime"], keep="last")
        df = df.set_index("datetime", drop=False)

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                )

        return df

    except Exception as e:
        print(
            f"TwelveData Exception: {e}"
        )
        return None