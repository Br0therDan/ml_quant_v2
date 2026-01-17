import plotly.express as px
import streamlit as st

from app.ui.data_access import (
    load_targets,
    load_targets_comparison,
    load_targets_history,
)
from app.ui.kpi import format_df_for_display

st.set_page_config(page_title="Targets Analyzer", layout="wide", page_icon="🎯")

# # --- Sidebar Title ---
# st.sidebar.title("🎯 Targets Analyzer")

# --- Page Title ---
st.title(
    "🎯 Targets Analyzer",
    help="Strategy target result analysis and visualization. Execution (including recommendations and backtests) is only available in Run Center.",
)
st.caption(
    "⚠️ Targets Analyzer는 결과 분석 전용입니다.실행(추천/백테스트 포함)은 Run Center에서만 가능합니다."
)

# run_center_cta(
#     title="⚠️ ",
#     body="Targets Analyzer는 결과 분석 전용입니다.",
# )

# --- Layout: 2-Panel ---
ctrl_col, res_col = st.columns([0.28, 0.72], gap="small")

with ctrl_col, st.container(border=True, height="stretch"):
    st.subheader("Controls")

    # 1. Strategy & Date Selection
    all_targets = load_targets()
    strategies = (
        sorted(all_targets["strategy_id"].unique().tolist())
        if not all_targets.empty
        else []
    )
    sel_strat = st.selectbox("Strategy", strategies)

    dates = []
    if sel_strat:
        dates = sorted(
            all_targets[all_targets["strategy_id"] == sel_strat]["asof"]
            .unique()
            .tolist(),
            reverse=True,
        )
    sel_asof = st.selectbox("Asof Date", dates)

    st.divider()

    # 2. Filters
    approved_only = st.toggle("Approved Only", value=False)
    min_score = st.slider("Min Score", 0.0, 1.0, 0.0, 0.05)
    top_n = st.slider("Top N Symbols", 1, 100, 20)
    compare_prev = st.checkbox("Compare with Prev Asof", value=True)

with res_col, st.container(border=True, height="stretch"):
    if not sel_strat or not sel_asof:
        st.info("Select a strategy and date to analyze targets.")
    else:
        # with st.container(border=True):
        st.subheader(f"Target Results: {sel_strat} ({sel_asof.strftime('%Y-%m-%d')})")
        # Load Raw Targets for Current
        df_curr = load_targets(strategy_id=sel_strat, asof=sel_asof)
        if approved_only:
            df_curr = df_curr[df_curr["approved"]]
        df_curr = df_curr[df_curr["score"] >= min_score].head(top_n)

        # KPI Cards Row
        st.container(border=False)
        k1, k2, k3, k4 = st.columns(4)
        pos_count = len(df_curr)
        app_ratio = df_curr["approved"].mean() if not df_curr.empty else 0

        df_comp = load_targets_comparison(sel_strat, sel_asof)
        turnover = "--"
        if not df_comp.empty:
            raw_turnover = df_comp["weight_delta"].abs().sum() / 2
            turnover = f"{raw_turnover:.1%}"

        k1.metric("Positions", pos_count)
        k2.metric("Approved Ratio", f"{app_ratio:.1%}")
        k3.metric("Implied Turnover", turnover)
        k4.metric("Exposure", "100.0%")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["Snapshot", "Delta vs Prev", "History"])

    with tab1:

        st.subheader("Target Snapshot")
        top_syms = df_curr[df_curr["approved"]].head(5)["symbol"].tolist()
        if top_syms:
            st.write("**Top Approved:** " + " ".join([f"`{s}`" for s in top_syms]))
        st.dataframe(format_df_for_display(df_curr), width="stretch", hide_index=True)

    with tab2, st.container(border=True):
        st.subheader("Portfolio Changes (Delta)")
        if df_comp.empty:
            st.info("No previous targets found for comparison.")
        else:
            new_symbols = df_comp[df_comp["weight_prev"] == 0]["symbol"].tolist()
            rem_symbols = df_comp[df_comp["weight_curr"] == 0]["symbol"].tolist()

            c21, c22 = st.columns(2)
            with c21:
                st.success(
                    f"🆕 **New ({len(new_symbols)}):** "
                    + (
                        ", ".join(new_symbols[:10])
                        + ("..." if len(new_symbols) > 10 else "")
                        if new_symbols
                        else "None"
                    )
                )
            with c22:
                st.error(
                    f"❌ **Removed ({len(rem_symbols)}):** "
                    + (
                        ", ".join(rem_symbols[:10])
                        + ("..." if len(rem_symbols) > 10 else "")
                        if rem_symbols
                        else "None"
                    )
                )

            st.write("**Weight Changes**")
            display_comp = df_comp[df_comp["weight_delta"] != 0].copy()
            for col in ["weight_curr", "weight_prev", "weight_delta"]:
                display_comp[col] = display_comp[col].apply(lambda x: f"{x:.2%}")
            st.dataframe(display_comp, width="stretch", hide_index=True)

    with tab3, st.container(border=True):
        st.subheader("Strategy Metrics History")
        df_hist = load_targets_history(sel_strat)
        if df_hist.empty:
            st.info("No history available.")
        else:
            fig_pos = px.line(
                df_hist, x="asof", y="positions", title="Position Count Trend"
            )
            fig_pos.update_layout(template="plotly_white", height=300)
            st.plotly_chart(fig_pos, width="stretch")

            fig_app = px.area(
                df_hist,
                x="asof",
                y="approved_ratio",
                title="Approved Ratio Trend",
            )
            fig_app.update_layout(
                template="plotly_white", height=300, yaxis_range=[0, 1]
            )
            st.plotly_chart(fig_app, width="stretch")
