import streamlit as st
import os


st.set_page_config(
    page_title="Quant Lab V2 - Home",
    page_icon="🚀",
    layout="wide",
)

# --- Sidebar Title ---
# st.sidebar.title("🚀 Quant Lab V2")

# --- Page Title ---
st.title("🛡️ Welcome to Quant Lab V2")
st.markdown("<br>", unsafe_allow_html=True)

with st.container(border=True, height=800):
    st.subheader("System Entrance")
    st.write(
        "Welcome to the **ML Quant Lab**. Use the sidebar to navigate through the specialized analysis modules."
    )
    st.info("💡 **Dashboard**: View system health and recent results at a glance.")
    st.info("📊 **Market Explorer**: Deep-dive into market data and features.")
    st.info("🎯 **Targets Analyzer**: Evaluate and track portfolio recommendations.")
    st.info("📈 **Backtest Analyzer**: Perform granular performance analysis.")

st.divider()
st.caption("Universal Data Access Layer is active. Connected to DuckDB & SQLite.")
