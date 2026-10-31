# download_data.py

#!/usr/bin/env python3
"""
Five-Year EUR/USD Historical Data Downloader.

Downloads hourly OHLCV candles from Twelve Data, combines the
chunks, removes duplicates, sorts chronologically, and saves
the result to config.settings.HISTORICAL_DATA_PATH.

Supports:
    python ml/download_data.py
    from ml.download_data import download_historical_data
"""

import os
import sys
import time
import logging
import calendar
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from twelvedata import TDClient


# ---------------------------------------------------------
# PROJECT PATHS AND ENVIRONMENT
# ---------------------------------------------------------

ROOT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Load the project's .env file explicitly.
ENV_PATH = os.path.join(ROOT_DIR, ".env")
load_dotenv(ENV_PATH, override=False)

from config.settings import HISTORICAL_DATA_PATH  # noqa: E402

# Prefer an existing environment variable, otherwise read
# the project .env file directly.
TWELVEDATA_API_KEY = os.getenv(
    "TWELVEDATA_API_KEY", ""
).strip()


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

SYMBOL = "EUR/USD"
INTERVAL = "1h"
YEARS = 5

# Seven months can approach the API's maximum candle count.
# Use shorter chunks to reduce the risk of truncated responses.
CHUNK_MONTHS = 3

MAX_OUTPUTSIZE = 5000
RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# DATE UTILITIES
# ---------------------------------------------------------

def subtract_months(date, months):
    """Subtract calendar months while preserving a valid date."""

    month_index = date.month - 1 - months
    year = date.year + month_index // 12
    month = month_index % 12 + 1

    day = min(
        date.day,
        calendar.monthrange(year, month)[1],
    )

    return date.replace(year=year, month=month, day=day)


def get_timestamp_column(df):
    """Find the candle timestamp column or raise an error."""

    candidates = {
        "datetime",
        "date",
        "time",
        "timestamp",
        "index",
    }

    for column in df.columns:
        if str(column).strip().lower() in candidates:
            return column

    raise ValueError(
        "No timestamp column found in the Twelve Data response. "
        f"Received columns: {list(df.columns)}"
    )


# ---------------------------------------------------------
# API REQUEST
# ---------------------------------------------------------

def download_chunk(
    client,
    start_date,
    end_date,
    symbol=SYMBOL,
    interval=INTERVAL,
):
    """Download a single date range, retrying failed requests."""

    last_error = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.info(
                "Requesting %s | %s to %s",
                symbol,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )

            response = client.time_series(
                symbol=symbol,
                interval=interval,
                start_date=start_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                end_date=end_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                outputsize=MAX_OUTPUTSIZE,
                order="ASC",
                timezone="UTC",
            )

            df = response.as_pandas()

            if df is None or df.empty:
                raise RuntimeError(
                    "Twelve Data returned no candles for this range."
                )

            df = df.reset_index()
            timestamp_column = get_timestamp_column(df)

            df = df.rename(
                columns={timestamp_column: "datetime"}
            )

            df["datetime"] = pd.to_datetime(
                df["datetime"],
                errors="coerce",
                utc=True,
            )

            df = df.dropna(subset=["datetime"])

            # Keep only candles inside the requested interval.
            df = df.loc[
                (df["datetime"] >= start_date)
                & (df["datetime"] <= end_date)
            ].copy()

            if df.empty:
                raise RuntimeError(
                    "The response contained no valid candles "
                    "inside the requested date range."
                )

            df = df.sort_values("datetime")

            if len(df) >= MAX_OUTPUTSIZE:
                raise RuntimeError(
                    f"The response contains {len(df)} candles, "
                    f"reaching the {MAX_OUTPUTSIZE}-candle limit. "
                    "Reduce CHUNK_MONTHS to 1."
                )

            return df

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Attempt %s/%s failed: %s",
                attempt,
                RETRY_ATTEMPTS,
                exc,
            )

            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise RuntimeError(
        f"Failed to download {start_date} through {end_date} "
        f"after {RETRY_ATTEMPTS} attempts: {last_error}"
    ) from last_error


# ---------------------------------------------------------
# FIVE-YEAR DOWNLOAD
# ---------------------------------------------------------

def download_historical_data(
    symbol=SYMBOL,
    interval=INTERVAL,
    years=YEARS,
):
    """
    Download historical candles and save a single CSV.

    Returns:
        int: Number of unique candles saved.

    Raises:
        RuntimeError: If the API key is missing or a date
                      range cannot be downloaded.
        ValueError: If years is invalid.
    """

    if not TWELVEDATA_API_KEY:
        raise RuntimeError(
            f"Twelve Data API key is missing.\n"
            f"Expected environment variable: TWELVEDATA_API_KEY\n"
            f"Expected .env file: {ENV_PATH}\n"
            "Add TWELVEDATA_API_KEY=your_key to that file."
        )

    if years <= 0:
        raise ValueError("years must be greater than zero.")

    client = TDClient(apikey=TWELVEDATA_API_KEY)

    end_date = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    start_date = end_date.replace(
        year=end_date.year - years,
        day=min(
            end_date.day,
            calendar.monthrange(
                end_date.year - years,
                end_date.month,
            )[1],
        ),
    )

    logger.info("=" * 60)
    logger.info("FIVE-YEAR HISTORICAL DATA DOWNLOAD")
    logger.info("Symbol: %s", symbol)
    logger.info("Interval: %s", interval)
    logger.info("Start UTC: %s", start_date)
    logger.info("End UTC: %s", end_date)
    logger.info("=" * 60)

    chunks = []
    chunk_end = end_date
    chunk_number = 0

    while chunk_end > start_date:
        chunk_start = max(
            start_date,
            subtract_months(chunk_end, CHUNK_MONTHS),
        )

        chunk_number += 1

        logger.info(
            "Chunk %s: %s -> %s",
            chunk_number,
            chunk_start.date(),
            chunk_end.date(),
        )

        # A failed or empty range stops the run rather than
        # silently producing a misleadingly incomplete dataset.
        df = download_chunk(
            client=client,
            start_date=chunk_start,
            end_date=chunk_end,
            symbol=symbol,
            interval=interval,
        )

        chunks.append(df)

        logger.info(
            "Chunk %s downloaded: %s candles",
            chunk_number,
            len(df),
        )

        chunk_end = chunk_start

        if chunk_end > start_date:
            time.sleep(1)

    if not chunks:
        raise RuntimeError("No historical candles were downloaded.")

    # Merge all date ranges.
    combined = pd.concat(chunks, ignore_index=True)

    combined["datetime"] = pd.to_datetime(
        combined["datetime"],
        errors="coerce",
        utc=True,
    )

    combined = combined.dropna(subset=["datetime"])

    combined = combined.loc[
        (combined["datetime"] >= start_date)
        & (combined["datetime"] <= end_date)
    ].copy()

    combined = combined.drop_duplicates(
        subset=["datetime"],
        keep="last",
    )

    combined = combined.sort_values(
        "datetime"
    ).reset_index(drop=True)

    if combined.empty:
        raise RuntimeError(
            "No valid candles remain after data cleaning."
        )

    # Validate essential OHLC fields.
    required_columns = {"open", "high", "low", "close"}
    normalized_columns = {
        str(column).strip().lower()
        for column in combined.columns
    }

    missing_columns = required_columns - normalized_columns

    if missing_columns:
        raise RuntimeError(
            f"Missing required OHLC columns: {sorted(missing_columns)}"
        )

    # Save timestamps in UTC without timezone suffixes, compatible
    # with most existing pandas-based CSV backtest loaders.
    combined["datetime"] = combined["datetime"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    output_path = os.path.abspath(HISTORICAL_DATA_PATH)
    output_dir = os.path.dirname(output_path)

    os.makedirs(output_dir, exist_ok=True)

    temporary_path = output_path + ".tmp"

    try:
        combined.to_csv(temporary_path, index=False)
        os.replace(temporary_path, output_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

    logger.info("=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("Output: %s", output_path)
    logger.info("Unique candles: %s", len(combined))
    logger.info("First candle UTC: %s", combined["datetime"].iloc[0])
    logger.info("Last candle UTC: %s", combined["datetime"].iloc[-1])
    logger.info("=" * 60)

    return len(combined)


# ---------------------------------------------------------
# COMMAND-LINE ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    try:
        rows = download_historical_data()

        print(
            f"\nSUCCESS: Saved {rows:,} candles to "
            f"{os.path.abspath(HISTORICAL_DATA_PATH)}"
        )

    except Exception as exc:
        logger.exception("Historical data download failed")
        print(f"\nERROR: {exc}")
        sys.exit(1)
