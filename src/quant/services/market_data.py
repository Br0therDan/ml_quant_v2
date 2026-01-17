from datetime import datetime, timedelta
import pandas as pd
from typing import Optional

from market_data.client import LocalMarketDataClient
from quant.db.metastore import MetaStore
from quant.db.timeseries import SeriesStore
from quant.models import CompanyOverview, Symbol
from quant.config import settings


class MarketDataService:
    def __init__(self, api_key: str | None = None, read_only: bool = False):
        self.client = LocalMarketDataClient(
            api_key=api_key or settings.alpha_vantage_api_key
        )
        self.meta_store = MetaStore()
        self.series_store = SeriesStore(read_only=read_only)

    def get_daily_prices(
        self,
        symbol: str,
        force_refresh: bool = False,
        asset_type: str = "Equity",
        currency: str = "USD",
        enrich_metadata: bool = False,
    ) -> pd.DataFrame:
        """
        수집(market_data)과 저장(SeriesStore)을 조율하고 데이터 보강(Join)을 수행합니다.
        """
        # 1. 로컬 최신 날짜 확인
        latest_date = self.series_store.get_latest_date(
            symbol, frequency="daily", currency=currency
        )

        # 2. 수집 여부 결정
        should_fetch = force_refresh
        if not latest_date:
            should_fetch = True
        else:
            if (datetime.now() - latest_date) > timedelta(days=1):
                # 장마감 후 데이터 업데이트 확인 (단순 구현)
                should_fetch = True

        if should_fetch and not self.series_store.read_only:
            outputsize = "full" if not latest_date else "compact"
            # market_data 클라이언트는 이제 순수 DF만 반환한다고 가정 (후속 작업 예정)
            df = self.client.get_daily_prices_raw(symbol, outputsize=outputsize)

            if not df.empty:
                self.series_store.save_ohlcv(
                    df,
                    symbol,
                    frequency="daily",
                    asset_type=asset_type,
                    currency=currency,
                )

        # 3. 로컬에서 데이터 조회
        df_res = self.series_store.get_ohlcv(
            symbol, frequency="daily", currency=currency
        )

        # 4. 데이터 보강 (Join 로직 이관)
        if enrich_metadata and not df_res.empty:
            overview = self.get_company_overview(symbol)
            if overview:
                df_res["sector"] = overview.sector
                df_res["industry"] = overview.industry

        return df_res

    def get_company_overview(
        self, symbol: str, force_refresh: bool = False
    ) -> Optional[CompanyOverview]:
        """기초 데이터 수집 및 SQLite 저장 조율"""
        # 1. DB 먼저 확인
        with self.meta_store.get_session() as session:
            obj = session.get(CompanyOverview, symbol)
            if obj:
                session.refresh(obj)

        should_fetch = force_refresh
        if not obj or (datetime.utcnow() - obj.updated_at) > timedelta(days=30):
            should_fetch = True

        if should_fetch:
            # market_data 클라이언트 활용
            data = self.client.api.get_company_overview(symbol)
            if data:
                mapped_data = self.client._map_av_overview(data)
                if not mapped_data.get("symbol"):
                    mapped_data["symbol"] = symbol
                overview = CompanyOverview(**mapped_data)
                self.meta_store.save_company_overview(overview)
                return overview

        return obj

    def search_symbols(self, query: str, limit: int = 20) -> pd.DataFrame:
        """
        Hybrid Search:
        1. 로컬 SQLite 메타 DB 검색 (Symbol 테이블)
        2. Alpha Vantage API 검색
        3. 결과 병합 (로컬 우선)
        """
        from sqlmodel import select, col

        results = []
        seen_symbols = set()

        # 1. 로컬 검색
        with self.meta_store.get_session() as session:
            stmt = (
                select(Symbol)
                .where(
                    (col(Symbol.symbol).contains(query))
                    | (col(Symbol.name).contains(query))
                )
                .limit(limit)
            )
            local_res = session.exec(stmt).all()
            for r in local_res:
                d = r.model_dump()
                d["source"] = "LOCAL"
                d["relevance"] = 1.0
                results.append(d)
                seen_symbols.add(r.symbol)

        # 2. API 검색
        # 클라이언트의 search_hybrid는 이제 순수하게 API 검색만 수행함
        api_res_df = self.client.search_hybrid(query)
        for _, row in api_res_df.iterrows():
            sym = row["symbol"]
            if sym and sym not in seen_symbols:
                d = row.to_dict()
                d["source"] = "API"
                results.append(d)
                seen_symbols.add(sym)

        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values(by="relevance", ascending=False).reset_index(drop=True)
        return df
