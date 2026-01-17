import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from ..config import settings
from ..db.duck import connect as duck_connect

logger = logging.getLogger(__name__)


class FeatureCalculator:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.quant_duckdb_path

    def load_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Load OHLCV data from DuckDB."""
        conn = duck_connect(self.db_path)
        try:
            # We use a simple select. DuckDB handles the date conversion to pandas well,
            # but we explicitly sort by ts.
            query = f"SELECT * FROM ohlcv WHERE symbol = '{symbol}' ORDER BY ts"
            df = conn.execute(query).df()
            if not df.empty:
                df["ts"] = pd.to_datetime(df["ts"])
                df = df.set_index("ts")
            return df
        finally:
            conn.close()

    def calculate_v1_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate v1 feature set.
        - returns: ret_1d, ret_5d, ret_20d, ret_60d
        - volatility: vol_20d (rolling std of ret_1d)
        - gap: gap_open ((open - prev_close) / prev_close)
        - range: hl_range ((high - low) / close)
        - volume: volume_ratio_20d (volume / volume_avg_20d)
        """
        if df.empty:
            return pd.DataFrame()

        df = df.sort_index()
        feat_df = pd.DataFrame(index=df.index)

        # 1. Returns
        feat_df["ret_1d"] = df["close"].pct_change(1)
        feat_df["ret_5d"] = df["close"].pct_change(5)
        feat_df["ret_20d"] = df["close"].pct_change(20)
        feat_df["ret_60d"] = df["close"].pct_change(60)

        # 2. Volatility
        feat_df["vol_20d"] = feat_df["ret_1d"].rolling(20).std()

        # 3. Gap
        prev_close = df["close"].shift(1)
        feat_df["gap_open"] = (df["open"] - prev_close) / prev_close

        # 4. Range
        # Using close as denominator for normalization
        feat_df["hl_range"] = (df["high"] - df["low"]) / df["close"]

        # 5. Volume Ratio
        vol_avg = df["volume"].rolling(20).mean()
        # Avoid division by zero
        feat_df["volume_ratio_20d"] = df["volume"] / vol_avg.replace(0, np.nan)

        return feat_df

    def save_features(self, symbol: str, df_features: pd.DataFrame, version: str):
        """
        Save features in long-form to DuckDB.
        """
        if df_features.empty:
            return

        # Quality Gate: Drop NaNs (Calculated from windows)
        original_len = len(df_features)
        df_features = df_features.dropna()
        dropped_len = original_len - len(df_features)
        if dropped_len > 0:
            logger.debug(f"Dropped {dropped_len} NaN rows for {symbol}")

        if df_features.empty:
            logger.warning(f"No valid features after dropping NaNs for {symbol}")
            return

        # Transform to long-form
        # symbol, ts, feature_name, feature_value, feature_version, computed_at
        df_long = df_features.reset_index().melt(
            id_vars=["ts"], var_name="feature_name", value_name="feature_value"
        )
        df_long["symbol"] = symbol
        df_long["feature_version"] = version
        df_long["computed_at"] = datetime.now(UTC)

        # Ensure correct column order
        cols = [
            "symbol",
            "ts",
            "feature_name",
            "feature_value",
            "feature_version",
            "computed_at",
        ]
        df_long = df_long[cols]

        # Convert types for DuckDB stability
        df_long["ts"] = df_long["ts"].dt.strftime("%Y-%m-%d")
        df_long["computed_at"] = df_long["computed_at"].dt.strftime("%Y-%m-%d %H:%M:%S")

        conn = duck_connect(self.db_path)
        try:
            # Register pandas DF
            conn.register("df_tmp", df_long)

            # Atomic Delete & Insert (Upsert)
            conn.execute("BEGIN TRANSACTION")
            try:
                # Use explicit DELETE to handle overlap safely
                conn.execute(
                    f"""
                    DELETE FROM features_daily 
                    WHERE symbol = '{symbol}' 
                      AND feature_version = '{version}'
                      AND ts::DATE IN (SELECT ts::DATE FROM df_tmp)
                """
                )
                conn.execute(
                    """
                    INSERT INTO features_daily 
                    (symbol, ts, feature_name, feature_value, feature_version, computed_at)
                    SELECT 
                        symbol, ts::DATE, feature_name, feature_value, feature_version, computed_at::TIMESTAMP 
                    FROM df_tmp
                """
                )
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise e

            logger.debug(
                f"Successfully saved {len(df_long)} feature rows for {symbol} (version={version})"
            )
        finally:
            conn.close()

    def run_for_symbol(self, symbol: str, version: str = "v1"):
        """Run the full calculation and save pipeline for a symbol."""
        logger.debug(f"Calculating features for {symbol} (version={version})")
        df_ohlcv = self.load_ohlcv(symbol)
        if df_ohlcv.empty:
            logger.warning(f"No OHLCV data found for {symbol}")
            return

        df_features = self.calculate_v1_features(df_ohlcv)
        self.save_features(symbol, df_features, version)
