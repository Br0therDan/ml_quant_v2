import logging

import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when data fails quality validation."""

    pass


class QualityGate:
    @staticmethod
    def validate_ohlcv(df: pd.DataFrame, symbol: str) -> bool:
        """
        Validate OHLCV data for basic sanity.
        """
        if df.empty:
            raise DataQualityError(f"Empty data received for {symbol}")

        # 1. Essential columns check
        required_cols = ["open", "high", "low", "close", "volume"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise DataQualityError(f"Missing columns for {symbol}: {missing_cols}")

        # 2. NaN check
        if df[required_cols].isnull().any().any():
            nan_count = df[required_cols].isnull().sum().sum()
            logger.warning(f"Detected {nan_count} NaN values in {symbol}")
            # Depending on policy, we could drop them or raise error
            # For now, let's just drop them if it's not too many
            total_rows = len(df)
            if nan_count / (total_rows * len(required_cols)) > 0.05:
                raise DataQualityError(f"Too many NaN values in {symbol}: {nan_count}")

        # 3. Numeric validity (OHLCV > 0)
        # Note: Volume can be 0 in some cases, but OHLC prices should be > 0
        price_cols = ["open", "high", "low", "close"]
        if (df[price_cols] <= 0).any().any():
            invalid_rows = df[(df[price_cols] <= 0).any(axis=1)]
            logger.warning(
                f"Invalid price detected (<= 0) for {symbol}: {len(invalid_rows)} rows"
            )
            # Usually we don't want to stop everything for one bad tick, but let's log it.
            # For strict mode: raise DataQualityError(...)

        # 4. Duplicate TS check
        if df.index.duplicated().any():
            raise DataQualityError(f"Duplicate timestamps detected for {symbol}")

        return True
