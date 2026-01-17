import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..config import settings
from ..db.duck import connect as duck_connect
from .provider import AlphaVantageProvider
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)


class DataIngester:
    def __init__(self, provider: AlphaVantageProvider, db_path: str | None = None):
        self.provider = provider
        self.db_path = db_path or settings.quant_duckdb_path
        self.gate = QualityGate()

    def get_latest_ts(self, symbol: str) -> datetime | None:
        """Get the latest timestamp for a symbol from DuckDB."""
        conn = duck_connect(Path(self.db_path) if isinstance(self.db_path, str) else self.db_path)
        try:
            res = conn.execute(
                "SELECT max(ts) FROM ohlcv WHERE symbol = ?", [symbol]
            ).fetchone()
            return res[0] if res and res[0] else None
        except Exception as e:
            logger.warning(f"Could not get latest ts for {symbol}: {e}")
            return None
        finally:
            conn.close()

    def ingest_symbol(self, symbol: str, force_full: bool = False):
        """
        Ingest OHLCV for a single symbol.
        Handles incremental load by default.
        """
        latest_ts = self.get_latest_ts(symbol)
        outputsize = "compact"

        if not latest_ts or force_full:
            outputsize = "full"
            logger.info(f"Initial ingestion for {symbol} (outputsize=full)")
        else:
            logger.info(f"Incremental ingestion for {symbol} (latest_ts={latest_ts})")

        # 1. Fetch
        df = self.provider.get_daily_ohlcv(symbol, outputsize=outputsize)

        # 1.5. Apply Adjustments (Handle splits/dividends)
        if not df.empty and "adjusted_close" in df.columns:
            logger.info(f"Applying adjustments for {symbol}")
            # Standard back-adjustment: adj_factor = adj_close / close
            # We avoid division by zero just in case
            adj_factor = df["adjusted_close"] / df["close"].replace(0, 1)
            df["open"] = df["open"] * adj_factor
            df["high"] = df["high"] * adj_factor
            df["low"] = df["low"] * adj_factor
            df["close"] = df["close"] * adj_factor  # This should match adjusted_close

        # 2. Validate
        self.gate.validate_ohlcv(df, symbol)

        # 3. Filter incremental
        if latest_ts and not force_full:
            df = df[df.index > pd.Timestamp(latest_ts)]
            if df.empty:
                logger.info(f"No new data for {symbol}")
                return

        # 4. Save to DuckDB
        conn = duck_connect(Path(self.db_path) if isinstance(self.db_path, str) else self.db_path)
        try:
            # DEBUG: What is 'ohlcv' REALLY?
            print(
                f"\n[DEBUG] DESCRIBE ohlcv: {conn.execute('DESCRIBE ohlcv').fetchall()}"
            )
            df = df.reset_index()
            df["symbol"] = symbol
            df["source"] = "alpha_vantage"
            df["ingested_at"] = datetime.now(UTC)

            cols = [
                "symbol",
                "ts",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "adjusted_close",
                "source",
                "ingested_at",
            ]
            df = df[cols]
            # Ensure ts is a date string for DuckDB CSV parser or direct load
            df["ts"] = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%d")
            # Ensure ingested_at is a string
            df["ingested_at"] = pd.to_datetime(df["ingested_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

            # Use a more robust way: Delete matching and Insert
            # We use the pandas dataframe 'df' as a source
            conn.execute("CREATE OR REPLACE TEMPORARY TABLE df_tmp AS SELECT * FROM df")

            # Atomic delete & insert
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    f"DELETE FROM ohlcv WHERE symbol = '{symbol}' AND ts::DATE IN (SELECT ts::DATE FROM df_tmp)"
                )
                conn.execute(
                    "INSERT INTO ohlcv SELECT symbol, ts::DATE, open, high, low, close, volume, adjusted_close, source, ingested_at::TIMESTAMP FROM df_tmp"
                )
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise e

            logger.info(f"Successfully ingested {len(df)} rows for {symbol}")
        finally:
            conn.close()

    def ingest_overview(self, symbol: str):
        """Fetch and save company overview to SQLite."""
        from ..db.metastore import MetaStore
        from ..models.market import CompanyOverview

        logger.info(f"Fetching overview for {symbol}")
        data = self.provider.get_overview(symbol)
        if not data:
            logger.warning(f"No overview data for {symbol}")
            return

        if not data.get("symbol"):
            data["symbol"] = symbol

        store = MetaStore()
        try:
            with store.get_session() as session:
                overview = CompanyOverview(**data)
                session.merge(overview)
                session.commit()
            logger.info(f"Saved overview for {symbol}")
        except Exception as e:
            logger.error(f"Failed to save overview for {symbol}: {e}")

    def ingest_all(self, symbols: list[str]):
        """Ingest multiple symbols."""
        for sym in symbols:
            try:
                self.ingest_symbol(sym)
            except Exception as e:
                logger.error(f"Failed to ingest {sym}: {e}")
                raise e
