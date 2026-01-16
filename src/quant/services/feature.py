import logging
import pandas as pd
from typing import List, Optional

from quant.db.timeseries import SeriesStore
from quant.db.metastore import MetaStore
from quant.features.definitions import compute_basic_features
from quant.models import Symbol

log = logging.getLogger(__name__)


class FeatureService:
    def __init__(
        self,
        series_store: Optional[SeriesStore] = None,
        meta_store: Optional[MetaStore] = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()

    def compute_all_features(
        self,
        symbols: Optional[List[str]] = None,
        version: str = "v1",
        winsorize: bool = False,
        winsorize_limits: Optional[List[float]] = None,
    ):
        """
        심볼 목록에 대해 특징량을 계산하고 저장합니다.
        symbols가 None이면 활성화된 모든 심볼을 대상으로 합니다.
        """
        if symbols is None:
            with self.meta_store.get_session() as session:
                from sqlmodel import select

                statement = select(Symbol).where(Symbol.is_active == True)
                active_symbols = session.exec(statement).all()
                symbols = [s.symbol for s in active_symbols]

        for symbol in symbols:
            log.info(f"Computing features for {symbol} (version={version})...")
            try:
                # 1. OHLCV 로드
                df_ohlcv = self.series_store.get_ohlcv(symbol, frequency="daily")
                if df_ohlcv.empty:
                    log.warning(f"No OHLCV data found for {symbol}. Skipping.")
                    continue

                # 2. 특징량 계산
                df_features = compute_basic_features(df_ohlcv)
                if df_features.empty:
                    log.warning(
                        f"Feature computation returned empty for {symbol}. Skipping."
                    )
                    continue

                # 3. Winsorization (Optional)
                if winsorize:
                    df_features = self.apply_winsorization(
                        df_features, limits=winsorize_limits
                    )
                    log.info(f"Applied winsorization to features for {symbol}.")

                # 3. 저장
                self.series_store.save_features(df_features, symbol, version=version)
                log.info(f"Successfully saved features for {symbol}.")

            except Exception as e:
                log.error(f"Error computing features for {symbol}: {e}")

    def get_feature_data(self, symbol: str, version: str = "v1") -> pd.DataFrame:
        """저장된 특징량 데이터를 조회합니다."""
        return self.series_store.get_features(symbol, version=version)

    def apply_winsorization(
        self, df: pd.DataFrame, limits: Optional[List[float]] = None
    ) -> pd.DataFrame:
        """
        데이터프레임의 각 컬럼에 대해 Winsorization을 적용합니다.
        limits: [lower_percentile, upper_percentile] (e.g. [0.01, 0.01] for 1% and 99%)
        """
        if limits is None:
            limits = [0.01, 0.01]

        lower_limit, upper_limit = limits[0], limits[1]
        df_winsorized = df.copy()

        # feature_* 컬럼만 적용하거나, 모든 숫자형 컬럼에 적용
        # 여기서는 인덱스(date) 제외한 모든 숫자형 컬럼 대상
        cols = df_winsorized.select_dtypes(include=["number"]).columns

        for col in cols:
            lower_bound = df_winsorized[col].quantile(lower_limit)
            upper_bound = df_winsorized[col].quantile(1.0 - upper_limit)
            df_winsorized[col] = df_winsorized[col].clip(
                lower=lower_bound, upper=upper_bound
            )

        return df_winsorized
