import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Optional
from ..db.duck import connect as duck_connect
from ..config import settings

logger = logging.getLogger(__name__)


class LabelCalculator:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.quant_duckdb_path

    def load_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Load OHLCV data from DuckDB."""
        conn = duck_connect(self.db_path)
        try:
            query = f"SELECT * FROM ohlcv WHERE symbol = '{symbol}' ORDER BY ts"
            df = conn.execute(query).df()
            if not df.empty:
                df["ts"] = pd.to_datetime(df["ts"])
                df = df.set_index("ts")
            return df
        finally:
            conn.close()

    def calculate_v1_labels(self, df: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
        """
        Calculate v1 labels.
        - fwd_ret_N: (close.shift(-N) - close) / close
        - direction_N: 1 if fwd_ret_N > 0 else 0
        """
        if df.empty:
            return pd.DataFrame()

        df = df.sort_index()
        label_df = pd.DataFrame(index=df.index)

        # 1. Forward Return
        # Negative shift looks forward in time
        fwd_close = df["close"].shift(-horizon)
        label_name = f"fwd_ret_{horizon}d"
        label_df[label_name] = (fwd_close - df["close"]) / df["close"]

        # 2. Direction
        dir_name = f"direction_{horizon}d"
        # We handle NaN explicitly to avoid (NaN > 0) -> False (0.0) which is misleading
        label_df[dir_name] = np.nan
        label_df.loc[label_df[label_name] > 0, dir_name] = 1.0
        label_df.loc[label_df[label_name] <= 0, dir_name] = 0.0

        return label_df

    def save_labels(self, symbol: str, df_labels: pd.DataFrame, version: str):
        """
        Save labels in long-form to DuckDB.
        """
        if df_labels.empty:
            return

        # Quality Gate: Drop NaNs (Calculated from future shift)
        original_len = len(df_labels)
        df_labels = df_labels.dropna()
        dropped_len = original_len - len(df_labels)
        if dropped_len > 0:
            logger.debug(f"Dropped {dropped_len} NaN rows for {symbol} (future window)")

        if df_labels.empty:
            logger.warning(f"No valid labels after dropping NaNs for {symbol}")
            return

        # Transform to long-form
        # symbol, ts, label_name, label_value, label_version
        df_long = df_labels.reset_index().melt(
            id_vars=["ts"], var_name="label_name", value_name="label_value"
        )
        df_long["symbol"] = symbol
        df_long["label_version"] = version

        # Ensure correct column order
        cols = ["symbol", "ts", "label_name", "label_value", "label_version"]
        df_long = df_long[cols]

        # Convert ts to string for DuckDB
        df_long["ts"] = df_long["ts"].dt.strftime("%Y-%m-%d")

        conn = duck_connect(self.db_path)
        try:
            # Register pandas DF
            conn.register("df_tmp", df_long)

            # Atomic Delete & Insert (Upsert)
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    f"""
                    DELETE FROM labels 
                    WHERE symbol = '{symbol}' 
                      AND label_version = '{version}'
                      AND ts::DATE IN (SELECT ts::DATE FROM df_tmp)
                """
                )
                conn.execute(
                    """
                    INSERT INTO labels (symbol, ts, label_name, label_value, label_version)
                    SELECT symbol, ts::DATE, label_name, label_value, label_version FROM df_tmp
                """
                )
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise e

            logger.info(
                f"Successfully saved {len(df_long)} label rows for {symbol} (version={version})"
            )
        finally:
            conn.close()

    def run_for_symbol(self, symbol: str, version: str = "v1", horizon: int = 60):
        """Run the full calculation and save pipeline for a symbol."""
        logger.info(
            f"Calculating labels for {symbol} (version={version}, horizon={horizon})"
        )
        df_ohlcv = self.load_ohlcv(symbol)
        if df_ohlcv.empty:
            logger.warning(f"No OHLCV data found for {symbol}")
            return

        df_labels = self.calculate_v1_labels(df_ohlcv, horizon)
        self.save_labels(symbol, df_labels, version)
