from __future__ import annotations

import logging
import os
from pathlib import Path

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel

from .config import settings
from .db.duck import connect as duck_connect
from .db.engine import get_engine, get_session
from .logging import setup_logging
from .ml.scorer import MLScorer
from .ml.trainer import MLTrainer
from .models.meta import SQLModel
from .repos.symbol import SymbolRepo

console = Console()
app = typer.Typer(add_completion=False)
log = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context):
    setup_logging()
    if ctx.invoked_subcommand is None:
        from .interactive import main_menu

        main_menu()


@app.command("about")
def about():
    print(
        Panel.fit(
            "[b]quant-lab[/b]\n"
            "- CLI-first executor (ingest/features/labels/train/score/backtest)\n"
            "- Streamlit read-only viewer\n",
            title="About",
        )
    )


@app.command("ui")
def ui():
    """Start Interactive CLI Mode (TUI)."""
    from .interactive import main_menu

    main_menu()


@app.command("init-db")
def init_db(
    duckdb_path: Path | None = typer.Option(None, "--duckdb", help="DuckDB file path"),
    sqlite_path: Path | None = typer.Option(None, "--sqlite", help="SQLite file path"),
):
    """Initialize DuckDB + SQLite schemas (Drop & Recreate)."""
    # 1. SQLite (SQLModel)
    engine = get_engine(sqlite_path, force_new=True)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    # 2. Run Tracking (Start AFTER tables are created)
    from .repos.run_registry import RunRegistry

    run_id = RunRegistry.run_start(
        "init-db", {"duckdb": str(duckdb_path), "sqlite": str(sqlite_path)}
    )

    try:
        # 3. DuckDB (Raw SQL)
        try:
            dconn = duck_connect(duckdb_path)
            schema_duck_sql = (
                Path(__file__).parent / "db" / "schema_duck.sql"
            ).read_text(encoding="utf-8")
            # Drop all V2 tables
            tables = [
                "ohlcv",
                "returns",
                "features_daily",
                "labels",
                "predictions",
                "targets",
                "backtest_trades",
                "backtest_summary",
            ]
            for t in tables:
                dconn.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")

            dconn.execute(schema_duck_sql)
            dconn.close()
        except Exception as de:
            print(f"[red]DuckDB Error: {de}[/red]")
            raise de

        RunRegistry.run_success(run_id)
        print(
            Panel.fit(
                f"Initialized DBs (Drop & Recreate)\n"
                f"DuckDB: [b]{duckdb_path or settings.quant_duckdb_path}[/b]\n"
                f"SQLite: [b]{sqlite_path or settings.quant_sqlite_path}[/b]\n"
                f"Run ID: [dim]{run_id}[/dim]",
                title="init-db",
            )
        )
    except Exception as e:
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Error during init-db: {e}[/red]")
        raise typer.Exit(code=1)
    finally:
        engine.dispose()


@app.command("symbol-register")
def symbol_register(
    symbols: list[str] = typer.Argument(..., help="List of symbols to register"),
    ingest: bool = typer.Option(
        False, "--ingest", help="Immediately ingest OHLCV after registration"
    ),
):
    """Register one or more symbols via AlphaVantageProvider and save to SQLite."""
    for symbol in symbols:
        with get_session() as session:
            repo = SymbolRepo(session)
            sym = repo.register_symbol(symbol)
            print(f"Registered: [b]{sym.symbol}[/b] ({sym.name}) - {sym.currency}")

        if ingest:
            from .data_curator.ingest import DataIngester
            from .data_curator.provider import AlphaVantageProvider

            print(
                f"[bold green]Starting immediate ingestion for {symbol}...[/bold green]"
            )
            provider = AlphaVantageProvider(api_key=settings.alpha_vantage_api_key)
            ingester = DataIngester(provider)
            ingester.ingest_symbol(symbol, force_full=False)
            ingester.ingest_overview(symbol)
            print(f"[bold green]Ingestion complete for {symbol}[/bold green]")


@app.command("config")
def show_config():
    """Print resolved configuration."""
    from .repos.run_registry import RunRegistry

    run_id = RunRegistry.run_start("config")

    data = {
        "alpha_vantage_api_key_set": bool(settings.alpha_vantage_api_key),
        "quant_data_dir": str(settings.quant_data_dir),
        "quant_duckdb_path": str(settings.quant_duckdb_path),
        "quant_sqlite_path": str(settings.quant_sqlite_path),
        "quant_log_level": settings.quant_log_level,
    }
    print(Panel.fit(str(data), title="config"))
    RunRegistry.run_success(run_id)


# Placeholders for future sprints (stubs)
@app.command("ingest")
def ingest(
    symbols: list[str] = typer.Option(
        None, "--symbols", help="Specific symbols to ingest"
    ),
    force_full: bool = typer.Option(
        False, "--full", help="Force full instead of compact"
    ),
):
    """Ingest OHLCV from Alpha Vantage into DuckDB (V2 Ingester)."""
    from .data_curator.ingest import DataIngester
    from .data_curator.provider import AlphaVantageProvider
    from .repos.run_registry import RunRegistry
    from .repos.symbol import SymbolRepo

    run_id = RunRegistry.run_start(
        "ingest", {"symbols": symbols, "force_full": force_full}
    )

    try:
        # 1. Prepare target symbols
        with get_session() as session:
            repo = SymbolRepo(session)
            if symbols:
                target_symbols = [s for s in symbols if repo.get_symbol(s)]
            else:
                target_symbols = [s.symbol for s in repo.list_active_symbols()]

        if not target_symbols:
            msg = "No active symbols found to ingest."
            print(f"[yellow]{msg}[/yellow]")
            RunRegistry.run_success(run_id)  # Technically success as nothing to do
            return

        # 2. Initialize Ingester
        provider = AlphaVantageProvider(api_key=settings.alpha_vantage_api_key)
        ingester = DataIngester(provider)

        # 3. Execution
        with console.status("[bold green]Ingesting data...") as status:
            for i, sym in enumerate(target_symbols):
                status.update(
                    f"[bold green]Ingesting {sym} ({i+1}/{len(target_symbols)})..."
                )
                ingester.ingest_symbol(sym, force_full=force_full)

        RunRegistry.run_success(run_id)
        print(
            Panel.fit(
                f"Ingestion Complete for {len(target_symbols)} symbols", title="ingest"
            )
        )

    except Exception as e:
        log.exception("Ingestion failed")
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Ingestion failed: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("features")
def features(
    symbols: list[str] | None = typer.Option(None, "--symbols", "-s"),
    version: str = typer.Option("v1", "--feature-version", "-v"),
):
    """Compute features into DuckDB (V2 Feature Store)."""
    from .feature_store.features import FeatureCalculator
    from .repos.run_registry import RunRegistry
    from .repos.symbol import SymbolRepo

    run_id = RunRegistry.run_start("features", {"symbols": symbols, "version": version})

    try:
        with get_session() as session:
            repo = SymbolRepo(session)
            if symbols:
                target_symbols = [s for s in symbols if repo.get_symbol(s)]
            else:
                target_symbols = [s.symbol for s in repo.list_active_symbols()]

        if not target_symbols:
            print("[yellow]No symbols found to process features.[/yellow]")
            RunRegistry.run_success(run_id)
            return

        calc = FeatureCalculator()
        with console.status(f"[bold green]Computing features (version={version})..."):
            for sym in target_symbols:
                calc.run_for_symbol(sym, version=version)

        RunRegistry.run_success(run_id)
        print(
            Panel.fit(
                f"Feature Computation Complete (version={version}) for {len(target_symbols)} symbols",
                title="features",
            )
        )
    except Exception as e:
        log.exception("Feature calculation failed")
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Error computing features: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("labels")
def labels(
    symbols: list[str] | None = typer.Option(None, "--symbols", "-s"),
    horizon: int = typer.Option(60, "--horizon", "-h"),
    version: str = typer.Option("v1", "--label-version", "-v"),
):
    """Generate labels into DuckDB (V2 Label Store)."""
    from .feature_store.labels import LabelCalculator
    from .repos.run_registry import RunRegistry
    from .repos.symbol import SymbolRepo

    run_id = RunRegistry.run_start(
        "labels", {"symbols": symbols, "horizon": horizon, "version": version}
    )

    try:
        with get_session() as session:
            repo = SymbolRepo(session)
            if symbols:
                target_symbols = [s for s in symbols if repo.get_symbol(s)]
            else:
                target_symbols = [s.symbol for s in repo.list_active_symbols()]

        if not target_symbols:
            print("[yellow]No symbols found to generate labels.[/yellow]")
            RunRegistry.run_success(run_id)
            return

        calc = LabelCalculator()
        with console.status(
            f"[bold green]Generating labels (horizon={horizon}, version={version})..."
        ):
            for sym in target_symbols:
                calc.run_for_symbol(sym, version=version, horizon=horizon)

        RunRegistry.run_success(run_id)
        print(
            Panel.fit(
                f"Label Generation Complete (horizon={horizon}, version={version}) for {len(target_symbols)} symbols",
                title="labels",
            )
        )
    except Exception as e:
        log.exception("Label generation failed")
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Error generating labels: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def train(
    symbols: list[str] | None = typer.Option(None, "--symbols", "-s"),
    feature_version: str = typer.Option("v1", "--f-ver"),
    label_version: str = typer.Option("v1", "--l-ver"),
    horizon: int = typer.Option(60, "--horizon", "-h"),
    task: str = typer.Option("baseline", "--task", "-t", help="baseline or experts"),
    feature_selection: bool = typer.Option(
        False, "--feature-selection", "-fs", help="Enable stability selection"
    ),
    stability_n_runs: int = typer.Option(
        10, "--stability-n-runs", help="Runs for stability selection"
    ),
):
    """Train models (Baseline or Experts)."""
    with console.status(
        f"[bold green]Training {task} models (FS={feature_selection})..."
    ):
        trainer = MLTrainer()
        if symbols is None:
            # Active 모든 심볼
            from .db.metastore import MetaStore

            meta = MetaStore()
            with meta.get_session() as session:
                from sqlmodel import select

                from .models import Symbol

                symbols = [
                    s.symbol
                    for s in session.exec(
                        select(Symbol).where(Symbol.is_active)
                    ).all()
                ]

        for symbol in symbols:
            if task == "experts":
                trainer.train_experts(
                    symbol,
                    feature_version=feature_version,
                    label_version=label_version,
                    horizon=horizon,
                )
            else:
                trainer.train_baseline(
                    symbol,
                    feature_version,
                    label_version,
                    horizon,
                    feature_selection=feature_selection,
                    stability_n_runs=stability_n_runs,
                )

    print(Panel.fit(f"Training Complete ({task})", title="train"))


@app.command()
def score(
    symbols: list[str] | None = typer.Option(None, "--symbols", "-s"),
    model_id: str | None = typer.Option(None, "--model-id"),
    ensemble: bool = typer.Option(
        False, "--ensemble", help="Use expert ensemble (Gating)"
    ),
):
    """Generate predictions (Score)."""
    with console.status(f"[bold green]Scoring symbols (ensemble={ensemble})..."):
        scorer = MLScorer()
        if symbols is None:
            from .db.metastore import MetaStore

            meta = MetaStore()
            with meta.get_session() as session:
                from sqlmodel import select

                from .models import Symbol

                symbols = [
                    s.symbol
                    for s in session.exec(
                        select(Symbol).where(Symbol.is_active)
                    ).all()
                ]

        for symbol in symbols:
            if ensemble:
                scorer.score_ensemble(symbol)
            else:
                scorer.score(symbol, model_id)

    print(Panel.fit(f"Inference Complete (ensemble={ensemble})", title="score"))


@app.command("recommend")
def recommend(
    strategy: Path = typer.Option(
        ..., "--strategy", "-s", help="Path to strategy YAML"
    ),
    asof: str = typer.Option(..., "--asof", "-a", help="Target date YYYY-MM-DD"),
):
    """Generate portfolio recommendations (V2 Strategy Lab)."""
    from .portfolio_supervisor.engine import PortfolioSupervisor
    from .repos.run_registry import RunRegistry
    from .strategy_lab.loader import StrategyLoader
    from .strategy_lab.recommender import Recommender

    # DuckDB Concurrency Warning
    print(
        "[bold yellow]WARNING: DuckDB write 작업 중에는 Streamlit 동시 실행을 권장하지 않습니다.[/bold yellow]"
    )

    run_id = RunRegistry.run_start(
        "recommend", {"strategy": str(strategy), "asof": asof}
    )

    try:
        # 1. Load Strategy
        config = StrategyLoader.load_yaml(strategy)

        # 2. Recommender (Raw Targets)
        recommender = Recommender()
        df_raw = recommender.generate_targets(config, asof)

        if df_raw.empty:
            print(
                f"[yellow]No recommendations generated for {asof}. Check features data.[/yellow]"
            )
            RunRegistry.run_success(run_id)
            return

        # 3. Supervisor (Audit)
        supervisor = PortfolioSupervisor(config)
        df_final = supervisor.audit(df_raw)

        # 4. Save to DuckDB
        from .repos.targets import save_targets

        save_targets(df_final)

        RunRegistry.run_success(run_id)

        # 5. Display Result
        from rich.table import Table

        table = Table(title=f"Recommendations: {config['strategy_id']} (asof {asof})")
        table.add_column("Symbol", style="cyan")
        table.add_column("Weight", style="magenta")
        table.add_column("Score", style="green")
        table.add_column("Approved", style="bold")
        table.add_column("Risk Flags", style="dim")

        for _, row in df_final.iterrows():
            app_style = "green" if row["approved"] else "red"
            table.add_row(
                row["symbol"],
                f"{row['weight']*100:.1f}%",
                f"{row['score']:.4f}",
                f"[{app_style}]{row['approved']}[/{app_style}]",
                row["risk_flags"] or "-",
            )

        console.print(table)
        print(
            Panel.fit(
                f"Targets saved to DuckDB (targets) | Run ID: {run_id}",
                title="recommend",
            )
        )

    except Exception as e:
        log.exception("Recommendation failed")
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Error during recommend: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("backtest")
def backtest(
    strategy: Path = typer.Option(
        ..., "--strategy", "-s", help="Path to strategy YAML"
    ),
    start: str = typer.Option(..., "--from", "-f", help="Start date YYYY-MM-DD"),
    end: str = typer.Option(..., "--to", "-t", help="End date YYYY-MM-DD"),
):
    """Run backtest simulation (V2 Backtest Engine)."""
    from .backtest_engine.engine import BacktestEngine
    from .repos.run_registry import RunRegistry
    from .strategy_lab.loader import StrategyLoader

    # DuckDB Concurrency Warning
    print(
        "[bold yellow]WARNING: DuckDB write 작업 중에는 Streamlit 동시 실행을 권장하지 않습니다.[/bold yellow]"
    )

    run_id = RunRegistry.run_start(
        "backtest", {"strategy": str(strategy), "from": start, "to": end}
    )

    try:
        # 1. Load Strategy
        config = StrategyLoader.load_yaml(strategy)

        # 2. Run Engine
        engine = BacktestEngine()
        with console.status(
            f"[bold green]Running backtest for {config['strategy_id']}..."
        ):
            metrics = engine.run(config, start, end)

        if not metrics:
            print(
                "[yellow]Backtest completed with no results. Check targets and price data.[/yellow]"
            )
            RunRegistry.run_success(run_id)
            return

        RunRegistry.run_success(run_id)

        # 3. Display Summary
        from rich.table import Table

        table = Table(title=f"Backtest Result: {config['strategy_id']}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("CAGR", f"{metrics['cagr']:.2%}")
        table.add_row("Sharpe", f"{metrics['sharpe']:.2f}")
        table.add_row("MaxDD", f"{metrics['max_dd']:.2%}")
        table.add_row("Daily Mean", f"{metrics['mean']:.4%}")
        table.add_row("Daily Std", f"{metrics['std']:.4%}")
        table.add_row("Days", str(metrics["n_days"]))
        table.add_row("Run ID", metrics["run_id"])

        console.print(table)
        print(
            Panel.fit(
                f"Backtest results saved to DuckDB | Run ID: {run_id}", title="backtest"
            )
        )

    except Exception as e:
        log.exception("Backtest failed")
        RunRegistry.run_fail(run_id, str(e))
        print(f"[red]Error during backtest: {e}[/red]")
        raise typer.Exit(code=1)


# --- Pipeline Command Group ---
pipeline_app = typer.Typer(help="Batch Pipeline Orchestration")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("run")
def run_pipeline(
    strategy: Path = typer.Option(..., "--strategy", help="Path to strategy YAML"),
    start_date: str = typer.Option(..., "--from", help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(..., "--to", help="End date YYYY-MM-DD"),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Optional run_id UUID. If non-UUID is given, it is treated as a run slug (display alias) and a UUID run_id is generated.",
    ),
    symbols: list[str] | None = typer.Option(
        None, "--symbols", help="Override symbols"
    ),
    stages: str | None = typer.Option(
        None,
        "--stages",
        help="Comma-separated stages (ingest,features,labels,recommend,backtest)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Plan execution without running"
    ),
    fail_fast: bool = typer.Option(
        True, "--fail-fast/--no-fail-fast", help="Stop on first error"
    ),
):
    """Run End-to-End Pipeline."""
    import sys
    import uuid
    from datetime import date

    from .batch_orchestrator.pipeline import PipelineContext, PipelineRunner

    def _is_uuid(s: str | None) -> bool:
        if not s:
            return False
        try:
            uuid.UUID(str(s))
            return True
        except Exception:
            return False

    allowed_stages = set(PipelineRunner.STAGES)

    def _parse_stages(raw: str | None) -> list[str]:
        if not raw:
            return []
        parsed: list[str] = []
        seen: set[str] = set()
        for part in raw.split(","):
            st = part.strip().lower()
            if not st:
                continue
            if st not in allowed_stages:
                print(
                    f"[red]Invalid stage: '{st}'. Allowed: {', '.join(PipelineRunner.STAGES)}[/red]"
                )
                raise typer.Exit(code=1)
            if st in seen:
                continue
            seen.add(st)
            parsed.append(st)
        return parsed

    def _parse_symbols(raw_list: list[str] | None) -> list[str] | None:
        if not raw_list:
            return None
        # Typer List[str] can arrive as ['AAPL,PLTR,QQQM'] or ['AAPL','PLTR']
        joined = ",".join([s for s in raw_list if s is not None])
        parts = [p.strip() for p in joined.split(",")]
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if not p:
                continue
            sym = p.upper()
            if sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
        return out

    # 1) Validate dates early
    try:
        d_from = date.fromisoformat(start_date)
        d_to = date.fromisoformat(end_date)
    except ValueError:
        print("[red]Invalid date format. Use YYYY-MM-DD for --from/--to[/red]")
        raise typer.Exit(code=1)
    if d_from > d_to:
        print("[red]Invalid date range: --from must be <= --to[/red]")
        raise typer.Exit(code=1)

    # 2) Parse/validate stages + symbols override
    active_stages = _parse_stages(stages)
    symbols_override = _parse_symbols(symbols)

    invoked_command = " ".join(sys.argv)

    plan_run_id = (os.getenv("QUANT_PLAN_RUN_ID") or "").strip() or None
    plan_artifacts_dir = (os.getenv("QUANT_PLAN_ARTIFACTS_DIR") or "").strip() or None

    requested_run_id = run_id if _is_uuid(run_id) else None
    requested_run_slug = None if _is_uuid(run_id) else run_id

    # 2. Context
    ctx = PipelineContext(
        strategy_path=strategy,
        from_date=start_date,
        to_date=end_date,
        symbols=symbols_override or [],
        dry_run=dry_run,
        fail_fast=fail_fast,
        active_stages=active_stages,
        requested_run_id=requested_run_id,
        requested_run_slug=requested_run_slug,
        invoked_command=invoked_command,
        plan_run_id=plan_run_id,
        plan_artifacts_dir=plan_artifacts_dir,
    )

    # 3. Validation (Minimal)
    if not strategy.exists():
        print(f"[red]Strategy file not found: {strategy}[/red]")
        raise typer.Exit(code=1)

    # 4. Dry-run: compute and print plan only (no stage execution)
    if dry_run:
        runner = PipelineRunner(ctx)
        plan = runner.build_plan(
            invoked_command=invoked_command,
            stages_requested=stages,
            symbols_override_raw=symbols,
            run_id_override=run_id,
        )
        runner.print_and_persist_plan(plan)
        if not plan.get("validation", {}).get("ok", False):
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    # 5. Run
    runner = PipelineRunner(ctx)
    success = runner.run()

    if not success:
        print("[red]Pipeline Failed[/red]")
        raise typer.Exit(code=1)

    print("[green]Pipeline Completed Successfully[/green]")


def main() -> None:
    """Module entrypoint (enables `python -m quant.cli ...`)."""
    app()


if __name__ == "__main__":
    main()
