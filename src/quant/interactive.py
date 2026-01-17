import logging
from datetime import datetime

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from quant.backtest_engine.engine import BacktestEngine
from quant.config import settings
from quant.data_curator.ingest import DataIngester
from quant.data_curator.provider import AlphaVantageProvider
from quant.feature_store.features import FeatureCalculator
from quant.ml.scorer import MLScorer
from quant.ml.trainer import MLTrainer
from quant.portfolio_supervisor.engine import PortfolioSupervisor
from quant.repos.targets import save_targets
from quant.strategy_lab.loader import StrategyLoader
from quant.strategy_lab.recommender import Recommender

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
                provider = AlphaVantageProvider(api_key=settings.alpha_vantage_api_key)
                ingester = DataIngester(provider)

                if not symbols:
                    from quant.db.engine import get_session
                    from quant.repos.symbol import SymbolRepo

                    with get_session() as session:
                        repo = SymbolRepo(session)
                        symbols = [s.symbol for s in repo.list_active_symbols()]

                for sym in symbols:
                    console.print(f"Ingesting [bold]{sym}[/bold]...")
                    ingester.ingest_symbol(sym)
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

        if inquirer.confirm(message="Start computation?").execute():
            with console.status("[bold green]Computing features..."):
                calc = FeatureCalculator()

                from quant.db.metastore import MetaStore

                with MetaStore().get_session() as session:
                    from sqlmodel import select

                    from quant.models import Symbol

                    symbols = [
                        s.symbol
                        for s in session.exec(
                            select(Symbol).where(Symbol.is_active)
                        ).all()
                    ]

                for sym in symbols:
                    calc.run_for_symbol(sym, version=version)
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
                trainer = MLTrainer()
                # For simplicity, train all active symbols
                from quant.db.metastore import MetaStore

                with MetaStore().get_session() as session:
                    from sqlmodel import select

                    from quant.models import Symbol

                    symbols = [
                        s.symbol
                        for s in session.exec(
                            select(Symbol).where(Symbol.is_active)
                        ).all()
                    ]

                for sym in symbols:
                    if task == "experts":
                        trainer.train_experts(sym)
                    else:
                        trainer.train_baseline(sym, feature_selection=feature_selection)

            console.print("[green]Training Complete![/green]")

    elif action == "score":
        ensemble = inquirer.confirm(message="Use Expert Ensemble (Gating)?").execute()
        if inquirer.confirm(message="Start scoring?").execute():
            with console.status("[bold green]Scoring..."):
                scorer = MLScorer()
                # Get symbols again... (should refactor this)
                from quant.db.metastore import MetaStore

                with MetaStore().get_session() as session:
                    from sqlmodel import select

                    from quant.models import Symbol

                    symbols = [
                        s.symbol
                        for s in session.exec(
                            select(Symbol).where(Symbol.is_active)
                        ).all()
                    ]

                for sym in symbols:
                    if ensemble:
                        scorer.score_ensemble(sym)
                    else:
                        scorer.score(sym)  # Default latest model

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

    # Strategy Selection
    strategies_dir = settings.project_root / "strategies"
    if not strategies_dir.exists():
        console.print(f"[red]Strategies directory not found: {strategies_dir}[/red]")
        return

    strategy_files = list(strategies_dir.glob("*.yaml"))
    if not strategy_files:
        console.print(f"[red]No YAML strategies found in {strategies_dir}[/red]")
        return

    strategy_path = inquirer.select(
        message="Select Strategy:",
        choices=[Choice(str(f), name=f.name) for f in strategy_files],
    ).execute()

    config = StrategyLoader.load_yaml(Path(strategy_path))

    if action == "recommend":
        asof = inquirer.text(
            message="Target Date (YYYY-MM-DD):",
            default=datetime.now().strftime("%Y-%m-%d"),
        ).execute()
        if inquirer.confirm(message="Generate recommendations?").execute():
            with console.status("[bold green]Generating..."):
                recommender = Recommender()
                df_raw = recommender.generate_targets(config, asof)
                if not df_raw.empty:
                    supervisor = PortfolioSupervisor(config)
                    df_final = supervisor.audit(df_raw)
                    save_targets(df_final)
                    console.print(df_final)
                else:
                    console.print("[yellow]No raw recommendations generated.[/yellow]")

    elif action == "backtest":
        start = inquirer.text(
            message="Start Date (YYYY-MM-DD):", default="2024-01-01"
        ).execute()
        end = inquirer.text(
            message="End Date (YYYY-MM-DD):", default="2024-12-31"
        ).execute()
        if inquirer.confirm(message="Run Backtest?").execute():
            with console.status("[bold green]Running Simulation..."):
                engine = BacktestEngine()
                metrics = engine.run(config, start, end)

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
