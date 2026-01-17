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
            search_query = st.text_input(
                "Search Symbol", placeholder="e.g. NVDA, AAPL"
            )
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

        st.markdown("---")

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

        st.markdown("---")

        # 3. Market Explorer (Symbol Selector)
        active_symbols = load_active_symbols()
        selected_symbol = st.selectbox(
            "Symbol (Market Explorer)",
            [s.symbol for s in active_symbols] if active_symbols else ["AAPL"],
            key="selected_symbol",
        )
        symbol = selected_symbol

        # Date Range
        today = datetime.today()
        range_option = st.selectbox("Range", ["1M", "3M", "6M", "1Y", "MAX"], index=1)

        if range_option == "1M":
            start_date = today - timedelta(days=30)
        elif range_option == "3M":
            start_date = today - timedelta(days=90)
        elif range_option == "6M":
            start_date = today - timedelta(days=180)
        elif range_option == "1Y":
            start_date = today - timedelta(days=365)
        else:
            start_date = datetime(2020, 1, 1)

        # Chart Settings
        st.markdown("---")
        chart_type = st.radio("Chart Type", ["Candlestick", "Line"], horizontal=True)
        log_scale = st.checkbox("Log Scale")
        vol_overlay = st.checkbox("Volume Overlay", value=True)

        st.markdown("---")
        # st.caption("실행(등록/수집/피처 계산)은 Run Center에서 수행합니다.")

        # Display feedback for recent actions
        if "data_center_msg" in st.session_state:
            st.info(st.session_state["data_center_msg"])
            if st.button("Clear Message"):
                del st.session_state["data_center_msg"]
                st.rerun()


with col_results:
    with st.container(border=True, height=800):
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            st.subheader("Symbol Inventory")
        with c2:
            if st.button("🔄 Refresh Data", width="stretch"):
                st.rerun()

        inventory_df = load_symbol_inventory()

        tab_registry, tab_ingest, tab_market = st.tabs(
            ["📌 Symbol Registry", "⏱️ Ingestion Monitor", "📈 Market Explorer"]
        )

        with tab_registry:
            st.subheader("Symbol Registration Status")

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

        with tab_ingest:
            st.subheader("Ingestion Monitoring (read-only)")
            st.caption(
                "인제스트 상태는 (1) DuckDB 커버리지, (2) 최근 pipeline run.json(artifacts) 요약으로 관측합니다."
            )

            if inventory_df.empty:
                st.info("표시할 심볼 인벤토리가 없습니다.")
            else:
                st.markdown("**1) Coverage from DuckDB (ohlcv)**")
                cov = inventory_df[["symbol", "count", "min_date", "max_date"]].copy()
                cov = cov.rename(
                    columns={
                        "symbol": "Symbol",
                        "count": "Rows",
                        "min_date": "From",
                        "max_date": "To",
                    }
                )
                st.dataframe(cov, hide_index=True, width="stretch")

            st.markdown("---")
            st.markdown("**2) Recent pipeline runs (artifacts/runs/*/run.json)**")
            runs = list_runs_from_run_json()
            ingest_rows: list[dict] = []
            for r in runs[:200]:
                stage_results = r.get("stage_results") or []
                if not isinstance(stage_results, list):
                    continue
                for sr in stage_results:
                    if not isinstance(sr, dict):
                        continue
                    if (sr.get("stage_name") or "").strip().lower() != "ingest":
                        continue
                    ingest_rows.append(
                        {
                            "run_id": r.get("run_id"),
                            "run_slug": r.get("run_slug"),
                            "status": sr.get("status"),
                            "started_at": r.get("started_at"),
                            "duration_sec": sr.get("duration_sec"),
                        }
                    )

            if ingest_rows:
                st.dataframe(
                    pd.DataFrame(ingest_rows)[:50], hide_index=True, width="stretch"
                )
            else:
                st.caption("No ingest stage results found in recent run.json files.")

        with tab_market:
            st.subheader(f"Price History: {symbol}")

            from_str = start_date.strftime("%Y-%m-%d")
            to_str = today.strftime("%Y-%m-%d")
            df_ohlcv = load_ohlcv(symbol, from_str, to_str)

            if df_ohlcv.empty:
                st.warning(
                    f"No data found for {symbol} in DuckDB. Run Center에서 ingest를 실행해 주세요."
                )
                st.info("Chart will be displayed once data is ingested.")
            else:
                fig = plot_market_explorer_chart(
                    df_ohlcv,
                    chart_type=chart_type,
                    log_scale=log_scale,
                    vol_overlay=vol_overlay,
                    sma_list=[20, 60],
                )
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.warning(
                        "Failed to generate chart for the selected symbol/date range."
                    )

                tab_summary, tab_quality, tab_raw = st.tabs(
                    ["Summary", "Quality Gate", "Raw Data"]
                )

                with tab_summary:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Rows", len(df_ohlcv))
                    c2.metric("Start Date", df_ohlcv["ts"].min().strftime("%Y-%m-%d"))
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
