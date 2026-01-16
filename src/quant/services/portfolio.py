import logging
import pandas as pd
from datetime import datetime
from typing import List, Optional

from quant.db.timeseries import SeriesStore
from quant.db.metastore import MetaStore
from quant.models import Symbol

log = logging.getLogger(__name__)


class PortfolioService:
    def __init__(
        self,
        series_store: Optional[SeriesStore] = None,
        meta_store: Optional[MetaStore] = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()

    def generate_recommendation(
        self, date: Optional[datetime] = None, top_k: int = 3
    ) -> pd.DataFrame:
        """
        특정 시점(기본값: 최신 데이터 시점)의 예측 점수를 바탕으로
        Top-K 종목을 선정하고 동일 비중(Equal Weight)으로 배분합니다.
        """
        # 1. 활성 심볼 목록 가져오기
        with self.meta_store.get_session() as session:
            from sqlmodel import select

            symbols = [
                s.symbol
                for s in session.exec(
                    select(Symbol).where(Symbol.is_active == True)
                ).all()
            ]

        if not symbols:
            log.warning("No active symbols found.")
            return pd.DataFrame()

        # 2. 모든 심볼의 최신 예측 점수(expert_ensemble 필터링) 가져오기
        all_preds = []
        for symbol in symbols:
            df_p = self.series_store.get_predictions(symbol)
            if not df_p.empty:
                # expert_ensemble 태스크 결과 우선, 없으면 daily_pred
                df_expert = df_p[df_p["task_id"] == "expert_ensemble"]
                if not df_expert.empty:
                    all_preds.append(df_expert)
                else:
                    all_preds.append(df_p[df_p["task_id"] == "daily_pred"])

        if not all_preds:
            log.warning("No predictions found for any symbol.")
            return pd.DataFrame()

        df_all = pd.concat(all_preds)

        # 3. 타겟 날짜 결정 (입력이 없으면 가장 최신 날짜)
        if date is None:
            target_date = df_all["date"].max()
        else:
            # 전달받은 date와 가장 가까운 (또는 정확히 일치하는) 날짜 찾기
            target_date = date

        df_today = df_all[df_all["date"] == target_date].copy()
        if df_today.empty:
            log.warning(f"No predictions found for date: {target_date}")
            return pd.DataFrame()

        # 4. 상위 K개 종목 선정 (Score 내림차순)
        df_top = df_today.sort_values("score", ascending=False).head(top_k)

        # 5. 비중 배분 (Equal Weight)
        n_selected = len(df_top)
        df_top["weight"] = 1.0 / n_selected if n_selected > 0 else 0.0

        # 6. 결과 정리
        df_res = df_top[["date", "symbol", "weight", "score", "model_id"]].copy()

        # DuckDB 저장
        self.series_store.save_portfolio_decisions(df_res)
        log.info(
            f"Generated and saved portfolio decisions for {target_date} (Top-{n_selected})"
        )

        return df_res

    def generate_recommendations_range(
        self, start_date: str, end_date: str, top_k: int = 3
    ):
        """특정 기간 동안 매일의 추천 포트폴리오를 생성하여 저장합니다."""
        # 모든 예측 점수 로드
        with self.meta_store.get_session() as session:
            from sqlmodel import select

            symbols = [
                s.symbol
                for s in session.exec(
                    select(Symbol).where(Symbol.is_active == True)
                ).all()
            ]

        all_preds = []
        for symbol in symbols:
            df_p = self.series_store.get_predictions(symbol)
            if not df_p.empty:
                df_expert = df_p[df_p["task_id"] == "expert_ensemble"]
                if not df_expert.empty:
                    all_preds.append(df_expert)
                else:
                    all_preds.append(df_p[df_p["task_id"] == "daily_pred"])

        if not all_preds:
            return

        df_all = pd.concat(all_preds)
        df_all["date"] = pd.to_datetime(df_all["date"])

        mask = (df_all["date"] >= pd.to_datetime(start_date)) & (
            df_all["date"] <= pd.to_datetime(end_date)
        )
        df_filtered = df_all[mask]

        dates = sorted(df_filtered["date"].unique())
        log.info(f"Backfilling recommendations for {len(dates)} days...")

        for d in dates:
            self.generate_recommendation(date=d, top_k=top_k)
