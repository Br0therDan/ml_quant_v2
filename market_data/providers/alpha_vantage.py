import os
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


class AlphaVantageAPI:
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            # Fallback or warning
            pass

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        params["apikey"] = self.api_key
        response = requests.get(self.BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if "Note" in data and "call frequency" in data["Note"]:
            raise Exception(f"Alpha Vantage Rate Limit Hit: {data['Note']}")

        if "Error Message" in data:
            raise Exception(f"Alpha Vantage API Error: {data['Error Message']}")

        if "Information" in data:
            # Sometimes used for "invalid api key" or "reaching limit"
            pass

        return data

    def get_daily_adjusted(
        self, symbol: str, outputsize: str = "compact"
    ) -> tuple[pd.DataFrame, dict]:
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
        }
        data = self._get(params)

        # Parse logic
        ts_key = "Time Series (Daily)"
        if ts_key not in data:
            return pd.DataFrame(), data

        df = pd.DataFrame.from_dict(data[ts_key], orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.sort_index()
        return df, data

    def get_weekly(self, symbol: str) -> tuple[pd.DataFrame, dict]:
        return self._get_time_series(symbol, "TIME_SERIES_WEEKLY")

    def get_monthly(self, symbol: str) -> tuple[pd.DataFrame, dict]:
        return self._get_time_series(symbol, "TIME_SERIES_MONTHLY")

    def _get_time_series(self, symbol: str, function: str) -> tuple[pd.DataFrame, dict]:
        params = {
            "function": function,
            "symbol": symbol,
        }
        data = self._get(params)
        ts_key = (
            "Weekly Time Series"
            if "WEEKLY" in function.upper()
            else "Monthly Time Series"
        )
        if ts_key not in data:
            return pd.DataFrame(), data

        df = pd.DataFrame.from_dict(data[ts_key], orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.sort_index()
        return df, data

    def get_crypto_series(
        self,
        symbol: str,
        market: str = "USD",
        function: str = "DIGITAL_CURRENCY_DAILY",
        outputsize: str = "full",
    ) -> tuple[pd.DataFrame, dict]:
        """Fetch Crypto Time Series."""
        params = {
            "function": function,
            "symbol": symbol,
            "market": market,
        }
        # Crypto doesn't explicitly document 'outputsize' in some docs but it works for daily
        if "DAILY" in function.upper():
            params["outputsize"] = outputsize

        data = self._get(params)

        # Determine Key Based on Function
        if "DAILY" in function.upper():
            ts_key = "Time Series (Digital Currency Daily)"
        elif "WEEKLY" in function.upper():
            ts_key = "Time Series (Digital Currency Weekly)"
        else:
            ts_key = "Time Series (Digital Currency Monthly)"

        if ts_key not in data:
            return pd.DataFrame(), data

        df = pd.DataFrame.from_dict(data[ts_key], orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.sort_index()
        return df, data

    def get_forex_series(
        self,
        from_symbol: str,
        to_symbol: str = "USD",
        function: str = "FX_DAILY",
        outputsize: str = "full",
    ) -> tuple[pd.DataFrame, dict]:
        """Fetch Forex/FX Time Series."""
        params = {
            "function": function,
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
        }
        if "DAILY" in function.upper():
            params["outputsize"] = outputsize

        data = self._get(params)

        if "DAILY" in function.upper():
            ts_key = "Time Series FX (Daily)"
        elif "WEEKLY" in function.upper():
            ts_key = "Time Series FX (Weekly)"
        else:
            ts_key = "Time Series FX (Monthly)"

        if ts_key not in data:
            return pd.DataFrame(), data

        df = pd.DataFrame.from_dict(data[ts_key], orient="index")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        df = df.sort_index()
        return df, data

    def get_company_overview(self, symbol: str) -> dict[str, Any]:
        params = {"function": "OVERVIEW", "symbol": symbol}
        return self._get(params)

    def get_economic_indicator(
        self, function: str, interval: str | None = None
    ) -> pd.DataFrame:
        """
        Fetch economic indicator (e.g., BIG_MAC_INDEX, REAL_GDP).
        Returns a DataFrame with 'date' and 'value'.
        """
        params = {"function": function}
        if interval:
            params["interval"] = interval

        data = self._get(params)

        if "data" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["data"])
        # AV returns 'date' and 'value'
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()

        return df

    def get_commodity(self, function: str, interval: str | None = None) -> pd.DataFrame:
        """
        Fetch commodity price (e.g., WTI, BRENT, COPPER).
        """
        # Logic is identical to economic indicators (function + interval -> data)
        return self.get_economic_indicator(function, interval)

        return self.get_economic_indicator(function, interval)

    def get_news_sentiment(
        self, tickers: str | None = None, topics: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        """
        Fetch News & Sentiment.
        """
        params = {"function": "NEWS_SENTIMENT", "limit": limit, "sort": "LATEST"}
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics

        return self._get(params)

    def symbol_search(self, keywords: str) -> list[dict[str, Any]]:
        """
        Search for symbols using Alpha Vantage SYMBOL_SEARCH.
        """
        params = {"function": "SYMBOL_SEARCH", "keywords": keywords}
        data = self._get(params)
        return data.get("bestMatches", [])
