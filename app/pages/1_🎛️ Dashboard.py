import streamlit as st

from app.ui.data_access import (
    load_backtest_summary,
    load_latest_targets_snapshot,
    load_pipeline_status,
    load_system_health,
)
from app.ui.navigation import open_run_center, run_center_cta

st.set_page_config(
    page_title="Dashboard | Quant Lab V2",
    page_icon="🎛️",
    layout="wide",
)
st.title("🎛️ Dashboard")

# --- Spec 4.1: Dashboard Layout ---
# Controls Panel (Left) vs Results Panel (Right)
col_controls, col_results = st.columns([0.28, 0.72], gap="small")


with col_controls, st.container(border=True, height=800):
    with st.container(border=True, height="content"):
        st.subheader("🚀 Quick Actions")

        run_center_cta(
            title="실행(및 dry-run)은 Run Center에서만 가능합니다.",
            body="Dashboard는 상태 요약/관측용입니다.",
        )

    with st.container(border=True, height="stretch"):
        try:
            health = load_system_health()
            duck_icon = "🟢" if health["duckdb_ok"] else "🔴"
            sqlite_icon = "🟢" if health["sqlite_ok"] else "🔴"

            st.markdown("**System Status**")
            st.markdown(f"- DuckDB: {duck_icon}")
            st.markdown(f"- SQLite: {sqlite_icon}")
            st.markdown("- Orchestrator: **Ready**")
        except Exception:
            st.error("System Check Failed")


with col_results, st.container(border=True, height=800):
    # 1. Pipeline Status Cards
    st.subheader("Pipeline Status (Latest Run)")

    try:
        status_map = load_pipeline_status()
        stages = ["ingest", "features", "labels", "recommend", "backtest"]

        cols = st.columns(len(stages), gap="small")

        for i, stage in enumerate(stages):
            info = status_map.get(stage, {})
            status = info.get("status", "pending")

            icon_map = {"success": "✅", "fail": "❌", "running": "🔄", "pending": "⏳"}
            icon = icon_map.get(status, "⏳")

            with cols[i], st.container(border=True):
                st.markdown(f"**{stage.capitalize()}**")
                st.markdown(f"### {icon}")
                if status == "fail":
                    st.caption("Failed")
                elif status == "success":
                    st.caption("Done")

    except Exception:
        st.error("Failed to load status")

    # 2. Recent Backtests & Snapshot
    c_bt, c_snap = st.columns(2, gap="small")

    with c_bt, st.container(border=True, height="stretch"):
        st.subheader("Recent Backtests")
        try:
            bt_df = load_backtest_summary(limit=5)
            if not bt_df.empty:
                st.dataframe(
                    bt_df[["run_id", "strategy_id", "cagr", "sharpe"]],
                    hide_index=True,
                    width="stretch",
                )

                sel = st.selectbox(
                    "Open backtest run in Run Center",
                    options=bt_df["run_id"].astype(str).tolist(),
                    index=0,
                )
                if st.button("Open in Run Center", width="stretch"):
                    open_run_center(run_id=str(sel))
            else:
                st.info("No backtests found.")
        except Exception as e:
            st.error(f"Error: {e}")

    with c_snap, st.container(border=True, height="stretch"):
        st.subheader("Latest Targets Snapshot")
        try:
            tgt_df = load_latest_targets_snapshot(limit=5)
            if not tgt_df.empty:
                st.dataframe(
                    tgt_df[["strategy", "positions", "approved_ratio"]],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("No targets found.")
        except Exception:
            st.info("No targets loaded.")
