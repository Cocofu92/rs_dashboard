import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import os
import json
from pathlib import Path

# --- CONFIG ---
st.set_page_config(page_title="📈 RS Screener", layout="wide")
st.title("📈 Top 10% Relative Strength Stocks vs SPY")
st.caption("Powered by Polygon.io")

# --- API ---
API_KEY = st.secrets["POLYGON_API_KEY"]

# --- CACHE SETTINGS ---
TICKER_CACHE_FILE = "tickers_cache.json"
TICKER_CACHE_HOURS = 24

# --- Sidebar Filters ---
lookback_days = st.sidebar.slider("Lookback Period (days)", 10, 60, 21)
min_price = st.sidebar.number_input("Minimum Price", value=5.0)
min_avg_volume = st.sidebar.number_input("Minimum Avg Volume", value=1_000_000)

# --- Dates ---
end_date = datetime.utcnow().date()
start_date = end_date - timedelta(days=lookback_days)

# --- Benchmark ---
benchmark = "SPY"

# --- Ticker Cache ---
def is_cache_valid(path, max_age_hours):
    if not Path(path).exists():
        return False
    mtime = datetime.fromtimestamp(Path(path).stat().st_mtime)
    return (datetime.utcnow() - mtime).total_seconds() < max_age_hours * 3600

def get_ticker_list():
    if is_cache_valid(TICKER_CACHE_FILE, TICKER_CACHE_HOURS):
        with open(TICKER_CACHE_FILE, "r") as f:
            return json.load(f)

    tickers = []
    url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&active=true&limit=1000&apiKey={API_KEY}"

    while url:
        res = requests.get(url)
        data = res.json()
        for item in data.get("results", []):
            if item.get("primary_exchange") != "OTC" and item.get("type") == "CS":
                tickers.append(item["ticker"])
        url = data.get("next_url")
        if url:
            url += f"&apiKey={API_KEY}"

    with open(TICKER_CACHE_FILE, "w") as f:
        json.dump(tickers, f)

    return tickers

# --- Fetch % Change ---
def get_pct_change(ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    res = requests.get(url)
    data = res.json()

    try:
        results = data["results"]
        closes = [bar["c"] for bar in results]
        vols = [bar["v"] for bar in results]
        if len(closes) < 2:
            return None
        pct = (closes[-1] - closes[0]) / closes[0]
        avg_vol = sum(vols) / len(vols)
        return {"pct": pct, "avg_vol": avg_vol, "price": closes[-1]}
    except:
        return None

# --- Main Logic ---
with st.spinner("Fetching data and calculating relative strength..."):
    tickers = get_ticker_list()
    tickers = tickers[:500]  # temp limit

    benchmark_data = get_pct_change(benchmark)
    if not benchmark_data or benchmark_data["pct"] == 0:
        st.error("Benchmark data unavailable.")
    else:
      rs_list = []
progress_bar = st.progress(0)
status_text = st.empty()

for i, ticker in enumerate(tickers):
    data = get_pct_change(ticker)
    if data and data["price"] >= min_price and data["avg_vol"] >= min_avg_volume:
        rs_score = data["pct"] / benchmark_data["pct"]
        rs_list.append({
            "Ticker": ticker,
            "Price": round(data["price"], 2),
            "Return %": round(data["pct"] * 100, 2),
            "Avg Volume": int(data["avg_vol"]),
            "RS Score": round(rs_score, 2)
        })

    progress = (i + 1) / len(tickers)
    progress_bar.progress(progress)
    status_text.text(f"Scanning ticker {i + 1} of {len(tickers)}")

status_text.text("Done scanning tickers!")


        df = pd.DataFrame(rs_list).sort_values("RS Score", ascending=False)
        top_n = int(len(df) * 0.1)
        top_df = df.head(max(1, top_n))

        if not top_df.empty:
            st.success(f"Top {len(top_df)} stocks by RS (vs {benchmark})")
            st.dataframe(top_df, use_container_width=True)
        else:
            st.warning("No stocks matched your filter criteria.")
