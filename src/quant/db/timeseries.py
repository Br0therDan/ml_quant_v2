import os
from datetime import datetime

import duckdb
import pandas as pd
from typing import Optional

from quant.config import settings

# Use paths from quant settings
DB_PATH = settings.quant_duckdb_path


class SeriesStore:
    def __init__(self, db_path: str = DB_PATH, read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only
        self._table_columns_cache: dict[str, set[str]] = {}
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = duckdb.connect(self.db_path, read_only=read_only)
        if not read_only:
            self._init_db()

    def _get_table_columns(self, table_name: str) -> set[str]:
        cached = self._table_columns_cache.get(table_name)
        if cached is not None:
            return cached
        try:
            rows = self.conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        except Exception:
            cols: set[str] = set()
        else:
            cols = {r[1] for r in rows}
        self._table_columns_cache[table_name] = cols
        return cols

    def _get_date_column(self, table_name: str) -> str:
        cols = self._get_table_columns(table_name)
        if "date" in cols:
            return "date"
        if "ts" in cols:
            return "ts"
        return "date"

    def close(self):
        """Close the DuckDB connection."""
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_db(self):
        """
        [V2 Compatibility Notice]
        Automatic table creation/dropping is disabled in V1 to prevent interference with V2 schemas.
        V2 tables are managed by 'quant init-db'.
        """
        pass

    def save_ohlcv(
        self,
        df: pd.DataFrame,
        symbol: str,
        frequency: str,
        asset_type: str = "Equity",
        currency: str = "USD",
    ):
        # Expects DataFrame with index as Date or 'date' column
        if df.empty:
            return

        df = df.copy()
        if "date" not in df.columns:
            df = df.reset_index()

        # Robust Column Renaming for various Alpha Vantage formats (Equity, Crypto, Forex)
        # Examples: "1. open", "1a. open (USD)", "4. close", "4b. close (USD)", "5. adjusted close"
        new_cols = {}
        target_mappings = {
            "open": ["open"],
            "high": ["high"],
            "low": ["low"],
            "close": ["adjusted close", "close"],
            "volume": ["volume"],
        }

        for target, keywords in target_mappings.items():
            for kw in keywords:
                # Find first column that contains the keyword
                match = next((c for c in df.columns if kw in str(c).lower()), None)
                if match:
                    new_cols[match] = target
                    break

        df = df.rename(columns=new_cols)

        # Drop columns that weren't renamed and aren't 'date'
        # (e.g. "1b. open (Market)", "2b. high (Market)" etc in Crypto)
        keep_cols = list(new_cols.values()) + ["date"]
        df = df[[c for c in df.columns if c in keep_cols]]

        if df.empty:
            return

        # Prepare for bulk insert
        # We expect df index to be 'date'

        # Add metadata columns
        df_save = df.copy()
        df_save["symbol"] = symbol
        df_save["frequency"] = frequency
        df_save["currency"] = currency
        df_save["type"] = asset_type
        df_save["updated_at"] = datetime.now()

        # Ensure all required storage columns exist
        if "volume" not in df_save.columns:
            df_save["volume"] = 0.0

        # Ensure column order matches table (frequency, symbol, date, open, high, low, close, volume, type, updated_at)
        # Note: df index is date. reset_index() makes it a column.
        df_save = df_save.reset_index()  # date is now a col

        # Select and reorder
        # Need to handle case where columns might ideally be named differently or just trust name matching?
        # DuckDB register method is robust.

        cols = [
            "frequency",
            "symbol",
            "currency",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "type",
            "updated_at",
        ]
        df_final = df_save[cols]

        # Register as view then insert
        self.conn.register("df_view", df_final)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO ohlcv
            (frequency, symbol, currency, date, open, high, low, close, volume, type, updated_at)
            SELECT frequency, symbol, currency, date, open, high, low, close, volume, type, updated_at FROM df_view
        """
        )
        self.conn.unregister("df_view")

    def get_ohlcv(
        self, symbol: str, frequency: str = "daily", currency: str = "USD"
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        cols = self._get_table_columns("ohlcv")
        date_col = self._get_date_column("ohlcv")

        where_clauses = ["symbol = ?"]
        params: list[object] = [symbol]

        if "frequency" in cols:
            where_clauses.append("frequency = ?")
            params.append(frequency)
        if "currency" in cols:
            where_clauses.append("currency = ?")
            params.append(currency)

        query = f"SELECT * FROM ohlcv WHERE {' AND '.join(where_clauses)} ORDER BY {date_col}"
        df = self.conn.execute(query, params).df()

        if not df.empty:
            if "date" not in df.columns and "ts" in df.columns:
                df = df.rename(columns={"ts": "date"})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df

    def get_latest_date(
        self, symbol: str, frequency: str = "daily", currency: str = "USD"
    ) -> datetime | None:
        symbol = symbol.upper()
        cols = self._get_table_columns("ohlcv")
        date_col = self._get_date_column("ohlcv")

        where_clauses = ["symbol = ?"]
        params: list[object] = [symbol]

        if "frequency" in cols:
            where_clauses.append("frequency = ?")
            params.append(frequency)
        if "currency" in cols:
            where_clauses.append("currency = ?")
            params.append(currency)

        query = f"SELECT MAX({date_col}) FROM ohlcv WHERE {' AND '.join(where_clauses)}"
        res = self.conn.execute(query, params).fetchone()
        return res[0] if res else None

    def get_coverage_stats(self, frequency: str = "daily") -> pd.DataFrame:
        """
        Get min date, max date, and count for all symbols.
        Returns DF with columns: symbol, currency, start_date, end_date, count
        """
        cols = self._get_table_columns("ohlcv")
        date_col = self._get_date_column("ohlcv")

        select_currency = (
            "currency" if "currency" in cols else "NULL::VARCHAR as currency"
        )
        where_clause = "WHERE frequency = ?" if "frequency" in cols else ""
        params = [frequency] if "frequency" in cols else []

        query = f"""
            SELECT
                symbol,
                {select_currency},
                MIN({date_col}) as start_date,
                MAX({date_col}) as end_date,
                COUNT(*) as count
            FROM ohlcv
            {where_clause}
            GROUP BY symbol, currency
        """
        df = self.conn.execute(query, params).df()
        if not df.empty:
            df["start_date"] = pd.to_datetime(df["start_date"])
            df["end_date"] = pd.to_datetime(df["end_date"])
        return df

    def get_coverage_details(self) -> pd.DataFrame:
        """
        Get coverage stats (start, end, count) grouped by symbol AND frequency.
        """
        cols = self._get_table_columns("ohlcv")
        date_col = self._get_date_column("ohlcv")
        select_frequency = (
            "frequency" if "frequency" in cols else "NULL::VARCHAR as frequency"
        )
        select_currency = (
            "currency" if "currency" in cols else "NULL::VARCHAR as currency"
        )
        select_updated_at = (
            "MAX(updated_at) as updated_at"
            if "updated_at" in cols
            else "NULL::TIMESTAMP as updated_at"
        )

        query = f"""
            SELECT
                symbol,
                {select_frequency},
                {select_currency},
                MIN({date_col}) as start_date,
                MAX({date_col}) as end_date,
                COUNT(*) as count,
                {select_updated_at}
            FROM ohlcv
            GROUP BY symbol, frequency, currency
        """
        df = self.conn.execute(query).df()
        if not df.empty:
            df["start_date"] = pd.to_datetime(df["start_date"])
            df["end_date"] = pd.to_datetime(df["end_date"])
        return df

    def save_commodity(self, df: pd.DataFrame, symbol: str, frequency: str = "monthly"):
        if df.empty:
            return

        df_save = df.copy()
        df_save["symbol"] = symbol
        df_save["frequency"] = frequency
        df_save["updated_at"] = datetime.now()
        df_save = df_save.reset_index()  # date

        cols = ["symbol", "frequency", "date", "value", "updated_at"]
        # Ensure value exists (AV returns 'value')

        df_final = df_save[cols]

        self.conn.register("comm_view", df_final)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO commodities
            (symbol, frequency, date, value, updated_at)
            SELECT symbol, frequency, date, value, updated_at FROM comm_view
        """
        )
        self.conn.unregister("comm_view")

    def get_commodity(self, symbol: str, frequency: str = "monthly") -> pd.DataFrame:
        query = f"SELECT * FROM commodities WHERE symbol = '{symbol}' AND frequency = '{frequency}' ORDER BY date"
        df = self.conn.execute(query).df()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        return df

    def save_features(self, df: pd.DataFrame, symbol: str, version: str = "v1"):
        """
        Save features to DuckDB.
        Handles both wide-form and long-form DataFrames.
        """
        if df.empty:
            return

        df_save = df.copy()

        # Ensure 'date' is a column and correctly named
        if "date" not in df_save.columns:
            df_save.index.name = "date"
            df_save = df_save.reset_index()

        # Melt wide form to long form if necessary
        if "feature_name" not in df_save.columns:
            id_vars = ["date"]
            # Exclude symbol if it exists as a column already
            val_vars = [c for c in df_save.columns if c not in ["date", "symbol"]]
            df_save = df_save.melt(
                id_vars=id_vars,
                value_vars=val_vars,
                var_name="feature_name",
                value_name="feature_value",
            )

        # Drop NaNs - features often have NaNs due to rolling windows
        df_save = df_save.dropna(subset=["feature_value"])
        if df_save.empty:
            return

        symbol = symbol.upper()
        table_cols = self._get_table_columns("features_daily")
        date_col = self._get_date_column("features_daily")

        # Add mandatory columns
        df_save["symbol"] = symbol
        df_save["feature_version"] = version
        if "computed_at" in table_cols:
            df_save["computed_at"] = datetime.now()

        if date_col != "date" and "date" in df_save.columns:
            df_save = df_save.rename(columns={"date": date_col})

        cols = [
            "symbol",
            date_col,
            "feature_name",
            "feature_value",
            "feature_version",
        ]
        if "computed_at" in table_cols:
            cols.append("computed_at")
        df_final = df_save[cols]

        self.conn.register("df_view", df_final)
        col_list = ", ".join(cols)
        try:
            self.conn.execute(
                f"INSERT OR REPLACE INTO features_daily ({col_list}) SELECT {col_list} FROM df_view"
            )
        except Exception:
            set_clauses = ["feature_value = EXCLUDED.feature_value"]
            if "computed_at" in table_cols:
                set_clauses.append("computed_at = EXCLUDED.computed_at")
            conflict_cols = ", ".join(
                ["symbol", date_col, "feature_name", "feature_version"]
            )
            self.conn.execute(
                f"""
                INSERT INTO features_daily ({col_list}) SELECT {col_list} FROM df_view
                ON CONFLICT ({conflict_cols})
                DO UPDATE SET {', '.join(set_clauses)}
            """
            )
        finally:
            self.conn.unregister("df_view")

    def get_features(self, symbol: str, version: str = "v1") -> pd.DataFrame:
        """Returns wide-form features for a symbol."""
        symbol = symbol.upper()
        date_col = self._get_date_column("features_daily")
        query = f"SELECT * FROM features_daily WHERE symbol = ? AND feature_version = ? ORDER BY {date_col}"
        df = self.conn.execute(query, [symbol, version]).df()
        if df.empty:
            return df

        if "date" not in df.columns and "ts" in df.columns:
            df = df.rename(columns={"ts": "date"})

        # Pivot to wide form
        df_pivot = df.pivot(
            index="date", columns="feature_name", values="feature_value"
        )
        return df_pivot

    def save_labels(self, df: pd.DataFrame, symbol: str, version: str = "v1"):
        """
        Save labels to DuckDB.
        Handles both wide-form and long-form DataFrames.
        """
        if df.empty:
            return

        df_save = df.copy()

        # Ensure 'date' is a column and correctly named
        if "date" not in df_save.columns:
            df_save.index.name = "date"
            df_save = df_save.reset_index()

        # Melt wide form to long form if necessary
        if "label_name" not in df_save.columns:
            id_vars = ["date"]
            # Exclude symbol if it exists as a column already
            val_vars = [c for c in df_save.columns if c not in ["date", "symbol"]]
            df_save = df_save.melt(
                id_vars=id_vars,
                value_vars=val_vars,
                var_name="label_name",
                value_name="label_value",
            )

        # Drop NaNs
        df_save = df_save.dropna(subset=["label_value"])
        if df_save.empty:
            return

        symbol = symbol.upper()
        table_cols = self._get_table_columns("labels")
        date_col = self._get_date_column("labels")

        # Add mandatory columns
        df_save["symbol"] = symbol
        df_save["label_version"] = version
        if "computed_at" in table_cols:
            df_save["computed_at"] = datetime.now()

        if date_col != "date" and "date" in df_save.columns:
            df_save = df_save.rename(columns={"date": date_col})

        cols = [
            "symbol",
            date_col,
            "label_name",
            "label_value",
            "label_version",
        ]
        if "computed_at" in table_cols:
            cols.append("computed_at")
        df_final = df_save[cols]

        self.conn.register("df_view", df_final)
        col_list = ", ".join(cols)
        try:
            self.conn.execute(
                f"INSERT OR REPLACE INTO labels ({col_list}) SELECT {col_list} FROM df_view"
            )
        except Exception:
            set_clauses = ["label_value = EXCLUDED.label_value"]
            if "computed_at" in table_cols:
                set_clauses.append("computed_at = EXCLUDED.computed_at")
            conflict_cols = ", ".join(
                ["symbol", date_col, "label_name", "label_version"]
            )
            self.conn.execute(
                f"""
                INSERT INTO labels ({col_list}) SELECT {col_list} FROM df_view
                ON CONFLICT ({conflict_cols})
                DO UPDATE SET {', '.join(set_clauses)}
            """
            )
        finally:
            self.conn.unregister("df_view")

    def get_labels(self, symbol: str, version: str = "v1") -> pd.DataFrame:
        """Returns wide-form labels for a symbol."""
        symbol = symbol.upper()
        date_col = self._get_date_column("labels")
        query = f"SELECT * FROM labels WHERE symbol = ? AND label_version = ? ORDER BY {date_col}"
        df = self.conn.execute(query, [symbol, version]).df()
        if df.empty:
            return df

        if "date" not in df.columns and "ts" in df.columns:
            df = df.rename(columns={"ts": "date"})

        df_pivot = df.pivot(index="date", columns="label_name", values="label_value")
        return df_pivot

    def save_predictions(self, df: pd.DataFrame):
        """
        Save predictions to DuckDB.
        Expects df with columns: [symbol, date, model_id, task_id, score]
        """
        if df.empty:
            return

        df_save = df.copy()
        if "date" not in df_save.columns:
            df_save.index.name = "date"
            df_save = df_save.reset_index()

        df_save["generated_at"] = datetime.now()

        # Ensure correct column order
        cols = ["symbol", "date", "model_id", "task_id", "score", "generated_at"]
        df_final = df_save[cols]

        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO predictions SELECT * FROM df_final"
            )
        except Exception:
            self.conn.execute(
                """
                INSERT INTO predictions SELECT * FROM df_final
                ON CONFLICT (symbol, date, model_id, task_id)
                DO UPDATE SET 
                    score = EXCLUDED.score,
                    generated_at = EXCLUDED.generated_at
            """
            )

    def get_predictions(
        self, symbol: str, model_id: Optional[str] = None
    ) -> pd.DataFrame:
        """Returns predictions for a symbol."""
        query = f"SELECT * FROM predictions WHERE symbol = '{symbol}'"
        if model_id:
            query += f" AND model_id = '{model_id}'"
        query += " ORDER BY date"

        return self.conn.execute(query).df()

    def save_portfolio_decisions(self, df: pd.DataFrame):
        """
        Save portfolio decisions (weights) to DuckDB.
        Expects df with columns: [date, symbol, weight, score, model_id]
        """
        if df.empty:
            return

        df_save = df.copy()
        df_save["decision_at"] = datetime.now()

        # Ensure correct column order
        cols = ["date", "symbol", "weight", "score", "model_id", "decision_at"]
        df_final = df_save[cols]

        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO portfolio_decisions SELECT * FROM df_final"
            )
        except Exception:
            self.conn.execute(
                """
                INSERT INTO portfolio_decisions SELECT * FROM df_final
                ON CONFLICT (date, symbol)
                DO UPDATE SET 
                    weight = EXCLUDED.weight,
                    score = EXCLUDED.score,
                    model_id = EXCLUDED.model_id,
                    decision_at = EXCLUDED.decision_at
            """
            )

    def get_portfolio_decisions(self, date_str: Optional[str] = None) -> pd.DataFrame:
        """Returns portfolio decisions, optionally filtered by date."""
        query = "SELECT * FROM portfolio_decisions"
        if date_str:
            query += f" WHERE CAST(date AS DATE) = '{date_str}'"
        query += " ORDER BY date DESC, weight DESC"

        return self.conn.execute(query).df()

    def save_backtest_summary(self, df: pd.DataFrame):
        """Save backtest summary metrics to DuckDB."""
        if df.empty:
            return

        # Ensure column consistency
        cols = ["run_id", "from_ts", "to_ts", "cagr", "sharpe", "max_dd", "num_trades"]
        df_final = df[cols].copy()
        df_final["created_at"] = datetime.now()

        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO backtest_summary SELECT * FROM df_final"
            )
        except Exception:
            self.conn.execute(
                """
                INSERT INTO backtest_summary SELECT * FROM df_final
                ON CONFLICT (run_id)
                DO UPDATE SET 
                    cagr = EXCLUDED.cagr,
                    sharpe = EXCLUDED.sharpe,
                    max_dd = EXCLUDED.max_dd,
                    num_trades = EXCLUDED.num_trades
            """
            )

    def get_backtest_summary(self, limit: int = 100) -> pd.DataFrame:
        """Returns backtest summaries."""
        return self.conn.execute(
            f"SELECT * FROM backtest_summary ORDER BY created_at DESC LIMIT {limit}"
        ).df()

    def save_backtest_trades(self, df: pd.DataFrame):
        """Save detailed backtest trades to DuckDB."""
        if df.empty:
            return

        cols = ["run_id", "date", "symbol", "action", "price", "weight"]
        df_final = df[cols]

        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO backtest_trades SELECT * FROM df_final"
            )
        except Exception:
            self.conn.execute(
                """
                INSERT INTO backtest_trades SELECT * FROM df_final
                ON CONFLICT (run_id, date, symbol)
                DO UPDATE SET 
                    action = EXCLUDED.action,
                    price = EXCLUDED.price,
                    weight = EXCLUDED.weight
            """
            )

    def save_backtest_equity_curve(self, df: pd.DataFrame):
        """Save daily equity curve results to DuckDB."""
        if df.empty:
            return

        cols = ["run_id", "date", "equity", "daily_return"]
        df_final = df[cols]

        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO backtest_equity_curve SELECT * FROM df_final"
            )
        except Exception:
            self.conn.execute(
                """
                INSERT INTO backtest_equity_curve SELECT * FROM df_final
                ON CONFLICT (run_id, date)
                DO UPDATE SET 
                    equity = EXCLUDED.equity,
                    daily_return = EXCLUDED.daily_return
            """
            )

    def get_equity_curve(self, run_id: str) -> pd.DataFrame:
        """Returns daily equity curve for a run."""
        return self.conn.execute(
            f"SELECT * FROM backtest_equity_curve WHERE run_id = '{run_id}' ORDER BY date"
        ).df()
