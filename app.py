"""
app.py - Real-Time Stock Monitoring Dashboard (Streamlit)

Reads from data/prices.db (populated by fetch_prices.py / scan_alerts.py)
and renders:
  - Price trend + moving averages, per selected ticker
  - Volatility trend
  - A persisted alerts panel (from Step 3's anomaly detection)

Run locally:
    streamlit run app.py

When deployed to Streamlit Community Cloud, this file is the entry point.
The database it reads gets refreshed daily by the GitHub Action defined in
.github/workflows/daily_update.yml -- see that file and the README for the
full "runs itself" setup.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "prices.db"
ANALYSIS_VIEWS_PATH = Path(__file__).parent / "sql" / "analysis_views.sql"

st.set_page_config(page_title="Stock Monitoring Dashboard", layout="wide")


@st.cache_resource
def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    # Make sure the analysis views (moving averages, volatility, z-scores)
    # exist / are up to date every time the app starts.
    conn.executescript(ANALYSIS_VIEWS_PATH.read_text())
    return conn


@st.cache_data(ttl=3600)
def load_tickers(_conn):
    return [r[0] for r in _conn.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker")]


@st.cache_data(ttl=3600)
def load_price_data(_conn, ticker):
    query = """
        SELECT p.date, p.close, p.volume, m.ma_7, m.ma_30, v.volatility_30d
        FROM prices p
        LEFT JOIN moving_averages m ON p.ticker = m.ticker AND p.date = m.date
        LEFT JOIN rolling_volatility v ON p.ticker = v.ticker AND p.date = v.date
        WHERE p.ticker = ?
        ORDER BY p.date
    """
    df = pd.read_sql_query(query, _conn, params=(ticker,), parse_dates=["date"])
    return df


@st.cache_data(ttl=3600)
def load_alerts(_conn):
    return pd.read_sql_query(
        "SELECT ticker, date, pct_change, return_zscore, threshold_used, triggered_at "
        "FROM alerts ORDER BY date DESC",
        _conn,
        parse_dates=["date"],
    )


def main():
    st.title("Real-Time Stock Monitoring Dashboard")
    st.caption(
        "Daily OHLCV ingestion -> SQL analysis (moving averages, rolling volatility, "
        "z-scores) -> anomaly alerts. Data refreshes daily via a scheduled GitHub Action."
    )

    if not DB_PATH.exists():
        st.error(
            f"No database found at {DB_PATH}. Run `python scripts/fetch_prices.py "
            "--days-back 180` first to create it."
        )
        return

    conn = get_connection()
    tickers = load_tickers(conn)

    if not tickers:
        st.warning("Database exists but has no price data yet.")
        return

    with st.sidebar:
        st.header("Filters")
        selected_ticker = st.selectbox("Ticker", tickers)
        show_ma = st.checkbox("Show moving averages (7/30-day)", value=True)

    df = load_price_data(conn, selected_ticker)

    if df.empty:
        st.warning(f"No data for {selected_ticker}.")
        return

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    pct_change_today = (
        (latest["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latest Close", f"${latest['close']:.2f}", f"{pct_change_today:+.2f}%")
    col2.metric("7-day MA", f"${latest['ma_7']:.2f}" if pd.notna(latest["ma_7"]) else "N/A")
    col3.metric("30-day MA", f"${latest['ma_30']:.2f}" if pd.notna(latest["ma_30"]) else "N/A")
    col4.metric(
        "30-day Volatility",
        f"{latest['volatility_30d']:.2f}%" if pd.notna(latest["volatility_30d"]) else "N/A",
    )

    # --- Price + moving averages chart ---
    st.subheader(f"{selected_ticker} - Price Trend")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"], name="Close",
        line=dict(width=2.5, color="#00D4AA"),
    ))
    if show_ma:
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma_7"], name="MA 7",
            line=dict(dash="dot", width=1.5, color="#4FA8FF"),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma_30"], name="MA 30",
            line=dict(dash="dash", width=1.5, color="#FF6B6B"),
        ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        height=400,
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="#262730")
    fig.update_yaxes(gridcolor="#262730")
    st.plotly_chart(fig, width='stretch')

    # --- Volatility chart ---
    st.subheader(f"{selected_ticker} - 30-Day Rolling Volatility")
    vol_fig = go.Figure()
    vol_fig.add_trace(go.Scatter(
        x=df["date"], y=df["volatility_30d"],
        fill="tozeroy", line=dict(color="#FFB020"),
        fillcolor="rgba(255, 176, 32, 0.15)",
    ))
    vol_fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        height=250,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    vol_fig.update_xaxes(gridcolor="#262730")
    vol_fig.update_yaxes(gridcolor="#262730")
    st.plotly_chart(vol_fig, width='stretch')

    # --- Alerts panel ---
    st.subheader("Anomaly Alerts (all tickers)")
    alerts_df = load_alerts(conn)
    if alerts_df.empty:
        st.info("No alerts logged yet. Run `python scripts/scan_alerts.py` to scan for anomalies.")
    else:
        display_df = alerts_df.rename(columns={
            "ticker": "Ticker", "date": "Date", "pct_change": "Move",
            "return_zscore": "Z-Score", "threshold_used": "Threshold", "triggered_at": "Logged At",
        })

        def color_move(val):
            color = "#00D4AA" if val >= 0 else "#FF6B6B"
            return f"color: {color}; font-weight: 600"

        styled = (
            display_df.style
            .map(color_move, subset=["Move"])
            .format({"Move": "{:+.2f}%", "Z-Score": "{:+.2f}"})
        )
        st.dataframe(styled, width='stretch', hide_index=True)


if __name__ == "__main__":
    main()
