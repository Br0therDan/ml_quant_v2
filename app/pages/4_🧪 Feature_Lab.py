import contextlib
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from app.ui.charts import (
    plot_correlation_matrix,
    plot_feature_analysis,
    plot_feature_distribution,
)
from app.ui.data_access import get_duckdb_connection, load_active_symbols

st.set_page_config(
    page_title="Feature Lab | Quant Lab V2",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Feature Lab", help="Feature Analysis and Visualization")
st.caption(
    "⚠️ 피처 계산 실행은 Run Center에서만 가능합니다. 여기는 계산 결과 분석/시각화 전용입니다."
)
# --- Layout ---
col_controls, col_results = st.columns([0.2, 0.8], gap="small")

with col_controls, st.container(border=True, height="stretch"):
    st.subheader("Configuration")

    # Universe
    active_symbols = load_active_symbols()
    all_syms = [s.symbol for s in active_symbols] if active_symbols else []

    scope_mode = st.radio("Scope", ["Single Symbol", "Universe"], horizontal=True)

    selected_symbols = []
    if scope_mode == "Single Symbol":
        selected_symbols = [st.selectbox("Symbol", all_syms)] if all_syms else []
    else:
        selected_symbols = st.multiselect(
            "Symbols",
            all_syms,
            default=all_syms[:3] if len(all_syms) > 3 else all_syms,
        )

    # Date Range
    today = datetime.today()
    start_date = st.date_input("From", today - timedelta(days=365))
    end_date = st.date_input("To", today)

    # Presets (Mockup logic for V2 specific features)
    st.markdown("---")
    st.caption("Feature Selection")
    preset = st.selectbox(
        "Preset", ["All", "Trend", "Volatility", "Momentum", "Custom"]
    )

    st.markdown("---")
    st.caption(
        "새 피처 계산을 원하면 Run Center에서 pipeline 또는 features 단계를 실행하세요."
    )

with col_results:
    with st.container(border=True, height=800):
        st.subheader("Analysis Results")

        if not selected_symbols:
            st.info("Select symbols to analyze.")
        else:
            # Load Features for selected symbols
            try:
                conn = get_duckdb_connection()
                syms_str = ",".join([f"'{s}'" for s in selected_symbols])

                # Pivot features: symbol, ts, feature_name -> columns
                # This complex query might be heavy. For MVP, load wide format?
                # V2 features_daily table: symbol, ts, feature_name, feature_value

                query = f"""
                    SELECT symbol, ts, feature_name, feature_value
                    FROM features_daily
                    WHERE symbol IN ({syms_str})
                    AND ts BETWEEN '{start_date}' AND '{end_date}'
                    AND feature_version = 'v1'
                """

                # Defensive DB handling: get_duckdb_connection() may return None or execute() may behave differently.
                df_long = pd.DataFrame()
                if conn is None:
                    st.error("Failed to obtain DuckDB connection.")
                else:
                    try:
                        res = conn.execute(query)
                        if res is None:
                            # fallback: attempt to use alternative APIs if present
                            if hasattr(conn, "query"):
                                try:
                                    df_long = conn.query(query).to_df()
                                except Exception:
                                    df_long = pd.DataFrame()
                            else:
                                df_long = pd.DataFrame()
                        else:
                            # try common result methods
                            try:
                                df_long = res.df()
                            except Exception:
                                try:
                                    df_long = res.fetchdf()
                                except Exception:
                                    df_long = pd.DataFrame()
                    finally:
                        with contextlib.suppress(Exception):
                            conn.close()

                if df_long.empty:
                    st.warning("No feature data found.")
                else:
                    # Pivot for analysis
                    # Multi-index pivot (ts, symbol) -> features
                    df_wide = df_long.pivot_table(
                        index=["ts", "symbol"],
                        columns="feature_name",
                        values="feature_value",
                    ).reset_index()

                    # Tabs
                    t_ts, t_dist, t_corr, t_miss = st.tabs(
                        ["Timeseries", "Distribution", "Correlation", "Missingness"]
                    )

                    feature_cols = [
                        c for c in df_wide.columns if c not in ["ts", "symbol"]
                    ]

                    with t_ts:
                        # Filter by feature preset logic (simple name match)
                        disp_cols = feature_cols
                        if preset == "Trend":
                            disp_cols = [
                                c
                                for c in feature_cols
                                if any(x in c.lower() for x in ["sma", "ema"])
                            ]
                        elif preset == "Volatility":
                            disp_cols = [
                                c
                                for c in feature_cols
                                if any(x in c.lower() for x in ["std", "atr", "width"])
                            ]

                        if not disp_cols:
                            st.info(
                                f"No features match preset '{preset}'. Showing all."
                            )
                            disp_cols = feature_cols

                        # Plot for first symbol only to avoid mess
                        sym_ts = selected_symbols[0]
                        df_sym = df_wide[df_wide["symbol"] == sym_ts].sort_values("ts")

                        fig_line = plot_feature_analysis(df_sym[["ts"] + disp_cols])
                        # normalize possible tuple returns (e.g., (fig, meta)) to a single Figure or None
                        fig_to_show = None
                        if isinstance(fig_line, tuple):
                            for item in fig_line:
                                if item is not None:
                                    fig_to_show = item
                                    break
                        else:
                            fig_to_show = fig_line

                        if fig_to_show is not None:
                            st.plotly_chart(fig_to_show, width="stretch")
                            st.caption(f"Shown for representative symbol: {sym_ts}")

                    with t_dist:
                        target_feat = st.selectbox(
                            "Select Feature for Distribution", feature_cols
                        )
                        if target_feat:
                            # Aggregate across selected symbols or just all data
                            fig_dist = plot_feature_distribution(df_wide, target_feat)
                            st.plotly_chart(fig_dist, width="stretch")

                    with t_corr:
                        if len(feature_cols) > 1:
                            df_corr = df_wide[feature_cols].corr()
                            fig_corr = plot_correlation_matrix(df_corr)
                            st.plotly_chart(fig_corr, width="stretch")
                        else:
                            st.info("Need at least 2 features for correlation.")

                    with t_miss:
                        # Missingness Summary
                        missing = df_wide[feature_cols].isna().mean()
                        missing_df = pd.DataFrame(
                            missing, columns=["Missing Ratio"]
                        ).sort_values("Missing Ratio", ascending=False)
                        st.dataframe(missing_df.style.format("{:.2%}"), width="stretch")

            except Exception as e:
                st.error(f"Analysis Failed: {e}")
