import yaml
from typing import Dict, List, Tuple, Any


# NOTE: UI validator must not be stricter than the pipeline loader contract.
# Pipeline uses StrategyLoader.validate_schema(). We align required fields here.
REQUIRED_ROOT_FIELDS = [
    "strategy_id",
    "version",
    "universe",
    "rebalance",
    "portfolio",
    "supervisor",
]

# Optional-but-recommended fields for better UX / forward compatibility.
RECOMMENDED_ROOT_FIELDS = [
    # Backward compatible legacy path uses `signal`
    "signal",
    # ML plugin path uses `recommender`
    "recommender",
    # Docs may mention these; pipeline does not require them at load time.
    "execution",
    "backtest",
]


def validate_strategy_yaml_with_warnings(
    content: str,
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate YAML syntax and minimal schema requirements.
    Returns (is_valid, error_messages, warning_messages).

    - Missing REQUIRED_* fields => error
    - Missing RECOMMENDED_* fields => warning
    - Must have either `signal` or `recommender` => error (aligned with StrategyLoader)
    """
    errors = []
    warnings: list[str] = []
    try:
        if content is None:
            content = ""
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return False, ["Invalid YAML structure: Root must be an object."], []

        # 1. Missing fields
        missing = [f for f in REQUIRED_ROOT_FIELDS if f not in data]
        if missing:
            errors.append(f"Missing required root fields: {', '.join(missing)}")

        missing_reco = [f for f in RECOMMENDED_ROOT_FIELDS if f not in data]
        if missing_reco:
            warnings.append(
                f"Missing recommended root fields: {', '.join(missing_reco)}"
            )

        # 1b. Signal/Recommender presence (one-of)
        has_signal = "signal" in data and isinstance(data.get("signal"), dict)
        has_recommender = "recommender" in data and isinstance(
            data.get("recommender"), dict
        )
        if not has_signal and not has_recommender:
            errors.append("Strategy must have either 'signal' or 'recommender'.")

        # 2. Type checks (Basic)
        if "universe" in data and not isinstance(data["universe"], dict):
            errors.append("'universe' must be an object.")

        if "backtest" in data:
            bt = data["backtest"]
            if not isinstance(bt, dict):
                errors.append("'backtest' must be an object.")
            else:
                # Backtest block is optional; if present, require minimal shape.
                if "from" not in bt or "to" not in bt:
                    errors.append("'backtest' requires 'from' and 'to' dates.")

        return len(errors) == 0, errors, warnings

    except yaml.YAMLError as e:
        return False, [f"YAML Syntax Error: {str(e)}"], []
    except Exception as e:
        return False, [f"Unexpected validation error: {str(e)}"], []


def validate_strategy_yaml(content: str) -> Tuple[bool, List[str]]:
    """Legacy API: returns only (is_valid, errors)."""
    ok, errors, _warnings = validate_strategy_yaml_with_warnings(content)
    return ok, errors


def extract_strategy_summary(content: str) -> Dict[str, Any]:
    """Extract key info for display cards (best effort)."""
    try:
        data = yaml.safe_load(content)
        if not data:
            return {}

        signal_type = data.get("signal", {}).get("type")
        if not signal_type:
            signal_type = data.get("recommender", {}).get("type")

        return {
            "id": data.get("strategy_id", "N/A"),
            "universe": data.get("universe", {}).get("type", "N/A"),
            "symbols_count": len(data.get("universe", {}).get("symbols", [])),
            "signal": signal_type or "N/A",
            "rebalance": data.get("rebalance", {}).get("frequency", "N/A"),
            "top_k": data.get("portfolio", {}).get("top_k", "N/A"),
        }
    except:
        return {}
