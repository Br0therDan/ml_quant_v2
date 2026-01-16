from datetime import datetime
import pandas as pd
from .providers.alpha_vantage import AlphaVantageAPI


class LocalMarketDataClient:
    """
    순수 API 프로바이더 클라이언트.
    데이터의 영속성(Persistence)은 src/quant/services/market_data.py에서 담당합니다.
    """

    def __init__(self, api_key: str | None = None):
        self.api = AlphaVantageAPI(api_key=api_key)

    def get_daily_prices_raw(
        self, symbol: str, outputsize: str = "compact"
    ) -> pd.DataFrame:
        """API로부터 일별 주가 데이터를 가져옵니다."""
        df, _ = self.api.get_daily_adjusted(symbol, outputsize=outputsize)
        return df

    def search_hybrid(self, query: str) -> pd.DataFrame:
        """API를 통해 심볼을 검색합니다. (하이브리드 로직은 서비스 계층으로 이관됨)"""
        results = []
        try:
            api_res = self.api.symbol_search(query)
            for item in api_res:
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
        except Exception:
            pass
        return pd.DataFrame(results)

    def _map_av_overview(self, data: dict) -> dict:
        """Alpha Vantage 기초 데이터를 내부 모델 필드로 매핑합니다."""
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
        mapped = {}
        for av_key, model_key in mapping.items():
            val = data.get(av_key)
            if val and val != "None":
                if "date" in model_key.lower() or "quarter" in model_key.lower():
                    try:
                        mapped[model_key] = datetime.strptime(val, "%Y-%m-%d")
                    except Exception:
                        pass
                elif any(
                    x in model_key.lower()
                    for x in ["cap", "ebitda", "revenue", "profit", "shares"]
                ):
                    try:
                        mapped[model_key] = int(val)
                    except Exception:
                        pass
                else:
                    try:
                        mapped[model_key] = float(val)
                    except Exception:
                        mapped[model_key] = val
        return mapped
