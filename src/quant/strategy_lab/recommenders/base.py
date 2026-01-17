from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RecommenderContext:
    """Execution context for recommend stage.

    Keep this small: the plugin should remain a pure library component.
    """

    strategy_config: dict[str, Any]
    symbols: list[str]
    from_date: str
    to_date: str
    artifacts_dir: Path | None = None
    duckdb_path: Path | None = None


class BaseRecommender:
    """Recommender plugin interface.

    - factor_rank: deterministic baseline (no fit)
    - ml_gbdt: POC (fit + predict)

    All plugins must emit targets compatible with the existing targets contract.
    """

    type_name: str

    def validate(self, config: dict[str, Any]) -> None:
        """Fail-fast validation of recommender-specific config."""
        raise NotImplementedError

    def fit(self, ctx: RecommenderContext) -> None:
        """Optional training step."""
        return None

    def predict(self, ctx: RecommenderContext) -> pd.DataFrame:
        """Return predictions.

        Expected columns (minimum):
        - symbol (str)
        - ts (datetime64[ns] or date-like)
        - score (float)
        """
        raise NotImplementedError

    def generate_targets(self, ctx: RecommenderContext) -> pd.DataFrame:
        """Generate raw targets dataframe.

        Must contain:
        - symbol, score, weight
        - strategy_id, version, asof, generated_at
        """
        raise NotImplementedError
