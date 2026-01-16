import pandas as pd
import logging
import json
from datetime import datetime
from ..db.duck import connect as duck_connect
from ..config import settings

log = logging.getLogger(__name__)


def save_targets(df: pd.DataFrame):
    """Save finalized targets to DuckDB ensuring strict schema compliance."""
    if df.empty:
        return

    df_db = df.copy()

    # 1. Rename 'asof' to 'study_date' if needed
    if "asof" in df_db.columns and "study_date" not in df_db.columns:
        df_db = df_db.rename(columns={"asof": "study_date"})

    # 2. Add/Fill missing columns
    required_cols = [
        "strategy_id",
        "version",
        "study_date",
        "symbol",
        "weight",
        "score",
        "approved",
        "risk_flags",
        "reason",
        "generated_at",
    ]

    # Defaults for missing columns
    defaults = {
        "version": "v1",  # Default if missing
        "score": 0.0,
        "approved": False,
        "risk_flags": "",
        "reason": "",
        "generated_at": datetime.utcnow(),
    }

    for col in required_cols:
        if col not in df_db.columns:
            val = defaults.get(col)
            if val is not None:
                df_db[col] = val
            else:
                # Critical column missing (e.g. strategy_id, symbol, weight, study_date)
                # Assuming they exist or we fail.
                pass

    # 3. Type Conversion
    df_db["study_date"] = pd.to_datetime(df_db["study_date"]).dt.date
    df_db["generated_at"] = pd.to_datetime(df_db["generated_at"])
    df_db["approved"] = df_db["approved"].astype(bool)

    # helper for list -> str
    def to_str(x):
        if isinstance(x, (list, dict)):
            return json.dumps(x)
        return str(x) if pd.notnull(x) else ""

    if "risk_flags" in df_db.columns:
        df_db["risk_flags"] = df_db["risk_flags"].apply(to_str)

    if "reason" in df_db.columns:
        df_db["reason"] = df_db["reason"].fillna("")

    # 4. Strict Column Selection
    df_db = df_db[required_cols]

    conn = duck_connect(settings.quant_duckdb_path)
    try:
        strategy_id = df_db.iloc[0]["strategy_id"]
        study_date = df_db.iloc[0]["study_date"]

        # Delete existing for the same strategy/date
        conn.execute(
            "DELETE FROM targets WHERE strategy_id = ? AND study_date = ?",
            (strategy_id, str(study_date)),
        )

        # Insert using register/append
        conn.register("df_targets_tmp", df_db)

        # Explicit column list for insert
        cols_str = ", ".join(required_cols)
        conn.execute(
            f"INSERT INTO targets ({cols_str}) SELECT {cols_str} FROM df_targets_tmp"
        )

        # Per-date logging can get very noisy during windowed recommend runs.
        # Keep this at DEBUG; the pipeline will emit an aggregated summary/progress.
        log.debug(
            f"Successfully saved {len(df_db)} targets for {strategy_id} on {study_date}"
        )
    finally:
        conn.close()


def save_targets_many(df: pd.DataFrame):
    """Save targets for one or many asof/study_date values.

    - Backward-compatible wrapper around save_targets.
    - If df contains multiple dates, we upsert per date (delete+insert).
    """
    if df is None or df.empty:
        return

    if "study_date" in df.columns:
        key = "study_date"
    elif "asof" in df.columns:
        key = "asof"
    else:
        save_targets(df)
        return

    # Normalize key for stable grouping
    tmp = df.copy()
    tmp[key] = pd.to_datetime(tmp[key]).dt.strftime("%Y-%m-%d")

    for _, g in tmp.groupby(key):
        save_targets(g)
