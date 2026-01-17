import contextlib
import logging
from datetime import datetime
from typing import Any

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
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
            "7. dividend amount": "dividend_amount",
            "8. split coefficient": "split_coefficient",
        }

        df = df.rename(columns=mapping)
        # Select and convert types
        cols = [
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
            "dividend_amount",
            "split_coefficient",
        ]
        df = df[cols].astype(float)
        df = df.sort_index()

        return df

    def get_overview(self, symbol: str) -> dict[str, Any]:
        """Fetch company overview data and map to internal schema."""
        params = {"function": "OVERVIEW", "symbol": symbol}
        data = self._fetch_with_retry(params)
        return self._map_overview(data)

    def search_symbols(self, query: str) -> pd.DataFrame:
        """Search for symbols using Alpha Vantage API."""
        params = {"function": "SYMBOL_SEARCH", "keywords": query}
        data = self._fetch_with_retry(params)
        results = []
        for item in data.get("bestMatches", []):
            results.append(
                {
                    "symbol": item.get("1. symbol"),
                    "name": item.get("2. name"),
                    "type": item.get("3. type"),
                    "region": item.get("4. region"),
                    "market_open": item.get("5. marketOpen"),
                    "market_close": item.get("6. marketClose"),
                    "timezone": item.get("7. timezone"),
                    "currency": item.get("8. currency"),
                    "relevance": float(item.get("9. matchScore", 0)),
                }
            )
        return pd.DataFrame(results)

    def _map_overview(self, data: dict[str, Any]) -> dict[str, Any]:
        """Alpha Vantage 기초 데이터를 내부 모델 필드로 매핑합니다."""
        if not data:
            return {}

        mapping = {
            "AssetType": "asset_type",
            "Name": "name",
            "Description": "description",
            "CIK": "cik",
            "Exchange": "exchange",
            "Currency": "currency",
            "Country": "country",
            "Sector": "sector",
            "Industry": "industry",
            "Address": "address",
            "OfficialSite": "official_site",
            "FiscalYearEnd": "fiscal_year_end",
            "LatestQuarter": "latest_quarter",
            "MarketCapitalization": "market_cap",
            "EBITDA": "ebitda",
            "PERatio": "pe_ratio",
            "PEGRatio": "peg_ratio",
            "BookValue": "book_value",
            "DividendPerShare": "dividend_per_share",
            "DividendYield": "dividend_yield",
            "EPS": "eps",
            "RevenuePerShareTTM": "revenue_per_share_ttm",
            "ProfitMargin": "profit_margin",
            "OperatingMarginTTM": "operating_margin_ttm",
            "ReturnOnAssetsTTM": "return_on_assets_ttm",
            "ReturnOnEquityTTM": "return_on_equity_ttm",
            "RevenueTTM": "revenue_ttm",
            "GrossProfitTTM": "gross_profit_ttm",
            "DilutedEPSTTM": "diluted_eps_ttm",
            "QuarterlyEarningsGrowthYOY": "quarterly_earnings_growth_yoy",
            "QuarterlyRevenueGrowthYOY": "quarterly_revenue_growth_yoy",
            "AnalystTargetPrice": "analyst_target_price",
            "AnalystRatingStrongBuy": "analyst_rating_strong_buy",
            "AnalystRatingBuy": "analyst_rating_buy",
            "AnalystRatingHold": "analyst_rating_hold",
            "AnalystRatingSell": "analyst_rating_sell",
            "AnalystRatingStrongSell": "analyst_rating_strong_sell",
            "TrailingPE": "trailing_pe",
            "ForwardPE": "forward_pe",
            "PriceToSalesRatioTTM": "price_to_sales_ratio_ttm",
            "PriceToBookRatio": "price_to_book_ratio",
            "EVToRevenue": "ev_to_revenue",
            "EVToEBITDA": "ev_to_ebitda",
            "Beta": "beta",
            "52WeekHigh": "high_52week",
            "52WeekLow": "low_52week",
            "50DayMovingAverage": "ma_50day",
            "200DayMovingAverage": "ma_200day",
            "SharesOutstanding": "shares_outstanding",
            "SharesFloat": "shares_float",
            "PercentInsiders": "percent_insiders",
            "PercentInstitutions": "percent_institutions",
            "DividendDate": "dividend_date",
            "ExDividendDate": "ex_dividend_date",
        }
        mapped: dict[str, Any] = {}
        for av_key, model_key in mapping.items():
            val = data.get(av_key)
            if val and val != "None":
                if "date" in model_key.lower() or "quarter" in model_key.lower():
                    with contextlib.suppress(Exception):
                        mapped[model_key] = datetime.strptime(val, "%Y-%m-%d")
                elif any(
                    x in model_key.lower()
                    for x in ["cap", "ebitda", "revenue", "profit", "shares"]
                ):
                    with contextlib.suppress(Exception):
                        # MarketCap etc can be very large
                        mapped[model_key] = int(val)
                else:
                    with contextlib.suppress(Exception):
                        mapped[model_key] = float(val)
                    if model_key not in mapped:
                        mapped[model_key] = val
        return mapped
