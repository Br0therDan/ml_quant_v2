import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class StrategyLoader:
    """
    Loads and validates V2 Strategy YAML files.
    """

    REQUIRED_ROOT_FIELDS = [
        "strategy_id",
        "version",
        "universe",
        "rebalance",
        "portfolio",
        "supervisor",
    ]

    @staticmethod
    def load_yaml(file_path: Path) -> dict[str, Any]:
        """Load YAML file from path."""
        if not file_path.exists():
            raise FileNotFoundError(f"Strategy file not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            try:
                config = yaml.safe_load(f)
                StrategyLoader.validate_schema(config)
                return config
            except yaml.YAMLError as e:
                logger.error(f"YAML parsing error in {file_path}: {e}")
                raise
            except ValueError as e:
                logger.error(f"Validation error in {file_path}: {e}")
                raise

    @staticmethod
    def validate_schema(config: dict[str, Any]):
        """Basic schema validation for V2."""
        if not config:
            raise ValueError("Empty strategy configuration.")

        # Check required root fields
        missing = [f for f in StrategyLoader.REQUIRED_ROOT_FIELDS if f not in config]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Universe validation
        universe = config.get("universe", {})
        if "type" not in universe:
            raise ValueError("Universe must have a 'type'.")

        # Signal/Recommender validation
        # - Backward compatible: legacy uses `signal`
        # - V2 ML POC path: `recommender` (plugin) is optional
        has_signal = "signal" in config and isinstance(config.get("signal"), dict)
        has_recommender = "recommender" in config and isinstance(
            config.get("recommender"), dict
        )

        if not has_signal and not has_recommender:
            raise ValueError("Strategy must have either 'signal' or 'recommender'.")

        if has_signal:
            signal = config.get("signal", {})
            if "type" not in signal:
                raise ValueError("Signal must have a 'type'.")

            if signal["type"] == "factor_rank":
                inputs = signal.get("inputs", {})
                if not inputs.get("feature_name") or not inputs.get("feature_version"):
                    raise ValueError(
                        "factor_rank signal requires feature_name and feature_version."
                    )
            elif signal["type"] == "model_score":
                inputs = signal.get("inputs", {})
                if not inputs.get("model_id"):
                    raise ValueError("model_score signal requires model_id.")
            else:
                raise ValueError(f"Unsupported signal type: {signal['type']}")

        if has_recommender:
            recommender = config.get("recommender", {})
            rtype = recommender.get("type")
            if rtype not in {"factor_rank", "ml_gbdt"}:
                raise ValueError(
                    "Unsupported recommender.type: must be factor_rank or ml_gbdt"
                )

            # Defaults
            if "top_k" in recommender:
                try:
                    top_k = int(recommender.get("top_k"))
                except Exception:
                    raise ValueError("recommender.top_k must be an int")
                if top_k <= 0:
                    raise ValueError("recommender.top_k must be > 0")

            weighting = recommender.get("weighting", "equal")
            if weighting not in {"equal", "score_weighted"}:
                raise ValueError(
                    "recommender.weighting must be 'equal' or 'score_weighted'"
                )

            if rtype == "ml_gbdt":
                model = recommender.get("model", {})
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
                        raise ValueError(
                            f"recommender.model.train_window.{k} is required"
                        )

        # Portfolio validation
        portfolio = config.get("portfolio", {})
        if "top_k" not in portfolio:
            raise ValueError("Portfolio must have 'top_k'.")

        logger.info(
            f"Strategy '{config['strategy_id']}' (v{config.get('version')}) validated successfully."
        )
