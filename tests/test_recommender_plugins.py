import os
import subprocess
from pathlib import Path
import uuid
import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from src.quant.strategy_lab.loader import StrategyLoader


def _env_for_tmp(tmp_path: Path) -> dict:
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    runs_dir = artifacts_dir / "runs"
    data_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    duckdb_path = data_dir / "quant.duckdb"
    sqlite_path = data_dir / "meta.db"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["QUANT_DUCKDB_PATH"] = str(duckdb_path)
    env["QUANT_SQLITE_PATH"] = str(sqlite_path)
    env["QUANT_ARTIFACTS_DIR"] = str(artifacts_dir)
    env["QUANT_RUNS_DIR"] = str(runs_dir)

    return env


def _init_dbs(env: dict):
    duckdb_path = env["QUANT_DUCKDB_PATH"]
    sqlite_path = env["QUANT_SQLITE_PATH"]
    subprocess.run(
        [
            "uv",
            "run",
            "quant",
            "init-db",
            "--duckdb",
            duckdb_path,
            "--sqlite",
            sqlite_path,
        ],
        check=True,
        env=env,
    )


def _seed_ohlcv_and_features(
    *,
    duckdb_path: Path,
    symbols: list[str],
    date_from: str,
    date_to: str,
):
    dates = pd.date_range(date_from, date_to, freq="D")

    rows = []
    rng = np.random.default_rng(42)
    for sym in symbols:
        base = 100 + rng.normal(0, 1)
        close = base + np.cumsum(rng.normal(0, 1, size=len(dates)))
        open_ = close + rng.normal(0, 0.3, size=len(dates))
        high = np.maximum(open_, close) + rng.uniform(0, 0.8, size=len(dates))
        low = np.minimum(open_, close) - rng.uniform(0, 0.8, size=len(dates))
        volume = rng.integers(1_000_000, 2_000_000, size=len(dates))
        for i, d in enumerate(dates):
            rows.append(
                {
                    "symbol": sym,
                    "ts": d.date(),
                    "open": float(open_[i]),
                    "high": float(high[i]),
                    "low": float(low[i]),
                    "close": float(close[i]),
                    "volume": int(volume[i]),
                }
            )

    df_ohlcv = pd.DataFrame(rows)

    conn = duckdb.connect(str(duckdb_path))
    try:
        conn.register("df_ohlcv_tmp", df_ohlcv)
        conn.execute(
            "INSERT INTO ohlcv (symbol, ts, open, high, low, close, volume) SELECT symbol, ts, open, high, low, close, volume FROM df_ohlcv_tmp"
        )

        # Feature set mirrors FeatureCalculator.calculate_v1_features
        feat_rows = []
        for sym in symbols:
            df = df_ohlcv[df_ohlcv["symbol"] == sym].copy()
            df["ts"] = pd.to_datetime(df["ts"])
            df = df.sort_values("ts").set_index("ts")

            feat = pd.DataFrame(index=df.index)
            feat["ret_1d"] = df["close"].pct_change(1)
            feat["ret_5d"] = df["close"].pct_change(5)
            feat["ret_20d"] = df["close"].pct_change(20)
            feat["ret_60d"] = df["close"].pct_change(60)
            feat["vol_20d"] = feat["ret_1d"].rolling(20).std()
            prev_close = df["close"].shift(1)
            feat["gap_open"] = (df["open"] - prev_close) / prev_close
            feat["hl_range"] = (df["high"] - df["low"]) / df["close"]
            vol_avg = df["volume"].rolling(20).mean()
            feat["volume_ratio_20d"] = df["volume"] / vol_avg.replace(0, np.nan)

            feat = feat.dropna().reset_index()
            feat = feat.melt(
                id_vars=["ts"], var_name="feature_name", value_name="feature_value"
            )
            feat["symbol"] = sym
            feat["feature_version"] = "v1"
            feat["computed_at"] = pd.Timestamp.utcnow()
            feat_rows.append(feat)

        df_feat = pd.concat(feat_rows, ignore_index=True)
        df_feat["ts"] = pd.to_datetime(df_feat["ts"]).dt.date

        conn.register("df_feat_tmp", df_feat)
        conn.execute(
            "INSERT INTO features_daily (symbol, ts, feature_name, feature_value, feature_version, computed_at) SELECT symbol, ts, feature_name, feature_value, feature_version, computed_at FROM df_feat_tmp"
        )
    finally:
        conn.close()


def test_yaml_validation_rejects_invalid_recommender_type_and_algo():
    base = {
        "strategy_id": "x",
        "version": "0.1",
        "universe": {"type": "symbols", "symbols": ["AAPL"]},
        "rebalance": {"frequency": "daily", "asof_policy": "close"},
        "portfolio": {"top_k": 2, "weighting": "equal"},
        "supervisor": {
            "gross_exposure_cap": 1.0,
            "max_weight_per_symbol": 1.0,
            "max_positions": 10,
        },
        "signal": {
            "type": "factor_rank",
            "inputs": {"feature_version": "v1", "feature_name": "ret_20d"},
        },
    }

    bad_type = {**base, "recommender": {"type": "foo"}}
    with pytest.raises(ValueError):
        StrategyLoader.validate_schema(bad_type)

    bad_algo = {
        **base,
        "recommender": {
            "type": "ml_gbdt",
            "top_k": 3,
            "weighting": "equal",
            "model": {
                "algo": "bad",
                "target": "forward_ret_5d",
                "featureset": "default",
                "train_window": {
                    "train_from": "2023-01-01",
                    "train_to": "2023-01-10",
                    "valid_from": "2023-01-11",
                    "valid_to": "2023-01-15",
                },
            },
        },
    }
    with pytest.raises(ValueError):
        StrategyLoader.validate_schema(bad_algo)


def test_ml_gbdt_pipeline_recommend_writes_model_and_targets(tmp_path: Path):
    env = _env_for_tmp(tmp_path)
    _init_dbs(env)

    duckdb_path = Path(env["QUANT_DUCKDB_PATH"])
    runs_dir = Path(env["QUANT_RUNS_DIR"])

    symbols = ["AAPL", "PLTR", "QQQM"]
    _seed_ohlcv_and_features(
        duckdb_path=duckdb_path,
        symbols=symbols,
        date_from="2022-09-01",
        date_to="2023-02-10",
    )

    strategy_path = tmp_path / "ml_gbdt.yaml"
    strategy_path.write_text(
        "\n".join(
            [
                'strategy_id: "t_ml_gbdt"',
                'version: "0.1"',
                "universe:",
                '  type: "symbols"',
                f"  symbols: {symbols}",
                "signal:",
                '  type: "factor_rank"',
                "  inputs:",
                '    feature_version: "v1"',
                '    feature_name: "ret_20d"',
                "rebalance:",
                '  frequency: "daily"',
                '  asof_policy: "close"',
                "portfolio:",
                "  top_k: 2",
                '  weighting: "equal"',
                "recommender:",
                '  type: "ml_gbdt"',
                "  top_k: 2",
                '  weighting: "equal"',
                "  model:",
                '    algo: "lightgbm"',
                '    target: "forward_ret_5d"',
                '    featureset: "default"',
                "    train_window:",
                '      train_from: "2023-01-01"',
                '      train_to:   "2023-01-15"',
                '      valid_from: "2023-01-16"',
                '      valid_to:   "2023-01-25"',
                "supervisor:",
                "  gross_exposure_cap: 1.0",
                "  max_weight_per_symbol: 1.0",
                "  max_positions: 10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run_id = str(uuid.uuid4())
    proc = subprocess.run(
        [
            "uv",
            "run",
            "quant",
            "pipeline",
            "run",
            "--strategy",
            str(strategy_path),
            "--from",
            "2023-01-26",
            "--to",
            "2023-01-30",
            "--symbols",
            "AAPL,PLTR,QQQM",
            "--stages",
            "recommend",
            "--run-id",
            run_id,
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    # LightGBM noise must not appear on console by default
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert "[LightGBM]" not in combined

    artifacts_dir = runs_dir / run_id
    assert (artifacts_dir / "models" / "model.lightgbm.joblib").exists()
    assert (artifacts_dir / "reports" / "ml_metrics.json").exists()
    assert (artifacts_dir / "reports" / "ml_summary.md").exists()
    assert not (
        artifacts_dir / "stages" / "recommend" / "lightgbm.log"
    ).exists(), "lightgbm.log is opt-in via QUANT_LGBM_LOG=1"

    # Stage result metadata should be enriched
    rec_result = json.loads(
        (artifacts_dir / "stages" / "recommend" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    meta = rec_result.get("meta") or {}
    assert meta.get("n_dates") is not None
    assert meta.get("n_rows") is not None
    assert meta.get("date_min")
    assert meta.get("date_max")
    assert meta.get("top_k") == 2
    assert (meta.get("recommender") or {}).get("type") == "ml_gbdt"
    arts = meta.get("artifacts") or {}
    assert arts.get("model_path") == "models/model.lightgbm.joblib"
    assert arts.get("metrics_path") == "reports/ml_metrics.json"
    assert arts.get("summary_path") == "reports/ml_summary.md"
    assert arts.get("predictions_path") == "outputs/predictions.csv"
    assert "lightgbm_log_path" not in arts

    # run.json must use stage_exec_id (not a nested run_id)
    run_json = json.loads((artifacts_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json.get("run_id") == run_id
    assert run_json.get("invoked_command")
    assert str(artifacts_dir) in (run_json.get("artifacts_dir") or "")
    assert run_json.get("run_slug")
    assert run_json.get("display_name")
    stage_results = run_json.get("stage_results") or []
    assert stage_results
    assert "run_id" not in stage_results[0]
    assert stage_results[0].get("stage_exec_id") is not None

    # Alias index entry must exist
    idx_path = (
        Path(env["QUANT_ARTIFACTS_DIR"])
        / "index"
        / "runs"
        / f"{run_json['run_slug']}.json"
    )
    assert idx_path.exists()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert idx.get("run_id") == run_id

    # Opt-in LightGBM native logs to artifacts
    env2 = dict(env)
    env2["QUANT_LGBM_LOG"] = "1"
    run_id2 = str(uuid.uuid4())
    subprocess.run(
        [
            "uv",
            "run",
            "quant",
            "pipeline",
            "run",
            "--strategy",
            str(strategy_path),
            "--from",
            "2023-01-26",
            "--to",
            "2023-01-30",
            "--symbols",
            "AAPL,PLTR,QQQM",
            "--stages",
            "recommend",
            "--run-id",
            run_id2,
        ],
        check=True,
        env=env2,
    )
    artifacts_dir2 = runs_dir / run_id2
    assert (artifacts_dir2 / "stages" / "recommend" / "lightgbm.log").exists()
    rec_result2 = json.loads(
        (artifacts_dir2 / "stages" / "recommend" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    arts2 = (rec_result2.get("meta") or {}).get("artifacts") or {}
    assert arts2.get("lightgbm_log_path") == "stages/recommend/lightgbm.log"

    conn = duckdb.connect(str(duckdb_path))
    try:
        result = conn.execute(
            "SELECT COUNT(*) FROM targets WHERE strategy_id = 't_ml_gbdt' AND study_date >= DATE '2023-01-26' AND study_date <= DATE '2023-01-30'"
        ).fetchone()
        assert result is not None, "Query returned no rows"
        cnt = result[0]
        assert cnt > 0, "ml_gbdt should write targets for the run window"
    finally:
        conn.close()


def test_factor_rank_pipeline_remains_baseline(tmp_path: Path):
    env = _env_for_tmp(tmp_path)
    _init_dbs(env)

    duckdb_path = Path(env["QUANT_DUCKDB_PATH"])
    runs_dir = Path(env["QUANT_RUNS_DIR"])

    symbols = ["AAPL", "PLTR"]
    _seed_ohlcv_and_features(
        duckdb_path=duckdb_path,
        symbols=symbols,
        date_from="2022-12-01",
        date_to="2023-02-10",
    )

    strategy_path = tmp_path / "factor_rank.yaml"
    strategy_path.write_text(
        "\n".join(
            [
                'strategy_id: "t_factor_rank"',
                'version: "0.1"',
                "universe:",
                '  type: "symbols"',
                f"  symbols: {symbols}",
                "signal:",
                '  type: "factor_rank"',
                "  inputs:",
                '    feature_version: "v1"',
                '    feature_name: "ret_20d"',
                "rebalance:",
                '  frequency: "daily"',
                '  asof_policy: "close"',
                "portfolio:",
                "  top_k: 2",
                '  weighting: "equal"',
                "supervisor:",
                "  gross_exposure_cap: 1.0",
                "  max_weight_per_symbol: 1.0",
                "  max_positions: 10",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run_id = str(uuid.uuid4())
    subprocess.run(
        [
            "uv",
            "run",
            "quant",
            "pipeline",
            "run",
            "--strategy",
            str(strategy_path),
            "--from",
            "2023-01-26",
            "--to",
            "2023-01-30",
            "--symbols",
            "AAPL,PLTR",
            "--stages",
            "recommend",
            "--run-id",
            run_id,
        ],
        check=True,
        env=env,
    )

    artifacts_dir = runs_dir / run_id
    assert not (
        artifacts_dir / "models"
    ).exists(), "baseline factor_rank must not train models"

    conn = duckdb.connect(str(duckdb_path))
    try:
        result = conn.execute(
            "SELECT COUNT(DISTINCT study_date) FROM targets WHERE strategy_id = 't_factor_rank'"
        ).fetchone()
        assert result is not None, "Query returned no rows"
        n_dates = result[0]
        assert (
            n_dates == 1
        ), "baseline factor_rank should emit targets only for asof=to_date"
    finally:
        conn.close()
