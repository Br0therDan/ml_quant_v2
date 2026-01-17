import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_equity_drawdown(df_trades, mode="Equity 1.0"):
    if df_trades.empty:
        return None, None, None

    df_trades["ts"] = pd.to_datetime(df_trades["entry_ts"])
    daily_ret = df_trades.groupby("ts")["pnl_pct"].sum()

    # Calculate Equity/Return
    cum_ret = (1 + daily_ret).cumprod()
    if mode == "CumReturn %":
        display_series = (cum_ret - 1) * 100
        y_label = "Return (%)"
    else:
        display_series = cum_ret
        y_label = "Equity (1.0 base)"

    drawdown = cum_ret / cum_ret.cummax() - 1

    fig_ret = px.line(
        x=display_series.index,
        y=display_series.values,
        labels={"x": "Date", "y": y_label},
        title="Performance Curve",
    )
    fig_ret.update_layout(template="plotly_white", height=400)

    fig_dd = px.area(
        x=drawdown.index,
        y=drawdown.values * 100,
        labels={"x": "Date", "y": "Drawdown (%)"},
        title="Drawdown (%)",
    )
    fig_dd.update_traces(fillcolor="rgba(239, 83, 80, 0.3)", line_color="#ef5350")
    fig_dd.update_layout(template="plotly_white", height=200)

    # Find MDD Period
    end_idx = drawdown.idxmin()
    peak_idx = cum_ret[:end_idx].idxmax()
    mdd_text = f"MDD Period: {peak_idx.date()} ~ {end_idx.date()}"

    return fig_ret, fig_dd, mdd_text


def plot_price_with_markers(df_ohlcv, df_trades, symbol, threshold=0.0, mode="Line"):
    if df_ohlcv.empty:
        return None

    df_ohlcv["ts"] = pd.to_datetime(df_ohlcv["ts"])

    fig = go.Figure()

    # 1. Base Price Chart
    if mode == "Candlestick":
        fig.add_trace(
            go.Candlestick(
                x=df_ohlcv["ts"],
                open=df_ohlcv["open"],
                high=df_ohlcv["high"],
                low=df_ohlcv["low"],
                close=df_ohlcv["close"],
                name="OHLC",
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=df_ohlcv["ts"],
                y=df_ohlcv["close"],
                mode="lines",
                name="Price",
                line={"color": "#2196f3", "width": 2},
            )
        )

    # 3. Add Trade Markers
    # Filter trades for this symbol
    if not df_trades.empty:
        sym_trades = df_trades[df_trades["symbol"] == symbol].sort_values("entry_ts")

        # Entry Markers (Buys)
        entries = sym_trades[sym_trades["qty"] > 0]
        if not entries.empty:
            fig.add_trace(
                go.Scatter(
                    x=entries["entry_ts"],
                    y=entries["entry_price"],
                    mode="markers",
                    marker={
                        "symbol": "triangle-up", "size": 10, "color": "#26a69a"
                    },  # Green Up
                    name="Buy",
                    text=entries.apply(
                        lambda x: (
                            f"<b>BUY</b><br>"
                            f"Date: {x['entry_ts']}<br>"
                            f"Price: {x['entry_price']:.2f}<br>"
                            f"Qty: {x['qty']:.4f}"
                        ),
                        axis=1,
                    ),
                    hoverinfo="text",
                )
            )

        # Exit Markers (Sells/PNL records)
        exits = sym_trades[sym_trades["pnl"] != 0]
        if not exits.empty:
            fig.add_trace(
                go.Scatter(
                    x=exits["exit_ts"],
                    y=exits["exit_price"],
                    mode="markers",
                    marker={
                        "symbol": "triangle-down", "size": 10, "color": "#ef5350"
                    },  # Red Down
                    name="Sell",
                    text=exits.apply(
                        lambda x: (
                            f"<b>SELL</b><br>"
                            f"Date: {x['exit_ts']}<br>"
                            f"Price: {x['exit_price']:.2f}<br>"
                            f"PNL: {x['pnl']:.2f} ({x['pnl_pct']:.2%})<br>"
                        ),
                        axis=1,
                    ),
                    hoverinfo="text",
                )
            )

    fig.update_layout(
        title=f"{symbol} Price & Trades",
        yaxis_title="Price",
        xaxis_title="Date",
        height=600,
        template="plotly_white",
        xaxis_rangeslider_visible=False,
    )
    return fig


def plot_market_explorer_chart(
    df,
    chart_type="Candlestick",
    log_scale=False,
    vol_overlay=True,
    sma_list=None,
    rsi_period=None,
    bb_params=None,
):
    """
    Advanced Market Explorer Chart with Overlays and Subplots.
    """
    if df.empty:
        return None

    # Prepare Data
    df = df.sort_values("ts")
    df["ts"] = pd.to_datetime(df["ts"])

    # Create figure with 2 rows if RSI is enabled
    row_heights = [0.8, 0.2] if rsi_period else [1.0]
    specs = [[{"secondary_y": True}]]
    if rsi_period:
        specs.append([{"secondary_y": False}])

    fig = make_subplots(
        rows=2 if rsi_period else 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=row_heights,
        specs=specs,
    )

    # 1. Main Price Trace
    if chart_type == "Candlestick":
        fig.add_trace(
            go.Candlestick(
                x=df["ts"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="Price",
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            ),
            row=1,
            col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=df["close"],
                mode="lines",
                name="Close",
                line={"color": "#2196f3", "width": 2},
            ),
            row=1,
            col=1,
        )

    # 2. Indicators - SMA
    if sma_list:
        colors = ["#ff9800", "#e91e63", "#9c27b0"]
        for i, period in enumerate(sma_list):
            sma = df["close"].rolling(window=period).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["ts"],
                    y=sma,
                    mode="lines",
                    name=f"SMA({period})",
                    line={"width": 1.5, "color": colors[i % len(colors)]},
                ),
                row=1,
                col=1,
            )

    # 3. Indicators - Bollinger Bands
    if bb_params:
        window, std_dev = bb_params
        mid = df["close"].rolling(window=window).mean()
        std = df["close"].rolling(window=window).std()
        upper = mid + (std * std_dev)
        lower = mid - (std * std_dev)

        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=upper,
                mode="lines",
                name="BB Upper",
                line={"width": 1, "color": "rgba(173, 216, 230, 0.4)"},
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=lower,
                mode="lines",
                name="BB Lower",
                line={"width": 1, "color": "rgba(173, 216, 230, 0.4)"},
                fill="tonexty",
                fillcolor="rgba(173, 216, 230, 0.2)",
            ),
            row=1,
            col=1,
        )

    # 4. Volume Overlay
    if vol_overlay:
        colors = [
            "#26a69a" if c >= o else "#ef5350" for o, c in zip(df["open"], df["close"], strict=False)
        ]
        fig.add_trace(
            go.Bar(
                x=df["ts"],
                y=df["volume"],
                name="Volume",
                marker_color=colors,
                opacity=0.5,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    # 5. RSI Subplot
    if rsi_period:
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        fig.add_trace(
            go.Scatter(
                x=df["ts"],
                y=rsi,
                mode="lines",
                name="RSI",
                line={"color": "#7e57c2", "width": 1.5},
            ),
            row=2,
            col=1,
        )
        # RSI range lines
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # Layout Updates
    fig.update_layout(
        template="plotly_white",
        height=700 if rsi_period else 600,
        margin={"l": 50, "r": 50, "t": 20, "b": 50},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis_rangeslider_visible=False,
    )

    if log_scale:
        fig.update_yaxes(type="log", row=1, col=1)

    # Secondary Y Axis for Volume (opacity and axis visibility)
    if vol_overlay:
        fig.update_yaxes(
            showgrid=False,
            range=[0, df["volume"].max() * 4],
            secondary_y=True,
            showticklabels=False,
        )

    return fig


def plot_feature_analysis(df_feat):
    """
    Plots multiple features as time series and a selected distribution.
    """
    if df_feat.empty:
        return None, None

    # 1. Feature Time Series
    cols = [c for c in df_feat.columns if c != "ts" and c != "symbol"]
    fig_line = px.line(df_feat, x="ts", y=cols, title="Feature Time Series")
    fig_line.update_layout(template="plotly_white", legend={"orientation": "h"})

    # 2. Histogram for first feature by default (or let user choose needed logic in page)
    # We just return the line chart primarily here for now if logic is complex.
    # Actually let's return a dict of figs or just the line one.

    return fig_line


def plot_feature_distribution(df, feature_name):
    fig = px.histogram(
        df, x=feature_name, title=f"Distribution: {feature_name}", nbins=50
    )
    fig.update_layout(template="plotly_white")
    return fig


def plot_correlation_matrix(df_corr):
    fig = px.imshow(
        df_corr,
        text_auto=".2f",
        aspect="auto",
        title="Feature Correlation Matrix",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
    )
    fig.update_layout(template="plotly_white")
    return fig


def plot_label_analysis(df_lbl):
    """
    Plots label distribution and basic stats.
    """
    if df_lbl.empty:
        return None, None

    cols = [c for c in df_lbl.columns if c != "ts" and c != "symbol"]

    # 1. Bar chart of positive/negative counts
    stats = []
    for c in cols:
        pos = (df_lbl[c] > 0).sum()
        neg = (df_lbl[c] <= 0).sum()
        stats.append({"Label": c, "Type": "Positive", "Count": pos})
        stats.append({"Label": c, "Type": "Negative", "Count": neg})

    df_stats = pd.DataFrame(stats)
    fig_bar = px.bar(
        df_stats,
        x="Label",
        y="Count",
        color="Type",
        barmode="group",
        title="Label Positive/Negative Counts",
    )
    fig_bar.update_layout(template="plotly_white")

    # 2. Distribution of the returns (labels)
    fig_hist = px.histogram(
        df_lbl, x=cols[0] if cols else None, title="Label Distribution (Returns)"
    )
    fig_hist.update_layout(template="plotly_white")

    return fig_bar, fig_hist


def plot_backtest_comparison(run1_data, run2_data, run1_id, run2_id):
    """
    Plots two equity curves for comparison.
    """
    fig = go.Figure()

    for df, label in [(run1_data, run1_id), (run2_data, run2_id)]:
        if not df.empty:
            df["ts"] = pd.to_datetime(df["entry_ts"])
            daily_cum = (1 + df.groupby("ts")["pnl_pct"].sum()).cumprod()
            fig.add_trace(
                go.Scatter(
                    x=daily_cum.index, y=daily_cum.values, mode="lines", name=label
                )
            )

    fig.update_layout(
        title="Equity Comparison (Base 1.0)",
        xaxis_title="Date",
        yaxis_title="Equity",
        template="plotly_white",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig
