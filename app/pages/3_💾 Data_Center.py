import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.ui.data_access import (
    load_active_symbols,
    load_symbol_inventory,
    load_ohlcv,
)
from app.ui.charts import plot_market_explorer_chart
from app.ui.navigation import run_center_cta
from app.ui.run_artifacts import list_runs_from_run_json

st.set_page_config(
    page_title="Data Center | Quant Lab V2",
    page_icon="💾",
    layout="wide",
)

st.title("💾 Data Center")

st.caption(
    "이 페이지는 read-only 모니터링입니다. 심볼 등록/인제스트 실행은 Run Center(단일 실행 진입점)에서만 수행합니다."
)

# --- Layout: 2-Panel ---
col_controls, col_results = st.columns([0.28, 0.72], gap="small")

with col_controls:
    with st.container(border=True, height="stretch"):
        st.subheader("Controls")

        run_center_cta(
            title="실행은 Run Center에서만 가능합니다.",
            body="Data Center는 심볼 등록/인제스트 상태를 관측하는 read-only 페이지입니다.",
        )

        with st.expander("How to register a symbol? (GUI)", expanded=False):
            st.markdown(
                "GUI에서는 `symbol-register`를 직접 실행하지 않습니다. 대신 아래 CLI를 사용하세요."
            )
            st.code(
                "\n".join(
                    [
                        "# Register only",
                        "uv run quant symbol-register AAPL",
                        "",
                        "# Register + immediate ingest (optional)",
                        "uv run quant symbol-register AAPL --ingest",
                    ]
                ),
                language="bash",
            )
            st.caption(
                "등록 후, 인제스트/피처/라벨/추천/백테스트 실행은 Run Center에서 수행합니다."
            )

        # Symbol Selector (Market Explorer)
        active_symbols = load_active_symbols()
        selected_symbol = st.selectbox(
            "Symbol",
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
        st.caption("실행(등록/수집/피처 계산)은 Run Center에서 수행합니다.")


with col_results:
    with st.container(border=True, height=800):
        st.subheader("Symbol Inventory")

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
                    st.warning("Failed to generate chart for the selected symbol/date range.")

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
