import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from app.ui.data_access import (
    load_backtest_summary,
    load_backtest_trades,
    load_ohlcv,
)
from app.ui.charts import (
    plot_equity_drawdown,
    plot_price_with_markers,
    plot_backtest_comparison,
)
from app.ui.navigation import run_center_cta, open_run_center
from app.ui.kpi import format_percent

st.set_page_config(
    page_title="Backtest Lab | Quant Lab V2", page_icon="📈", layout="wide"
)

st.title("📈 Backtest Lab", help="Backtest result exploration and comparison. Execution (including re-running backtests) is only available in Run Center.")
st.caption(
    "⚠️ 실행(백테스트 재실행 포함)은 Run Center에서만 가능합니다. Backtest Lab은 결과 탐색/비교 전용입니다."
)
# run_center_cta(
#     title="실행(백테스트 재실행 포함)은 Run Center에서만 가능합니다.",
#     body="Backtest Lab은 결과 탐색/비교 전용입니다.",
# )

# --- Layout: 2-Panel ---
ctrl_col, res_col = st.columns([0.2, 0.8], gap="small")

# Load Summary globally
df_summ = load_backtest_summary()

with ctrl_col:
    with st.container(border=True, height="stretch"):
        st.subheader("Controls")

        if df_summ.empty:
            st.info("No backtest runs found.")
            # Fallback controls if no runs?
        else:
            # 1. Run Selection
            run_ids = df_summ["run_id"].tolist()
            default_run_id = st.session_state.get("sel_run_id", run_ids[0])
            if default_run_id not in run_ids:
                default_run_id = run_ids[0]
            sel_run_id = st.selectbox(
                "Select Run", run_ids, index=run_ids.index(default_run_id)
            )

            if st.button("Open selected run in Run Center", width="stretch"):
                open_run_center(run_id=str(sel_run_id))

            # Show Strategy used in this run
            run_row = df_summ[df_summ["run_id"] == sel_run_id].iloc[0]
            st.caption(f"Strategy: **{run_row['strategy_id']}**")

            # 2. Symbol Selection (from result)
            df_trades = load_backtest_trades(sel_run_id)
            symbols = (
                ["All"]
                + sorted(
                    [
                        s
                        for s in df_trades["symbol"].unique()
                        if s not in ["CASH", "COST"]
                    ]
                )
                if not df_trades.empty
                else ["All"]
            )
            sel_sym = st.selectbox("Symbol Analysis", symbols)

            st.divider()

            # 3. Chart Options
            chart_mode = st.radio(
                "Chart Mode", ["Candlestick", "Line"], horizontal=True
            )
            c1, c2 = st.columns(2)
            log_scale = c1.toggle("Log", value=False)
            vol_overlay = c2.toggle("Volume", value=True)

            st.divider()

            # 4. New Backtest Execution (Shortcut)
            st.subheader("New Backtest")
            # Minimal inputs for re-run
            # We assume user wants to re-run the *same* strategy?
            # Or just a generic Runner button pointing to Run Center.
            if st.button("Run New Backtest", type="primary", width="stretch"):
                st.info("Run Center에서 backtest 단계를 실행해 새 결과를 생성하세요.")

with res_col:
    with st.container(border=True, height=800):
        if df_summ.empty:
            st.warning("No backtest results available.")
        else:
            tab_dash, tab_detail, tab_compare = st.tabs(
                ["Dashboard", "Trades Analysis", "Compare Runs"]
            )

            # --- Tab 1: Dashboard ---
            with tab_dash:
                # with st.container(border=True):
                # st.subheader(f"Results: {sel_run_id}")
                with st.container(border=True):
                # KPI Cards
                    k1, k2, k3, k4, k5, k6 = st.columns(6)
                    k1.metric("CAGR", f"{run_row['cagr']:.2%}")
                    k2.metric("Sharpe", f"{run_row['sharpe']:.2f}")
                    k3.metric("MDD", f"{run_row['max_dd']:.2%}")
                    k4.metric(
                        "Vol",
                        f"{run_row['std_daily_return']*(run_row['annual_factor']**0.5):.2%}",
                    )
                    k5.metric("Turnover", f"{run_row['turnover']:.2f}")
                    k6.metric("Win Rate", f"{run_row['win_rate']:.1%}")


                # Equity Curve
               
                mode = "CumReturn %"  # Default
                fig_eq, fig_dd, mdd_period = plot_equity_drawdown(df_trades, mode=mode)
                if fig_eq:
                    with st.container(border=True):
                        st.plotly_chart(fig_eq, width="stretch", height=250)
                    with st.container(border=True):
                        if fig_dd:
                            st.plotly_chart(fig_dd, width="stretch", height=250)
                        st.caption(mdd_period)
            # --- Tab 2: Trades Analysis ---
            with tab_detail:
                # with st.container(border=True):
                    c_head, c_dl = st.columns([0.8, 0.2])
                    c_head.subheader("Trade Markers & Ledger")

                    if sel_sym == "All":
                        st.info(
                            "Select a specific symbol in controls to view Line + Trade Markers."
                        )
                        st.dataframe(df_trades, width="stretch", hide_index=True)
                    else:
                        # Load Price Data for context
                        from_dt = pd.to_datetime(run_row["from_ts"]).date()
                        to_dt = pd.to_datetime(run_row["to_ts"]).date()
                        df_ohlcv = load_ohlcv(sel_sym, from_dt, to_dt)

                        fig_price = plot_price_with_markers(
                            df_ohlcv, df_trades, sel_sym, mode=chart_mode
                        )
                        if fig_price:
                            st.plotly_chart(fig_price, width="stretch")
                        else:
                            st.warning("No price data found.")

                        st.markdown("#### Trade Ledger")
                        st.dataframe(
                            df_trades[df_trades["symbol"] == sel_sym],
                            width="stretch",
                            hide_index=True,
                        )

            # --- Tab 3: Compare ---
            with tab_compare:
                st.subheader("Benchmark Comparison")
                other_run_id = st.selectbox(
                    "Compare with",
                    [r for r in run_ids if r != sel_run_id],
                    index=0 if len(run_ids) > 1 else None,
                )

                if other_run_id:
                    row2 = df_summ[df_summ["run_id"] == other_run_id].iloc[0]
                    df_trades2 = load_backtest_trades(other_run_id)

                    c1, c2 = st.columns(2)
                    c1.info(f"Base: {sel_run_id} ({run_row['strategy_id']})")
                    c2.success(f"Vs: {other_run_id} ({row2['strategy_id']})")

                    fig_comp = plot_backtest_comparison(
                        df_trades, df_trades2, sel_run_id, other_run_id
                    )
                    st.plotly_chart(fig_comp, width="stretch")
