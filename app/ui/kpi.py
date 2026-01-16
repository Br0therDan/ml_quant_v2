import pandas as pd
import streamlit as st


def format_percent(val, decimals=2):
    if pd.isna(val):
        return "-"
    return f"{val:.{decimals}%}"


def format_float(val, decimals=2):
    if pd.isna(val):
        return "-"
    return f"{val:.{decimals}f}"


def format_df_for_display(df):
    """
    Apply standard formatting to a dataframe for display.
    Returns a copy.
    """
    df_disp = df.copy()
    return df_disp


def render_kpi_card(title, value, delta=None, color=None):
    """
    Helper to render a consistent KPI card.
    Uses st.metric.
    """
    st.metric(
        label=title,
        value=value,
        delta=delta,
        delta_color="normal" if not color else color,
    )
