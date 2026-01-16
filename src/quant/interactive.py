import sys
import logging
from typing import List, Optional
from datetime import datetime

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console
from rich.panel import Panel
from rich.logging import RichHandler

from quant.services.market_data import MarketDataService
from quant.services.feature import FeatureService
from quant.services.ml import MLService
from quant.services.backtest import BacktestService
from quant.services.portfolio import PortfolioService
from quant.db.metastore import MetaStore
from quant.config import settings

console = Console()
log = logging.getLogger(__name__)


# --- Setup Rich Logging for Interactive Mode ---
def setup_interactive_logging():
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


def print_header():
    console.print(
        Panel.fit(
            "[bold cyan]Quant Lab Interactive[/bold cyan]\n"
            "[dim]Explore, Train, and Backtest your strategies[/dim]",
            subtitle=f"v0.1.0 | {datetime.now().strftime('%Y-%m-%d')}",
        )
    )


# --- Workflows ---


def data_workflow():
    """Data Management Workflow"""
    action = inquirer.select(
        message="Data Management:",
        choices=[
            Choice("ingest", name="Ingest OHLCV (Alpha Vantage)"),
            Choice("check", name="Check Data Status"),
            Choice("back", name="< Back to Main Menu"),
        ],
    ).execute()

    if action == "back":
        return

    if action == "ingest":
        symbols_input = inquirer.text(
            message="Enter symbols to ingest (comma separated, leave empty for all active):"
        ).execute()

        symbols = (
            [s.strip() for s in symbols_input.split(",")] if symbols_input else None
        )

        if inquirer.confirm(
            message=f"Start ingestion for {symbols or 'ALL active'}?"
        ).execute():
            with console.status("[bold green]Ingesting data..."):
                service = MarketDataService()
                # Assuming MarketDataService has a method to get active symbols if None is passed
                # But currently CLI logic handles active symbol fetching. Let's do it here.
                if not symbols:
                    from quant.repos.symbol import SymbolRepo
                    from quant.db.engine import get_session

                    with get_session() as session:
                        repo = SymbolRepo(session)
                        symbols = [s.symbol for s in repo.list_active_symbols()]

                for sym in symbols:
                    console.print(f"Ingesting [bold]{sym}[/bold]...")
                    service.get_daily_prices(sym)

                # Close connection to release lock
                if hasattr(service, "series_store"):
                    service.series_store.close()
            console.print("[green]Ingestion Complete![/green]")

    elif action == "check":
        # Simple stats using DuckDB
        from quant.db.duck import connect

        conn = connect(settings.quant_duckdb_path, read_only=True)
        try:
            res = conn.execute("SELECT count(*) FROM ohlcv").fetchone()
            console.print(f"Total OHLCV Rows: [bold cyan]{res[0]}[/bold cyan]")

            res_sym = conn.execute(
                "SELECT symbol, count(*) as cnt FROM ohlcv GROUP BY symbol"
            ).fetchall()
            console.print(Panel(str(res_sym), title="Rows per Symbol"))
        except Exception as e:
            console.print(f"[red]Error checking DB:[/red] {e}")
        finally:
            conn.close()


def ml_workflow():
    """Machine Learning Workflow"""
    action = inquirer.select(
        message="ML Pipeline:",
        choices=[
            Choice("features", name="1. Compute Features (Denoise)"),
            Choice("train", name="2. Train Models (Regularize)"),
            Choice("score", name="3. Score / Predict"),
            Choice("back", name="< Back to Main Menu"),
        ],
    ).execute()

    if action == "back":
        return

    if action == "features":
        version = inquirer.text(message="Feature Version:", default="v1").execute()
        winsorize = inquirer.confirm(message="Apply Winsorization (Denoise)?").execute()
        limits = None
        if winsorize:
            limits_str = inquirer.text(
                message="Winsorize Limits (lower,upper):", default="0.01,0.01"
            ).execute()
            limits = [float(x) for x in limits_str.split(",")]

        if inquirer.confirm(message="Start computation?").execute():
            with console.status("[bold green]Computing features..."):
                service = FeatureService()
                service.compute_all_features(
                    version=version, winsorize=winsorize, winsorize_limits=limits
                )
                if hasattr(service, "series_store"):
                    service.series_store.close()
            console.print("[green]Done![/green]")

    elif action == "train":
        task = inquirer.select(
            message="Training Task:",
            choices=[
                Choice("baseline", name="Baseline (LGBM)"),
                Choice("experts", name="Experts (Regime-based)"),
            ],
        ).execute()
        feature_selection = inquirer.confirm(
            message="Enable Stability Selection (Regularize)?"
        ).execute()

        if inquirer.confirm(message="Start training?").execute():
            with console.status(f"[bold green]Training {task}..."):
                service = MLService()
                # For simplicity, train all active symbols
                from quant.db.metastore import MetaStore

                with MetaStore().get_session() as session:
                    from quant.models import Symbol
                    from sqlmodel import select

                    symbols = [
                        s.symbol
                        for s in session.exec(
                            select(Symbol).where(Symbol.is_active == True)
                        ).all()
                    ]

                for sym in symbols:
                    if task == "experts":
                        service.train_experts(sym)
                    else:
                        service.train_baseline(sym, feature_selection=feature_selection)

                if hasattr(service, "series_store"):
                    service.series_store.close()

            console.print("[green]Training Complete![/green]")

    elif action == "score":
        ensemble = inquirer.confirm(message="Use Expert Ensemble (Gating)?").execute()
        if inquirer.confirm(message="Start scoring?").execute():
            with console.status("[bold green]Scoring..."):
                service = MLService()
                # Get symbols again... (should refactor this)
                from quant.db.metastore import MetaStore

                with MetaStore().get_session() as session:
                    from quant.models import Symbol
                    from sqlmodel import select

                    symbols = [
                        s.symbol
                        for s in session.exec(
                            select(Symbol).where(Symbol.is_active == True)
                        ).all()
                    ]

                for sym in symbols:
                    if ensemble:
                        service.score_ensemble(sym)
                    else:
                        service.score(sym)  # Default latest model

                if hasattr(service, "series_store"):
                    service.series_store.close()

            console.print("[green]Scoring Complete![/green]")


def backtest_workflow():
    """Backtest & Portfolio Workflow"""
    action = inquirer.select(
        message="Backtest & Portfolio:",
        choices=[
            Choice("recommend", name="Generate Portfolio Recommendations"),
            Choice("backtest", name="Run Backtest Simulation"),
            Choice("back", name="< Back to Main Menu"),
        ],
    ).execute()

    if action == "back":
        return

    if action == "recommend":
        top_k = int(inquirer.text(message="Top K:", default="3").execute())
        if inquirer.confirm(message="Generate recommendations?").execute():
            with console.status("[bold green]Generating..."):
                service = PortfolioService()
                df = service.generate_recommendation(top_k=top_k)
                if hasattr(service, "series_store"):
                    service.series_store.close()
            console.print(df)

    elif action == "backtest":
        start = inquirer.text(
            message="Start Date (YYYY-MM-DD):", default="2024-01-01"
        ).execute()
        end = inquirer.text(
            message="End Date (YYYY-MM-DD):", default="2024-12-31"
        ).execute()
        if inquirer.confirm(message="Run Backtest?").execute():
            with console.status("[bold green]Running Simulation..."):
                service = BacktestService()
                metrics = service.run_backtest(start_date=start, end_date=end)
                if hasattr(service, "series_store"):
                    service.series_store.close()

            if metrics:
                console.print(Panel(str(metrics), title="Backtest Result"))


# --- Main Loop ---


def main_menu():
    setup_interactive_logging()
    print_header()

    while True:
        choice = inquirer.select(
            message="Select Module:",
            choices=[
                Choice("data", name="💾 Data Management"),
                Choice("ml", name="🧠 Machine Learning"),
                Choice("backtest", name="📈 Portfolio & Backtest"),
                Choice("system", name="⚙️ System & Config"),
                Choice("exit", name="❌ Exit"),
            ],
            default="data",
        ).execute()

        if choice == "data":
            data_workflow()
        elif choice == "ml":
            ml_workflow()
        elif choice == "backtest":
            backtest_workflow()
        elif choice == "system":
            console.print(
                Panel(str(settings.model_dump()), title="Current Configuration")
            )
            inquirer.text(message="Press Enter to continue...").execute()
        elif choice == "exit":
            console.print("[bold]Goodbye![/bold]")
            break


if __name__ == "__main__":
    main_menu()
