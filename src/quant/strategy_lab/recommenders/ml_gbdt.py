from __future__ import annotations

import json
import os
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ...config import settings
from ...db.duck import connect as duck_connect
from .base import BaseRecommender, RecommenderContext

_DEFAULT_FEATURESET_V1 = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "vol_20d",
    "gap_open",
    "hl_range",
    "volume_ratio_20d",
]


def _parse_date(s: str) -> pd.Timestamp:
    return pd.to_datetime(s).normalize()


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@contextmanager
@contextmanager
def _redirect_fds_to_file(path: Path):
    """Redirect OS-level stdout/stderr to a file (captures native lib output).

    This is intentionally narrow: used only around external libs (e.g., LightGBM)
    to prevent noisy console logs while still persisting debug logs under artifacts.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd_out = 1
    fd_err = 2
    saved_out = os.dup(fd_out)
    saved_err = os.dup(fd_err)

    with open(path, "a", encoding="utf-8") as f:
        f.write(
            f"\n--- lightgbm redirect start: {datetime.now(UTC).isoformat()}Z ---\n"
        )
        f.flush()
        try:
            os.dup2(f.fileno(), fd_out)
            os.dup2(f.fileno(), fd_err)
            yield
        finally:
            try:
                os.dup2(saved_out, fd_out)
                os.dup2(saved_err, fd_err)
            finally:
                with suppress(Exception):
                    os.close(saved_out)
                    os.close(saved_err)
                with suppress(Exception):
                    f.write(
                        f"--- lightgbm redirect end: {datetime.now(UTC).isoformat()}Z ---\n"
                    )
                    f.flush()


@contextmanager
def _redirect_fds_to_devnull():
    """Redirect OS-level stdout/stderr to /dev/null (hard suppress native output)."""

    fd_out = 1
    fd_err = 2
    saved_out = os.dup(fd_out)
    saved_err = os.dup(fd_err)
    with open(os.devnull, "w") as f:
        try:
            os.dup2(f.fileno(), fd_out)
            os.dup2(f.fileno(), fd_err)
            yield
        finally:
            try:
                os.dup2(saved_out, fd_out)
                os.dup2(saved_err, fd_err)
            finally:
                with suppress(Exception):
                    os.close(saved_out)
                    os.close(saved_err)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2:
        return float("nan")
    return float(pd.Series(a).corr(pd.Series(b), method="spearman"))


@dataclass(frozen=True)
class MLConfig:
    algo: str
    target: str
    featureset: str
    train_from: str
    train_to: str
    valid_from: str
    valid_to: str
    params: dict[str, Any]


class MLGBDTRecommender(BaseRecommender):
    """GBDT regressor POC for recommend stage.

    - time-series split only (explicit train/valid windows)
    - test = pipeline run window (ctx.from_date~ctx.to_date)
    """

    type_name = "ml_gbdt"

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else settings.quant_duckdb_path
        self._model = None
        self._feature_names: list[str] = []
        self._algo: str = ""

    def validate(self, config: dict[str, Any]) -> None:
        rec = config.get("recommender", {})
        if rec.get("type") != "ml_gbdt":
            raise ValueError(
                f"ml_gbdt recommender requires recommender.type=ml_gbdt (got {rec.get('type')})"
            )

        top_k = rec.get("top_k")
        if top_k is None or int(top_k) <= 0:
            raise ValueError("recommender.top_k must be a positive int")

        weighting = rec.get("weighting", "equal")
        if weighting not in {"equal", "score_weighted"}:
            raise ValueError(
                "recommender.weighting must be 'equal' or 'score_weighted'"
            )

        model = rec.get("model", {})
        algo = model.get("algo")
        if algo not in {"lightgbm", "xgboost", "catboost"}:
            raise ValueError(
                "recommender.model.algo must be one of: lightgbm, xgboost, catboost"
            )

        target = model.get("target")
        if target not in {"forward_ret_5d", "forward_ret_20d"}:
            raise ValueError(
                "recommender.model.target must be forward_ret_5d or forward_ret_20d"
            )

        featureset = model.get("featureset", "default")
        if featureset != "default":
            raise ValueError(
                "recommender.model.featureset currently supports only 'default'"
            )

        tw = model.get("train_window", {})
        for k in ("train_from", "train_to", "valid_from", "valid_to"):
            if not tw.get(k):
                raise ValueError(f"recommender.model.train_window.{k} is required")

        # time ordering
        tf, tt = _parse_date(tw["train_from"]), _parse_date(tw["train_to"])
        vf, vt = _parse_date(tw["valid_from"]), _parse_date(tw["valid_to"])
        if tf > tt:
            raise ValueError("train_from must be <= train_to")
        if vf > vt:
            raise ValueError("valid_from must be <= valid_to")
        if tt >= vf:
            raise ValueError("train_to must be < valid_from (no overlap)")

    def _read_config(
        self, strategy_config: dict[str, Any]
    ) -> tuple[MLConfig, int, str]:
        rec = strategy_config.get("recommender", {})
        model = rec.get("model", {})
        tw = model.get("train_window", {})
        params = model.get("params", {}) or {}

        cfg = MLConfig(
            algo=model.get("algo", "lightgbm"),
            target=model.get("target", "forward_ret_5d"),
            featureset=model.get("featureset", "default"),
            train_from=tw["train_from"],
            train_to=tw["train_to"],
            valid_from=tw["valid_from"],
            valid_to=tw["valid_to"],
            params=params,
        )

        top_k = int(rec.get("top_k", 10))
        weighting = rec.get("weighting", "equal")
        return cfg, top_k, weighting

    def _load_feature_matrix(
        self,
        *,
        symbols: list[str],
        date_from: str,
        date_to: str,
        feature_version: str,
        feature_names: list[str],
    ) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()
        sym_list = "', '".join([s.upper() for s in symbols])
        feat_list = "', '".join(feature_names)
        conn = duck_connect(self.db_path)
        try:
            q = f"""
                SELECT symbol, ts, feature_name, feature_value
                FROM features_daily
                WHERE symbol IN ('{sym_list}')
                  AND feature_version = '{feature_version}'
                  AND feature_name IN ('{feat_list}')
                  AND ts >= DATE '{date_from}'
                  AND ts <= DATE '{date_to}'
            """
            df_long = conn.execute(q).df()
        finally:
            conn.close()

        if df_long.empty:
            return pd.DataFrame()

        df_long["ts"] = pd.to_datetime(df_long["ts"])
        df_wide = (
            df_long.pivot_table(
                index=["symbol", "ts"],
                columns="feature_name",
                values="feature_value",
                aggfunc=lambda x: x.iloc[0],
            )
            .reset_index()
            .sort_values(["symbol", "ts"])
        )
        df_wide.columns.name = None
        return df_wide

    def _load_forward_return(
        self,
        *,
        symbols: list[str],
        date_from: str,
        date_to: str,
        horizon: int,
    ) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()
        sym_list = "', '".join([s.upper() for s in symbols])

        # Need extra lookahead rows to compute LEAD(close, horizon)
        date_to_fwd = str(
            (_parse_date(date_to) + pd.Timedelta(days=horizon + 3)).date()
        )
        conn = duck_connect(self.db_path)
        try:
            q = f"""
            WITH px AS (
              SELECT
                symbol,
                ts,
                close,
                LEAD(close, {horizon}) OVER (PARTITION BY symbol ORDER BY ts) AS close_fwd
              FROM ohlcv
              WHERE symbol IN ('{sym_list}')
                AND ts >= DATE '{date_from}'
                                AND ts <= DATE '{date_to_fwd}'
              ORDER BY symbol, ts
            )
            SELECT symbol, ts, (close_fwd / close - 1.0) AS y
            FROM px
                        WHERE close_fwd IS NOT NULL
                            AND ts <= DATE '{date_to}'
            """
            df = conn.execute(q).df()
        finally:
            conn.close()

        if df.empty:
            return pd.DataFrame()
        df["ts"] = pd.to_datetime(df["ts"])
        return df

    def _make_model(self, algo: str, params: dict[str, Any]):
        if algo == "lightgbm":
            try:
                import lightgbm as lgb
            except Exception as e:
                raise RuntimeError("lightgbm is not installed") from e
            default = {
                "n_estimators": 300,
                "learning_rate": 0.05,
                "num_leaves": 31,
                "random_state": 42,
                # Suppress LightGBM console output by default
                "verbosity": -1,
            }
            default.update(params)
            return lgb.LGBMRegressor(**default)

        if algo == "xgboost":
            try:
                import xgboost as xgb
            except Exception as e:
                raise RuntimeError("xgboost is not installed") from e
            default = {
                "n_estimators": 500,
                "learning_rate": 0.05,
                "max_depth": 6,
                "subsample": 0.9,
                "colsample_bytree": 0.9,
                "random_state": 42,
            }
            default.update(params)
            return xgb.XGBRegressor(**default)

        if algo == "catboost":
            try:
                from catboost import CatBoostRegressor
            except Exception as e:
                raise RuntimeError("catboost is not installed") from e
            default = {
                "iterations": 500,
                "learning_rate": 0.05,
                "depth": 6,
                "loss_function": "RMSE",
                "random_seed": 42,
                "verbose": False,
            }
            default.update(params)
            return CatBoostRegressor(**default)

        raise ValueError(f"Unknown algo: {algo}")

    def fit(self, ctx: RecommenderContext) -> None:
        strategy_config = ctx.strategy_config
        ml_cfg, _, _ = self._read_config(strategy_config)

        feature_version = (
            strategy_config.get("signal", {}).get("inputs", {}).get("feature_version")
            or "v1"
        )
        feature_names = list(_DEFAULT_FEATURESET_V1)

        horizon = 5 if ml_cfg.target == "forward_ret_5d" else 20

        # Load features for train+valid (labels need horizon future; extend end date)
        max_end = str(_parse_date(ml_cfg.valid_to) + pd.Timedelta(days=horizon + 3))
        df_x = self._load_feature_matrix(
            symbols=ctx.symbols,
            date_from=ml_cfg.train_from,
            date_to=max_end,
            feature_version=feature_version,
            feature_names=feature_names,
        )
        df_y = self._load_forward_return(
            symbols=ctx.symbols,
            date_from=ml_cfg.train_from,
            date_to=max_end,
            horizon=horizon,
        )

        if df_x.empty or df_y.empty:
            raise ValueError(
                "Training data is empty: ensure features_daily and ohlcv exist"
            )

        df = pd.merge(df_x, df_y, on=["symbol", "ts"], how="inner")
        if df.empty:
            raise ValueError("No joined rows between features and labels")

        # Split
        ts = df["ts"]
        train_mask = (ts >= _parse_date(ml_cfg.train_from)) & (
            ts <= _parse_date(ml_cfg.train_to)
        )
        valid_mask = (ts >= _parse_date(ml_cfg.valid_from)) & (
            ts <= _parse_date(ml_cfg.valid_to)
        )

        feature_cols = [c for c in df.columns if c not in {"symbol", "ts", "y"}]
        df_train = df.loc[train_mask].dropna(subset=feature_cols + ["y"]).copy()
        df_valid = df.loc[valid_mask].dropna(subset=feature_cols + ["y"]).copy()

        if df_train.empty or df_valid.empty:
            raise ValueError("train/valid split produced empty dataset")

        # Keep X as DataFrame to preserve feature names and avoid sklearn warnings.
        X_train = df_train[feature_cols].astype(float)
        y_train = df_train["y"].to_numpy(dtype=float)
        X_valid = df_valid[feature_cols].astype(float)
        y_valid = df_valid["y"].to_numpy(dtype=float)

        model = self._make_model(ml_cfg.algo, ml_cfg.params)

        # Suppress external console noise by redirecting native stdout/stderr.
        # Default: hard-suppress LightGBM output.
        # Opt-in: persist LightGBM logs to artifacts when QUANT_LGBM_LOG=1.
        if ml_cfg.algo == "lightgbm":
            log_enabled = os.getenv("QUANT_LGBM_LOG", "0") == "1"
            if log_enabled and ctx.artifacts_dir is not None:
                lgb_log = ctx.artifacts_dir / "stages" / "recommend" / "lightgbm.log"
                with _redirect_fds_to_file(lgb_log):
                    model.fit(X_train, y_train)
            else:
                with _redirect_fds_to_devnull():
                    model.fit(X_train, y_train)
        else:
            model.fit(X_train, y_train)

        yhat_valid = np.asarray(model.predict(X_valid), dtype=float)
        rmse = float(np.sqrt(np.mean((y_valid - yhat_valid) ** 2)))
        mae = float(np.mean(np.abs(y_valid - yhat_valid)))
        rank_ic = _spearman(y_valid, yhat_valid)

        fi = None
        if hasattr(model, "feature_importances_"):
            imp = np.asarray(model.feature_importances_, dtype=float)
            order = np.argsort(-imp)
            fi = [
                {"feature": feature_cols[i], "importance": float(imp[i])}
                for i in order[:10]
            ]

        metrics = {
            "algo": ml_cfg.algo,
            "target": ml_cfg.target,
            "feature_version": feature_version,
            "features": feature_cols,
            "train_window": {
                "train_from": ml_cfg.train_from,
                "train_to": ml_cfg.train_to,
                "valid_from": ml_cfg.valid_from,
                "valid_to": ml_cfg.valid_to,
            },
            "valid_metrics": {
                "rmse": rmse,
                "mae": mae,
                "rank_ic_spearman": rank_ic,
                "n_valid": int(len(y_valid)),
            },
            "feature_importance_top10": fi or [],
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Persist artifacts
        if ctx.artifacts_dir is not None:
            models_dir = ctx.artifacts_dir / "models"
            reports_dir = ctx.artifacts_dir / "reports"
            _safe_mkdir(models_dir)
            _safe_mkdir(reports_dir)

            model_path = models_dir / f"model.{ml_cfg.algo}.joblib"
            joblib.dump(model, model_path)

            metrics_path = reports_dir / "ml_metrics.json"
            metrics_path.write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            summary_path = reports_dir / "ml_summary.md"
            summary_path.write_text(
                "\n".join(
                    [
                        "# ML Summary (ml_gbdt)",
                        f"- algo: {ml_cfg.algo}",
                        f"- target: {ml_cfg.target}",
                        f"- valid RMSE: {rmse:.6f}",
                        f"- valid MAE: {mae:.6f}",
                        f"- valid RankIC (Spearman): {rank_ic:.4f}",
                        f"- n_valid: {len(y_valid)}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

        self._model = model
        self._feature_names = feature_cols
        self._algo = ml_cfg.algo

    def predict(self, ctx: RecommenderContext) -> pd.DataFrame:
        if self._model is None:
            self.fit(ctx)

        strategy_config = ctx.strategy_config
        ml_cfg, _, _ = self._read_config(strategy_config)

        feature_version = (
            strategy_config.get("signal", {}).get("inputs", {}).get("feature_version")
            or "v1"
        )
        feature_names = list(_DEFAULT_FEATURESET_V1)

        df_x = self._load_feature_matrix(
            symbols=ctx.symbols,
            date_from=ctx.from_date,
            date_to=ctx.to_date,
            feature_version=feature_version,
            feature_names=feature_names,
        )
        if df_x.empty:
            return pd.DataFrame(columns=["symbol", "ts", "score"])

        # Align columns to training
        feature_cols = self._feature_names or [
            c for c in df_x.columns if c not in {"symbol", "ts"}
        ]
        for c in feature_cols:
            if c not in df_x.columns:
                df_x[c] = np.nan

        df_x = df_x.dropna(subset=feature_cols).copy()
        if df_x.empty:
            return pd.DataFrame(columns=["symbol", "ts", "score"])

        # Keep X as DataFrame to preserve feature names and avoid sklearn warnings.
        X = df_x[feature_cols].astype(float)
        # Ensure model is available; attempt to (re)train if missing
        if self._model is None:
            self.fit(ctx)
        if self._model is None:
            raise RuntimeError("Model is not trained; cannot predict")

        yhat = np.asarray(self._model.predict(X), dtype=float)

        out = df_x[["symbol", "ts"]].copy()
        out["score"] = yhat

        # Optional predictions dump
        if ctx.artifacts_dir is not None:
            outputs_dir = ctx.artifacts_dir / "outputs"
            _safe_mkdir(outputs_dir)
            out_csv = outputs_dir / "predictions.csv"
            out.to_csv(out_csv, index=False)

        return out

    def generate_targets(self, ctx: RecommenderContext) -> pd.DataFrame:
        strategy_config = ctx.strategy_config
        ml_cfg, top_k, weighting = self._read_config(strategy_config)

        df_pred = self.predict(ctx)
        if df_pred.empty:
            return pd.DataFrame()

        # Ranking per rebalance date (daily by available feature ts)
        # ensure ts is datetime and format as YYYY-MM-DD
        df_pred["ts"] = pd.to_datetime(df_pred["ts"])
        df_pred["asof"] = df_pred["ts"].apply(lambda t: t.strftime("%Y-%m-%d"))

        parts: list[pd.DataFrame] = []
        for _asof, g in df_pred.groupby("asof"):
            gg = g.sort_values("score", ascending=False).head(top_k).copy()
            if gg.empty:
                continue
            if weighting == "equal":
                gg["weight"] = 1.0 / len(gg)
            elif weighting == "score_weighted":
                s = gg["score"].clip(lower=0)
                gg["weight"] = (s / s.sum()) if s.sum() > 0 else 1.0 / len(gg)
            else:
                gg["weight"] = 1.0 / len(gg)

            gg["strategy_id"] = strategy_config["strategy_id"]
            gg["version"] = strategy_config["version"]
            gg["generated_at"] = datetime.now(UTC)
            gg["reason"] = f"ml_gbdt:{ml_cfg.algo}:{ml_cfg.target}"

            parts.append(
                gg[
                    [
                        "strategy_id",
                        "version",
                        "asof",
                        "symbol",
                        "weight",
                        "score",
                        "reason",
                        "generated_at",
                    ]
                ]
            )

        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)
