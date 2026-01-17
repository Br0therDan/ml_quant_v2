from datetime import datetime, timedelta

import duckdb
import pandas as pd
from rich.console import Console
from rich.table import Table

from quant.backtest_engine.engine import BacktestEngine
from quant.config import settings

console = Console()


def setup_dummy_data(conn, strategy_id: str, start_date: str, days: int):
    """Insert dummy ohlcv and targets for testing."""
    symbols = ["AAPL", "GOOGL"]
    start = pd.to_datetime(start_date)

    # 1. OHLCV
    ohlcv_data = []
    prices = dict.fromkeys(symbols, 100.0)

    # Generate 5 days prior + test range + buffer
    total_days = days + 10
    data_start = start - timedelta(days=5)

    for i in range(total_days):
        date = data_start + timedelta(days=i)
        for s in symbols:
            # Random walk
            prices[s] *= 1 + (i % 2 - 0.5) * 0.02  # +/- 1%
            ohlcv_data.append(
                {
                    "symbol": s,
                    "ts": date,
                    "open": prices[s],
                    "high": prices[s] * 1.01,
                    "low": prices[s] * 0.99,
                    "close": prices[s],
                    "volume": 1000,
                }
            )

    df_ohlcv = pd.DataFrame(ohlcv_data)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ohlcv (symbol VARCHAR, ts DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT)"
    )
    # Clear overlap
    conn.execute(
        f"DELETE FROM ohlcv WHERE ts >= DATE '{data_start.date()}' AND ts <= DATE '{(data_start + timedelta(days=total_days)).date()}'"
    )

    conn.register("df_ohlcv_tmp", df_ohlcv)
    # Explicit columns for safety
    ohlcv_cols = "symbol, ts, open, high, low, close, volume"
    conn.execute(
        f"INSERT INTO ohlcv ({ohlcv_cols}) SELECT {ohlcv_cols} FROM df_ohlcv_tmp"
    )

    # 2. Targets
    targets_data = []
    # Create targets for the test range
    for i in range(days):
        date = start + timedelta(days=i)
        # Toggle weights
        w = 0.5 if i % 2 == 0 else 0.8
        targets_data.append(
            {
                "strategy_id": strategy_id,
                "version": "1.0.0",
                "study_date": date.date(),
                "symbol": "AAPL",
                "weight": w,
                "score": 0.9,
                "approved": True,
                "risk_flags": "[]",
                "generated_at": datetime.now(),
            }
        )
        # Add GOOGL for diversification
        targets_data.append(
            {
                "strategy_id": strategy_id,
                "version": "1.0.0",
                "study_date": date.date(),
                "symbol": "GOOGL",
                "weight": 1.0 - w,
                "score": 0.8,
                "approved": True,
                "risk_flags": "[]",
                "generated_at": datetime.now(),
            }
        )

    df_targets = pd.DataFrame(targets_data)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS targets (strategy_id VARCHAR, version VARCHAR, study_date DATE, symbol VARCHAR, weight DOUBLE, score DOUBLE, approved BOOLEAN, risk_flags VARCHAR, generated_at TIMESTAMP)"
    )

    conn.execute(
        f"DELETE FROM targets WHERE strategy_id = '{strategy_id}' AND study_date >= DATE '{start.date()}' AND study_date <= DATE '{(start + timedelta(days=days)).date()}'"
    )

    conn.register("df_targets_tmp", df_targets)
    # Ensure targets table exists (if not, create it, but we assume it might exist with varying schema so be careful)
    # Ideally we match the schema of the real app.
    # Let's specify columns for targets insert too.
    target_cols = "strategy_id, version, study_date, symbol, weight, score, approved, risk_flags, generated_at"
    conn.execute(
        f"INSERT INTO targets ({target_cols}) SELECT {target_cols} FROM df_targets_tmp"
    )
    console.print(
        f"[green]Inserted {len(df_ohlcv)} OHLCV rows and {len(df_targets)} Targets[/green]"
    )


def verify_p5():
    console.print(
        "[bold cyan]Phase P5 Verification Script (Self-Contained)[/bold cyan]"
    )

    db_path = settings.quant_duckdb_path
    conn = duckdb.connect(db_path)

    strategy_id = "p5_test_strat"
    start_date = "2025-01-01"
    days = 5

    try:
        setup_dummy_data(conn, strategy_id, start_date, days)
    finally:
        conn.close()

    # 1. Backtest Execution
    strategy_config = {
        "strategy_id": strategy_id,
        "version": "1.0.0",
        "backtest": {"fee_bps": 5, "slippage_bps": 5},
    }

    engine = BacktestEngine()

    try:
        to_date = (pd.to_datetime(start_date) + timedelta(days=days - 1)).strftime(
            "%Y-%m-%d"
        )
        metrics = engine.run(strategy_config, start_date, to_date)

        if metrics:
            console.print("[green]Backtest Run Successful[/green]")
            table = Table(title="Metrics Check")
            table.add_column("Metric")
            table.add_column("Value")
            table.add_row("Mean Daily", f"{metrics.get('mean', 0):.4f}")
            table.add_row("Std Daily", f"{metrics.get('std', 0):.4f}")
            table.add_row("N Days", str(metrics.get("n_days", 0)))
            table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.4f}")
            console.print(table)

            # 2. DB Check
            conn = duckdb.connect(db_path)
            try:
                run_id = metrics["run_id"]
                df = conn.execute(
                    f"SELECT mean_daily_return, std_daily_return, n_days FROM backtest_summary WHERE run_id = '{run_id}'"
                ).df()
                console.print(f"\n[bold]DB Record Check ({run_id}):[/bold]")
                console.print(df)

                if df.empty or pd.isna(df.iloc[0]["mean_daily_return"]):
                    console.print(
                        "[red]DB Verification Failed: Columns missing or null[/red]"
                    )
                else:
                    console.print(
                        "[green]DB Verification Passed: New columns populated correctly[/green]"
                    )
            finally:
                conn.close()

        else:
            console.print("[yellow]Backtest returned no results[/yellow]")

    except Exception as e:
        console.print(f"[red]Verification Failed: {e}[/red]")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    verify_p5()
