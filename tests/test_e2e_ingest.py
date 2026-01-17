import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

import shutil
import subprocess

import duckdb
import pytest

from quant.config import settings

if os.getenv("RUN_E2E") != "1":
    pytest.skip("E2E ingest test is opt-in (set RUN_E2E=1)", allow_module_level=True)

if shutil.which("uv") is None:
    pytest.skip("E2E ingest test requires 'uv' in PATH", allow_module_level=True)

if not os.getenv("ALPHA_VANTAGE_API_KEY") and not getattr(
    settings, "alpha_vantage_api_key", None
):
    pytest.skip(
        "E2E ingest test requires Alpha Vantage API key (ALPHA_VANTAGE_API_KEY)",
        allow_module_level=True,
    )


def test_e2e_flow():
    # 1. Initialize DBs
    print("Initializing DBs...")
    subprocess.run(
        ["uv", "run", "quant", "init-db"],
        check=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    # 2. Register Symbol
    print("Registering Symbol AAPL...")
    subprocess.run(
        ["uv", "run", "quant", "symbol-register", "AAPL"],
        check=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    # 3. Run Ingest
    print("Running Ingest...")
    subprocess.run(
        ["uv", "run", "quant", "ingest"],
        check=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    # 4. Verify DuckDB
    print("Verifying DuckDB ohlcv rows...")
    # market_data/storage/timeseries.py default path vs quant settings path check
    # LocalMarketDataClient is initialized in SymbolRepo/cli without explicit db_path in some places
    # We should check both if they differ

    # We'll use the one defined in quant settings since MASTER_PLAN says data/quant.duckdb
    db_path = settings.quant_duckdb_path
    conn = duckdb.connect(str(db_path))

    # Check ohlcv table in quant.duckdb
    try:
        count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        print(f"Count in ohlcv: {count}")
        assert count > 0, "OHLCV table should have data after ingest"
        print("✅ E2E Verification Success!")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        # Try checking market_data.duckdb as fallback if they are separate
        fallback_path = "data/market_data.duckdb"
        if os.path.exists(fallback_path):
            print(f"Checking fallback path: {fallback_path}")
            fconn = duckdb.connect(fallback_path)
            fcount = fconn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
            print(f"Count in fallback ohlcv: {fcount}")
            assert fcount > 0, "Fallback OHLCV table should have data"
            print("✅ E2E Verification (Fallback Path) Success!")
        else:
            raise e
    finally:
        conn.close()


if __name__ == "__main__":
    test_e2e_flow()
