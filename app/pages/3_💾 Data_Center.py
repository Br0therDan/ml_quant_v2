import time
import uuid
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from app.ui.charts import plot_market_explorer_chart
from app.ui.data_access import (
    load_active_symbols,
    load_ohlcv,
    load_symbol_inventory,
)
from app.ui.execution import ExecutionManager
from app.ui.run_artifacts import list_runs_from_run_json
from quant.config import settings
from quant.data_curator.provider import AlphaVantageProvider

st.set_page_config(
    page_title="Data Center | Quant Lab V2",
    page_icon="💾",
    layout="wide",
)

st.title("💾 Data Center")

st.caption("Symbol 등록, 데이터 수집(Ingest) 및 상태 모니터링을 위한 공간입니다.")

# --- Layout: 2-Panel ---
col_controls, col_results = st.columns([0.3, 0.7], gap="small")

with col_controls:
    with st.container(border=True, height=800):
        st.subheader("Controls")

        # 1. Symbol Search & Registration
        with st.expander("🔍 Symbol Search & Registration", expanded=True):
            search_query = st.text_input("Search Symbol", placeholder="e.g. NVDA, AAPL")
            if st.button("Search", width="stretch") or search_query:
                if search_query:
                    try:
                        api_key = settings.alpha_vantage_api_key
                        if not api_key:
                            st.error(
                                "Alpha Vantage API key is not configured. Please set 'alpha_vantage_api_key' in settings."
                            )
                            st.session_state["search_results"] = None
                        else:
                            provider = AlphaVantageProvider(api_key=api_key)
                            results_df = provider.search_symbols(search_query)
                            if not results_df.empty:
                                st.session_state["search_results"] = results_df
                            else:
                                st.warning("No results found.")
                                st.session_state["search_results"] = None
                    except Exception as e:
                        st.error(f"Search failed: {e}")

            if st.session_state.get("search_results") is not None:
                res = st.session_state["search_results"]
                # Use a selection mechanism
                # Streamlit dataframe with selection is only in newer versions,
                # using a multiselect for simplicity or manual checkboxes is safer.
                # Let's use a simplified view + multiselect.

                options = [
                    f"{row['symbol']} | {row['name']} ({row['currency']})"
                    for _, row in res.iterrows()
                ]
                selected_options = st.multiselect("Select symbols to add", options)

                selected_symbols = [opt.split(" | ")[0] for opt in selected_options]

                col_reg, col_reg_ing = st.columns(2)
                with col_reg:
                    if st.button(
                        "Register Only", disabled=not selected_symbols, width="stretch"
                    ):
                        run_id = f"reg_{datetime.now().strftime('%H%M%S')}"
                        cmd = [
                            "uv",
                            "run",
                            "quant",
                            "symbol-register",
                        ] + selected_symbols
                        success = ExecutionManager.run_command_async(cmd, run_id)
                        if success:
                            st.success(
                                f"Started registration for {', '.join(selected_symbols)}"
                            )
                            time.sleep(1)
                            st.rerun()

                with col_reg_ing:
                    if st.button(
                        "Register & Ingest",
                        disabled=not selected_symbols,
                        width="stretch",
                        type="primary",
                    ):
                        run_id = f"reg_ing_{datetime.now().strftime('%H%M%S')}"
                        cmd = (
                            ["uv", "run", "quant", "symbol-register"]
                            + selected_symbols
                            + ["--ingest"]
                        )
                        success = ExecutionManager.run_command_async(cmd, run_id)
                        if success:
                            st.success(
                                f"Started registration & ingest for {', '.join(selected_symbols)}"
                            )
                            time.sleep(1)
                            st.rerun()

                # 2. Bulk Ingest for Registered Symbols
        with st.expander("⏱️ Bulk Ingest", expanded=False):
            active_symbols = load_active_symbols()
            if active_symbols:
                all_syms = [s.symbol for s in active_symbols]
                to_ingest = st.multiselect(
                    "Select registered symbols to ingest", all_syms
                )
                if st.button(
                    "Run Ingest",
                    disabled=not to_ingest,
                    width="stretch",
                    type="primary",
                ):
                    # We can use 'quant pipeline run --stages ingest --symbols ...'
                    run_id = f"ingest_{datetime.now().strftime('%H%M%S')}"
                    # Individual ingest or pipeline ingest?
                    # Pipeline ingest is better for multi-symbol
                    today_str = datetime.today().strftime("%Y-%m-%d")
                    start_str = (datetime.today() - timedelta(days=365)).strftime(
                        "%Y-%m-%d"
                    )
                    cmd = [
                        "uv",
                        "run",
                        "quant",
                        "pipeline",
                        "run",
                        "--from",
                        start_str,
                        "--to",
                        today_str,
                        "--stages",
                        "ingest",
                        "--symbols",
                        ",".join(to_ingest),
                        "--run-id",
                        str(uuid.uuid4()),
                    ]
                    success = ExecutionManager.run_command_async(cmd, run_id)
                    if success:
                        st.success("Ingest pipeline started.")
            else:
                st.info("No active symbols found.")

        # 3. DB Maintenance
        with st.expander("🛠️ Maintenance", expanded=False):
            st.warning(
                "DB 초기화는 기존 데이터를 유지하면서 스킴을 확인하거나 누락된 테이블을 생성합니다."
            )
            if st.button("Initialize Database (init-db)", width="stretch"):
                run_id = f"init_db_{datetime.now().strftime('%H%M%S')}"
                cmd = ["uv", "run", "quant", "init-db"]
                success = ExecutionManager.run_command_async(cmd, run_id)
                if success:
                    st.success("Database initialization started.")

        # Display feedback for recent actions
        if "data_center_msg" in st.session_state:
            st.info(st.session_state["data_center_msg"])
            if st.button("Clear Message"):
                del st.session_state["data_center_msg"]
                st.rerun()


with col_results:
    with st.container(border=True, height=800):

        inventory_df = load_symbol_inventory()

        tab_registry, tab_market = st.tabs(["📌 Symbol Registry", "📈 Market Explorer"])

        with tab_registry:

            c1, c2 = st.columns([0.8, 0.2])
            with c1:
                st.subheader("Symbol Inventory")
            with c2:
                if st.button("🔄 Refresh Data", width="stretch"):
                    st.rerun()

            if inventory_df.empty:
                st.info(
                    "등록된(active) 심볼이 없거나 메타 DB가 없습니다. 위 안내의 `symbol-register`로 등록하세요."
                )
            else:
                view = inventory_df.rename(
                    columns={
                        "symbol": "Symbol",
                        "name": "Name",
                        "currency": "CCY",
                        "count": "OHLCV Rows",
                        "min_date": "OHLCV From",
                        "max_date": "OHLCV To",
                    }
                )
                st.dataframe(view, hide_index=True, width="stretch")
                st.caption(
                    "`OHLCV Rows/From/To`는 DuckDB(ohlcv) 기준이며, 0이면 아직 ingest되지 않았을 수 있습니다."
                )

        with tab_market:
            # 1. Market Explorer Controls

            c1, c2, c3 = st.columns([3, 4, 3])

            with c1:
                active_symbols = load_active_symbols()
                symbol = st.selectbox(
                    "Symbol",
                    (
                        [s.symbol for s in active_symbols]
                        if active_symbols
                        else ["AAPL"]
                    ),
                    key="selected_symbol",
                )

            with c2:
                # Range as a horizontal button group (radio horizontal)
                range_option = st.radio(
                    "Range",
                    ["1M", "3M", "6M", "1Y", "3Y", "MAX"],
                    index=1,
                    horizontal=True,
                    key="range_option_explorer",
                )

            with c3:
                chart_display = st.radio(
                    "Style",
                    ["Candle", "Line"],
                    horizontal=True,
                    key="chart_style_explorer",
                )
                chart_type = "Candlestick" if chart_display == "Candle" else "Line"

            # 2. Date Calculation based on range_option
            today = datetime.today()
            if range_option == "1M":
                start_date = today - timedelta(days=30)
            elif range_option == "3M":
                start_date = today - timedelta(days=90)
            elif range_option == "6M":
                start_date = today - timedelta(days=180)
            elif range_option == "1Y":
                start_date = today - timedelta(days=365)
            elif range_option == "3Y":
                start_date = today - timedelta(days=1095)
            else:
                start_date = datetime(1990, 1, 1)

            from_str = start_date.strftime("%Y-%m-%d")
            to_str = today.strftime("%Y-%m-%d")
            df_ohlcv = load_ohlcv(symbol, from_str, to_str)

            if df_ohlcv.empty:
                st.warning(
                    f"No data found for {symbol} in DuckDB. Run Center에서 ingest를 실행해 주세요."
                )
                st.info("Chart will be displayed once data is ingested.")
            else:
                with st.container(border=True):
                    c1, c2 = st.columns([7, 3])
                    with c1:
                        st.markdown(
                            f"**Price Chart**: **`{symbol} ({from_str} ~ {to_str})`**"
                        )
                    with c2:
                        oc1, oc2 = st.columns(
                            2,
                        )
                        log_scale = oc1.checkbox("Log", key="log_scale_explorer")
                        vol_overlay = oc2.checkbox(
                            "Vol", value=True, key="vol_overlay_explorer"
                        )

                    fig = plot_market_explorer_chart(
                        df_ohlcv,
                        chart_type=chart_type,
                        log_scale=log_scale,
                        vol_overlay=vol_overlay,
                        sma_list=[20, 60],
                    )
                    if fig is not None:
                        st.plotly_chart(fig, width="stretch", height=360)
                    else:
                        st.warning(
                            "Failed to generate chart for the selected symbol/date range."
                        )

                with st.container(border=True):
                    tab_summary, tab_quality, tab_raw = st.tabs(
                        ["Summary", "Quality Gate", "Raw Data"]
                    )
                    with tab_summary:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Rows", len(df_ohlcv))
                        c2.metric(
                            "Start Date", df_ohlcv["ts"].min().strftime("%Y-%m-%d")
                        )
                        c3.metric("End Date", df_ohlcv["ts"].max().strftime("%Y-%m-%d"))

                    with tab_quality:
                        n_na = df_ohlcv.isna().sum().sum()
                        n_dups = df_ohlcv.duplicated().sum()
                        st.write(f"- Total Missing Values: {n_na}")
                        st.write(f"- Duplicate Rows: {n_dups}")

                    with tab_raw:
                        st.dataframe(
                            df_ohlcv.sort_values("ts", ascending=False),
                            width="stretch",
                        )
