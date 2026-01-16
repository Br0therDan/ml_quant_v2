import logging
import time
import requests
import pandas as pd
from typing import Any, Optional, Tuple
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class AlphaVantageProvider:
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("Alpha Vantage API Key is required")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (requests.exceptions.RequestException, Exception)
        ),
        reraise=True,
    )
    def _fetch_with_retry(self, params: dict[str, Any]) -> dict[str, Any]:
        params["apikey"] = self.api_key
        response = requests.get(self.BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Alpha Vantage specific errors
        if "Note" in data and "call frequency" in data["Note"]:
            logger.warning(f"Rate limit hit: {data['Note']}")
            raise Exception("RateLimitExceeded")

        if "Error Message" in data:
            raise ValueError(f"API Error: {data['Error Message']}")

        return data

    def get_daily_ohlcv(self, symbol: str, outputsize: str = "compact") -> pd.DataFrame:
        """
        Fetch daily adjusted time series.
        Returns cleaned DataFrame with snake_case columns.
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
        }

        data = self._fetch_with_retry(params)

        ts_key = "Time Series (Daily)"
        if ts_key not in data:
            logger.error(f"Missing '{ts_key}' in response for {symbol}")
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(data[ts_key], orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "ts"

        # Alpha Vantage column mapping to snake_case
        # 1. open, 2. high, 3. low, 4. close, 5. adjusted close, 6. volume, 7. dividend amount, 8. split coefficient
        mapping = {
            "1. open": "open",
            "2. high": "high",
            "3. low": "low",
            "4. close": "close",
            "5. adjusted close": "adjusted_close",
            "6. volume": "volume",
        }

        df = df.rename(columns=mapping)
        # Select and convert types
        cols = ["open", "high", "low", "close", "adjusted_close", "volume"]
        df = df[cols].astype(float)
        df = df.sort_index()

        return df

    def get_overview(self, symbol: str) -> dict[str, Any]:
        """Fetch company overview data."""
        params = {"function": "OVERVIEW", "symbol": symbol}
        return self._fetch_with_retry(params)
