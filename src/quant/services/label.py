import logging
import pandas as pd
from typing import List, Optional

from quant.db.timeseries import SeriesStore
from quant.db.metastore import MetaStore
from quant.labels.make_labels import compute_labels
from quant.models import Symbol

log = logging.getLogger(__name__)


class LabelService:
    def __init__(
        self,
        series_store: Optional[SeriesStore] = None,
        meta_store: Optional[MetaStore] = None,
    ):
        self.series_store = series_store or SeriesStore()
        self.meta_store = meta_store or MetaStore()

    def compute_all_labels(
        self,
        symbols: Optional[List[str]] = None,
        horizon: int = 60,
        version: str = "v1",
    ):
        """
        심볼 목록에 대해 레이블을 계산하고 저장합니다.
        """
        if symbols is None:
            with self.meta_store.get_session() as session:
                from sqlmodel import select

                statement = select(Symbol).where(Symbol.is_active == True)
                active_symbols = session.exec(statement).all()
                symbols = [s.symbol for s in active_symbols]

        for symbol in symbols:
            log.info(
                f"Computing labels for {symbol} (horizon={horizon}, version={version})..."
            )
            try:
                # 1. OHLCV 로드
                df_ohlcv = self.series_store.get_ohlcv(symbol, frequency="daily")
                if df_ohlcv.empty:
                    log.warning(f"No OHLCV data found for {symbol}. Skipping.")
                    continue

                # 2. 레이블 계산
                df_labels = compute_labels(df_ohlcv, horizon=horizon)
                if df_labels.empty:
                    log.warning(
                        f"Label computation returned empty for {symbol}. Skipping."
                    )
                    continue

                # 3. 저장
                self.series_store.save_labels(df_labels, symbol, version=version)
                log.info(f"Successfully saved labels for {symbol}.")

            except Exception as e:
                log.error(f"Error computing labels for {symbol}: {e}")

    def get_label_data(self, symbol: str, version: str = "v1") -> pd.DataFrame:
        """저장된 레이블 데이터를 조회합니다."""
        return self.series_store.get_labels(symbol, version=version)
