import pandas as pd
import numpy as np
import logging

log = logging.getLogger(__name__)


def detect_market_regime(
    df_ohlcv: pd.DataFrame, fast_period: int = 20, slow_period: int = 60
) -> pd.Series:
    """
    이동평균선(SMA) 골든/데드크로스를 기반으로 시장 국면을 진단합니다.
    1.0: Bull (Fast > Slow)
    -1.0: Bear (Fast <= Slow)
    """
    if df_ohlcv.empty:
        return pd.Series()

    close = df_ohlcv["close"]
    sma_fast = close.rolling(window=fast_period).mean()
    sma_slow = close.rolling(window=slow_period).mean()

    # 1.0 for Bull, -1.0 for Bear
    regime = np.where(sma_fast > sma_slow, 1.0, -1.0)

    return pd.Series(regime, index=df_ohlcv.index, name="regime")


def get_regime_label(value: float) -> str:
    """수치형 regime 값을 문자열 라벨로 변환합니다."""
    return "bull" if value > 0 else "bear"
