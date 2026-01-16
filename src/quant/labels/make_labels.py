import pandas as pd
import numpy as np


def compute_labels(df: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
    """
    OHLCV DataFrame을 입력받아 미래 N일 수익률(레이블)을 계산합니다.
    df index: date
    columns: close
    """
    if df.empty:
        return pd.DataFrame()

    labels = pd.DataFrame(index=df.index)
    close = df["close"]

    # 1. 미래 N일 수익률 (Forward Return)
    # shift(-horizon)으로 미래 가격을 현재 시점으로 당겨옴
    fwd_close = close.shift(-horizon)
    labels[fwd_ret_name := f"fwd_ret_{horizon}d"] = (fwd_close - close) / close

    # 2. 방향성 레이블 (Direction)
    labels[fwd_dir_name := f"direction_{horizon}d"] = (labels[fwd_ret_name] > 0).astype(
        float
    )

    # 마지막 horizon 기간은 미래 데이터가 없으므로 NaN이 됨
    # ML 학습 시에는 어차피 dropna 처리되거나 제외됨

    return labels
