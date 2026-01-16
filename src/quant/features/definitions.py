import pandas as pd
import numpy as np


def compute_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCV DataFrame을 입력받아 기본 특징량을 계산합니다.
    df index: date
    columns: open, high, low, close, volume
    """
    if df.empty:
        return pd.DataFrame()

    feat = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1. Momentum (Returns)
    feat["ret_1d"] = close.pct_change(1)
    feat["ret_5d"] = close.pct_change(5)
    feat["ret_20d"] = close.pct_change(20)
    feat["ret_60d"] = close.pct_change(60)

    # 2. Volatility
    feat["vol_20d"] = feat["ret_1d"].rolling(20).std()

    # ATR (Simplified)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    feat["atr_14d"] = tr.rolling(14).mean() / close  # Normalizing by price

    # 3. Trend (Moving Average)
    feat["ma_ratio_20_60"] = close.rolling(20).mean() / close.rolling(60).mean()
    feat["close_ma_20_ratio"] = close / close.rolling(20).mean()

    # 4. Intraday Range & Gap
    feat["day_range_pct"] = (high - low) / close
    feat["gap_pct"] = (df["open"] - close.shift(1)) / close.shift(1)

    # 5. Volume
    feat["volume_ratio_20d"] = volume / volume.rolling(20).median().replace(0, np.nan)

    # 6. RSI (Relative Strength Index)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    feat["rsi_14d"] = 100 - (100 / (1 + rs))

    # Drop NaNs created by rolling windows if needed,
    # but service layer can handle it (maybe keep them for continuity)
    return feat
