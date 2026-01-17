from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ...config import settings
from ...db.duck import connect as duck_connect
from .base import BaseRecommender, RecommenderContext


class FactorRankRecommender(BaseRecommender):
    """Deterministic baseline: rank by a single factor, take Top-K."""

    type_name = "factor_rank"

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(settings.quant_duckdb_path)

    def validate(self, config: dict[str, Any]) -> None:
        signal = config.get("signal", {})
        if signal.get("type") != "factor_rank":
            raise ValueError(
                f"factor_rank recommender requires signal.type=factor_rank (got {signal.get('type')})"
            )

        inputs = signal.get("inputs", {})
        if not inputs.get("feature_name") or not inputs.get("feature_version"):
            raise ValueError(
                "factor_rank requires signal.inputs.feature_name/feature_version"
            )

        portfolio = config.get("portfolio", {})
        if "top_k" not in portfolio:
            raise ValueError("portfolio.top_k is required")

    def _load_features(
        self,
        *,
        version: str,
        feature_name: str,
        asof: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        conn = duck_connect(Path(self.db_path))
        try:
            query = f"""
                SELECT symbol, feature_value as score
                FROM features_daily
                WHERE feature_version = '{version}'
                  AND feature_name = '{feature_name}'
                  AND ts = DATE '{asof}'
            """
            if symbols:
                sym_list = "', '".join(symbols)
                query += f" AND symbol IN ('{sym_list}')"

            return conn.execute(query).df()
        finally:
            conn.close()

    def predict(self, ctx: RecommenderContext) -> pd.DataFrame:
        # factor_rank is not a model; return score series for the single asof date.
        cfg = ctx.strategy_config
        signal = cfg.get("signal", {})
        inputs = signal.get("inputs", {})
        f_version = inputs.get("feature_version")
        f_name = inputs.get("feature_name")

        asof = ctx.to_date
        df = self._load_features(
            version=f_version,
            feature_name=f_name,
            asof=asof,
            symbols=ctx.symbols or None,
        )
        if df.empty:
            return pd.DataFrame(columns=["symbol", "ts", "score"])
        df["ts"] = pd.to_datetime(asof)
        return df[["symbol", "ts", "score"]]

    def generate_targets(self, ctx: RecommenderContext) -> pd.DataFrame:
        cfg = ctx.strategy_config
        portfolio = cfg.get("portfolio", {})

        df = self.predict(ctx)
        if df.empty:
            return pd.DataFrame()

        df = df.sort_values(by="score", ascending=False).reset_index(drop=True)

        top_k = int(portfolio.get("top_k", 5))
        df_top = df.head(top_k).copy()

        weighting = portfolio.get("weighting", "equal")
        if weighting == "equal":
            df_top["weight"] = 1.0 / len(df_top)
        elif weighting == "score_weighted":
            scores = df_top["score"].clip(lower=0)
            df_top["weight"] = (
                (scores / scores.sum()) if scores.sum() > 0 else 1.0 / len(df_top)
            )
        else:
            df_top["weight"] = 1.0 / len(df_top)

        df_top["strategy_id"] = cfg["strategy_id"]
        df_top["version"] = cfg["version"]
        df_top["asof"] = ctx.to_date
        df_top["generated_at"] = datetime.now(UTC)

        return df_top[
            [
                "strategy_id",
                "version",
                "asof",
                "symbol",
                "weight",
                "score",
                "generated_at",
            ]
        ]
