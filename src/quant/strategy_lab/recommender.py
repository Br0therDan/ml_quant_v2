from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .recommenders import (
    BaseRecommender,
    FactorRankRecommender,
    MLGBDTRecommender,
    RecommenderContext,
)


class Recommender:
    """Recommender facade.

    Non-negotiable baseline:
    - factor_rank remains the default engine.

    Optional plugin:
    - ml_gbdt (GBDT POC) when strategy YAML specifies recommender.type=ml_gbdt.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def _select_engine(self, strategy_config: dict[str, Any]) -> BaseRecommender:
        rec_cfg = strategy_config.get("recommender")
        if isinstance(rec_cfg, dict) and rec_cfg.get("type") == "ml_gbdt":
            return MLGBDTRecommender(db_path=self.db_path)
        # default baseline
        return FactorRankRecommender(db_path=self.db_path)

    def generate_targets(self, config: dict[str, Any], asof: str) -> pd.DataFrame:
        """Backward-compatible API used by `quant recommend`.

        For ml_gbdt, this will train on train_window and predict on a single asof date.
        """

        engine = self._select_engine(config)
        engine.validate(config)

        ctx = RecommenderContext(
            strategy_config=config,
            symbols=(config.get("universe", {}).get("symbols") or []),
            from_date=asof,
            to_date=asof,
            artifacts_dir=None,
            duckdb_path=None,
        )
        return engine.generate_targets(ctx)

    def generate_targets_for_window(
        self,
        *,
        config: dict[str, Any],
        symbols: list[str],
        from_date: str,
        to_date: str,
        artifacts_dir: Path | None = None,
    ) -> pd.DataFrame:
        """Pipeline API: generate targets for a date window.

        - factor_rank: current V2 behavior is typically 'asof=to_date' only.
        - ml_gbdt: generates Top-K targets per available rebalance date.
        """

        engine = self._select_engine(config)
        engine.validate(config)

        ctx = RecommenderContext(
            strategy_config=config,
            symbols=symbols,
            from_date=from_date,
            to_date=to_date,
            artifacts_dir=artifacts_dir,
            duckdb_path=None,
        )

        # Keep baseline behavior unchanged: single-date asof=to_date
        if getattr(engine, "type_name", "") == "factor_rank":
            ctx_single = RecommenderContext(
                strategy_config=config,
                symbols=symbols,
                from_date=to_date,
                to_date=to_date,
                artifacts_dir=artifacts_dir,
                duckdb_path=None,
            )
            return engine.generate_targets(ctx_single)

        return engine.generate_targets(ctx)
