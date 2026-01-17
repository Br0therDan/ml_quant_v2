import os
import sqlite3
from collections import namedtuple

import duckdb
import pandas as pd
import streamlit as st

from quant.config import settings

DB_PATH = str(settings.quant_duckdb_path)
META_DB_PATH = str(settings.quant_sqlite_path)


# Removed caching to avoid closed connection issues
def get_duckdb_connection():
    """
    Returns a read-only DuckDB connection.
    For local DuckDB, read_only=True is essential for concurrency.
    """
    if not os.path.exists(DB_PATH):
        # Allow creating if not exists? No, should exist from ingest.
        # But for first run, maybe return None.
        pass

    try:
        # Note: In Streamlit, persistent DuckDB connections can sometimes trigger
        # pybind11 'instance allocation failed' errors during reloads.
        return duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        st.error(f"Failed to connect to DB: {e}")
        return None


# Alias for backward compatibility if needed
get_db_connection = get_duckdb_connection


def run_query(query, params=None):
    """Helper to run a query and return a dataframe, handling connection lifecycle."""
    conn = get_duckdb_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        if params:
            return conn.execute(query, params).df()
        else:
            return conn.execute(query).df()
    except Exception as e:
        st.error(f"Query Error: {e}")
        return pd.DataFrame()


def get_meta_connection():
    # Ensure directory exists for meta db if strictly needed? No, it should exist.
    if not os.path.exists(META_DB_PATH):
        return None
    try:
        return sqlite3.connect(META_DB_PATH, check_same_thread=False)
    except Exception:
        return None


def load_runs(limit=100):
    conn = get_meta_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        try:
            limit_i = int(limit)
        except Exception:
            limit_i = 100
        limit_i = max(1, min(limit_i, 1000))
        df = pd.read_sql(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
            conn,
            params=[limit_i],
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


# Symbol definition for caching
Symbol = namedtuple("Symbol", ["symbol"])


@st.cache_data(ttl=60)
def load_active_symbols():
    """Load active symbols from SQLite metadata DB."""
    conn = get_meta_connection()
    if conn is None:
        return []
    try:
        df = pd.read_sql(
            "SELECT symbol FROM symbols WHERE is_active = 1 ORDER BY symbol", conn
        )
        conn.close()
        return [Symbol(row["symbol"]) for _, row in df.iterrows()]
    except Exception:
        return []


@st.cache_data(ttl=60)
def load_symbol_inventory():
    """
    Combined inventory: metadata from SQLite + OHLCV stats from DuckDB.
    """
    # 1. Get Symbols from SQLite
    meta_conn = get_meta_connection()
    if meta_conn is None:
        return pd.DataFrame()
    df_meta = pd.read_sql(
        "SELECT symbol, name, currency FROM symbols WHERE is_active = 1", meta_conn
    )
    meta_conn.close()

    # 2. Get Stats from DuckDB
    df_stats = load_ohlcv_summary()

    # 3. Merge
    if df_stats.empty:
        df_meta["count"] = 0
        df_meta["min_date"] = None
        df_meta["max_date"] = None
        return df_meta

    df_inventory = pd.merge(df_meta, df_stats, on="symbol", how="left")
    df_inventory["count"] = df_inventory["count"].fillna(0).astype(int)

    return df_inventory.sort_values("symbol")


@st.cache_data(ttl=60)  # Cache for 60 seconds
def load_ohlcv_summary(_conn_placeholder=None):
    query = """
    SELECT symbol, count(*) as count, min(ts) as min_date, max(ts) as max_date 
    FROM ohlcv 
    GROUP BY symbol
    ORDER BY symbol
    """
    return run_query(query)


@st.cache_data(ttl=60)
def load_ohlcv(symbol, from_date, to_date):
    q = """
                SELECT ts, open, high, low, close, volume
                FROM ohlcv
                WHERE symbol = ?
                    AND ts >= CAST(? AS DATE)
                    AND ts <= CAST(? AS DATE)
                ORDER BY ts
        """
    return run_query(q, params=[symbol, from_date, to_date])


@st.cache_data(ttl=60)
def load_features(symbol, from_date, to_date):
    # Pivot features: ts | feature_name...
    try:
        q = """
            SELECT ts, feature_name, feature_value
            FROM features_daily
            WHERE symbol = ?
              AND ts >= CAST(? AS DATE)
              AND ts <= CAST(? AS DATE)
        """
        df = run_query(q, params=[symbol, from_date, to_date])
        if df.empty:
            return df
        return df.pivot(
            index="ts", columns="feature_name", values="feature_value"
        ).reset_index()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_labels(symbol, from_date, to_date):
    try:
        q = """
            SELECT ts, label_name, label_value
            FROM labels
            WHERE symbol = ?
              AND ts >= CAST(? AS DATE)
              AND ts <= CAST(? AS DATE)
        """
        df = run_query(q, params=[symbol, from_date, to_date])
        if df.empty:
            return df
        return df.pivot(
            index="ts", columns="label_name", values="label_value"
        ).reset_index()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_targets(strategy_id=None, asof=None):
    where_parts = ["1=1"]
    params = []

    if strategy_id and strategy_id != "All":
        where_parts.append("strategy_id = ?")
        params.append(strategy_id)
    if asof:
        where_parts.append("study_date = CAST(? AS DATE)")
        params.append(asof)

    where_sql = " AND ".join(where_parts)
    q = (
        "\n".join(
            [
                "SELECT strategy_id, study_date as asof, symbol, weight, score, approved, reason",
                "FROM targets",
                "WHERE " + where_sql,
                "ORDER BY study_date DESC, strategy_id, weight DESC",
            ]
        )
        + "\n"
    )
    return run_query(q, params=params)


@st.cache_data(ttl=10)  # Shorter cache for run summary updates
def load_backtest_summary(limit=100):
    query = """
    SELECT 
        run_id, strategy_id, from_ts, to_ts, n_days, 
        cagr, sharpe, max_dd, mean_daily_return, std_daily_return, 
        annual_factor, turnover, created_at, win_rate
    FROM backtest_summary
    ORDER BY created_at DESC
    LIMIT ?
    """
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 100
    limit_i = max(1, min(limit_i, 1000))
    return run_query(query, params=[limit_i])


@st.cache_data(ttl=60)
def load_backtest_trades(run_id):
    query = "SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY entry_ts"
    return run_query(query, params=[run_id])


@st.cache_data(ttl=10)
def load_pipeline_summary(limit=5):
    """
    Returns the latest run status for each pipeline step or a set of recent runs.
    """
    conn = get_meta_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        # Just return raw runs for parsing
        try:
            limit_i = int(limit)
        except Exception:
            limit_i = 5
        limit_i = max(1, min(limit_i, 500))
        q = "SELECT kind, status, started_at, ended_at, run_id, error_text, parent_run_id as parent FROM runs ORDER BY started_at DESC LIMIT ?"
        df = pd.read_sql(q, conn, params=[limit_i])
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_pipeline_status():
    """
    Returns a dict mapping stage -> {status, last_run, ...}
    """
    stages = ["ingest", "features", "labels", "recommend", "backtest"]

    # 1) Prefer artifacts SSOT (run.json + stages/*/result.json)
    try:
        from app.ui.run_artifacts import list_runs_from_run_json, list_stage_results

        runs = [
            r
            for r in (list_runs_from_run_json() or [])
            if str(r.get("kind") or "") == "pipeline"
        ]
        if runs:
            latest = runs[0]
            run_id = str(latest.get("run_id") or "").strip()
            run_status = str(latest.get("status") or "").strip().lower()
            results = list_stage_results(run_id) if run_id else {}

            status_map: dict[str, dict] = {}
            for stage in stages:
                r = results.get(stage)
                if isinstance(r, dict):
                    ok = r.get("ok")
                    if isinstance(ok, bool):
                        status = "success" if ok else "fail"
                    else:
                        status = str(r.get("status") or "").strip().lower() or "pending"
                    status_map[stage] = {
                        "status": status,
                        "last_run": latest.get("ended_at")
                        or latest.get("started_at")
                        or "-",
                    }
                else:
                    status_map[stage] = {
                        "status": "running" if run_status == "running" else "pending",
                        "last_run": latest.get("ended_at")
                        or latest.get("started_at")
                        or "-",
                    }
            return status_map
    except Exception:
        # If artifacts scan fails, fall back to legacy SQLite below.
        pass

    # 2) Legacy fallback: SQLite meta DB
    df = load_pipeline_summary(limit=50)
    status_map = {}
    if df.empty:
        return status_map

    for stage in stages:
        row = df[df["kind"] == stage]
        if not row.empty:
            last = row.iloc[0]
            status_map[stage] = {
                "status": last["status"],
                "last_run": last["ended_at"] or last["started_at"],
            }
        else:
            status_map[stage] = {"status": "pending", "last_run": "-"}
    return status_map


@st.cache_data(ttl=2)
def load_run_status(run_id: str) -> dict:
    """Load a single run row from SQLite meta DB."""
    conn = get_meta_connection()
    if conn is None:
        return {}
    try:
        df = pd.read_sql(
            "SELECT run_id, kind, status, started_at, ended_at, error_text, parent_run_id as parent FROM runs WHERE run_id = ?",
            conn,
            params=[run_id],
        )
        conn.close()
        if df.empty:
            return {}
        return df.iloc[0].to_dict()
    except Exception:
        return {}


@st.cache_data(ttl=2)
def load_stage_runs(parent_run_id: str) -> pd.DataFrame:
    """Load child stage runs for a pipeline run_id."""
    conn = get_meta_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql(
            "SELECT run_id, kind, status, started_at, ended_at, error_text FROM runs WHERE parent_run_id = ? ORDER BY started_at ASC",
            conn,
            params=[parent_run_id],
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def load_system_health():
    return {
        "duckdb_ok": os.path.exists(DB_PATH),
        "sqlite_ok": os.path.exists(META_DB_PATH),
        "last_ingest": "-",  # Implement real check if needed
        "last_backtest": "-",
    }


@st.cache_data(ttl=60)
def load_latest_targets_snapshot(limit=5):
    """
    Aggregates target data for the most recent study_date.
    """
    # 1. Get latest date
    date_df = run_query("SELECT MAX(study_date) as last_date FROM targets")
    if date_df.empty or date_df.iloc[0]["last_date"] is None:
        return pd.DataFrame()

    last_date = date_df.iloc[0]["last_date"]

    # 2. Aggregate
    q = """
    SELECT 
        strategy_id as strategy,
        COUNT(*) as positions,
        AVG(CASE WHEN approved THEN 1.0 ELSE 0.0 END) as approved_ratio,
        STRING_AGG(CASE WHEN approved THEN symbol ELSE NULL END, ', ') as top_symbols
    FROM targets
    WHERE study_date = CAST(? AS DATE)
    GROUP BY strategy_id
    ORDER BY strategy_id
    LIMIT ?
    """
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 5
    limit_i = max(1, min(limit_i, 1000))
    df = run_query(q, params=[str(last_date), limit_i])
    return df


@st.cache_data(ttl=60)
def load_targets_comparison(strategy_id, asof):
    """
    Compare current targets with previous date's targets for the same strategy.
    """
    # 1. Get current
    df_curr = load_targets(strategy_id, asof)
    if df_curr.empty:
        return pd.DataFrame()

    # 2. Get previous date
    all_dates = run_query(
        "SELECT DISTINCT study_date FROM targets WHERE strategy_id = ? ORDER BY study_date DESC",
        params=[strategy_id],
    )
    if len(all_dates) < 2:
        return pd.DataFrame()

    # Simple logic: just pick the one immediately before
    dates_list = all_dates["study_date"].tolist()
    try:
        idx = dates_list.index(pd.to_datetime(asof).date())
        if idx + 1 >= len(dates_list):
            return pd.DataFrame()
        prev_asof = dates_list[idx + 1]
    except Exception:
        prev_asof = dates_list[1]  # Fallback to second latest

    df_prev = load_targets(strategy_id, str(prev_asof))

    # 3. Merge
    merged = pd.merge(
        df_curr[["symbol", "weight"]].rename(columns={"weight": "weight_curr"}),
        df_prev[["symbol", "weight"]].rename(columns={"weight": "weight_prev"}),
        on="symbol",
        how="outer",
    ).fillna(0)

    merged["weight_delta"] = merged["weight_curr"] - merged["weight_prev"]
    return merged


@st.cache_data(ttl=60)
def load_targets_history(strategy_id):
    """
    Aggregated historical stats for a strategy.
    """
    q = """
    SELECT 
        study_date as asof,
        COUNT(*) as positions,
        AVG(CASE WHEN approved THEN 1.0 ELSE 0.0 END) as approved_ratio
    FROM targets
    WHERE strategy_id = ?
    GROUP BY study_date
    ORDER BY study_date
    """
    return run_query(q, params=[strategy_id])
