import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG ---
st.set_page_config(page_title="📈 RS Screener", layout="wide")
st.title("📈 Top 10% Relative Strength Stocks vs SPY")
st.caption("Powered by Polygon.io")

API_KEY = st.secrets["POLYGON_API_KEY"]

# --- CACHE SETTINGS ---
TICKER_CACHE_FILE = "tickers_cache.json"
TICKER_CACHE_HOURS = 24

# --- SIDEBAR FILTERS ---
lookback_days = st.sidebar.slider("Lookback Period (days)", 100, 400, 250)
min_price = st.sidebar.number_input("Minimum Price", value=5.0)
min_avg_volume = st.sidebar.number_input("Minimum Avg Volume", value=500_000)
min_market_cap = st.sidebar.number_input("Minimum Market Cap ($)", value=2_000_000_000)
min_eps_growth = st.sidebar.number_input("EPS Growth This Year (%)", value=20.0)
min_eps_5y_growth = st.sidebar.number_input("EPS Growth 5Y Avg (%)", value=15.0)
min_sales_5y_growth = st.sidebar.number_input("Sales Growth 5Y Avg (%)", value=10.0)
min_roi = st.sidebar.number_input("Return on Investment (%)", value=15.0)
min_inst_ownership = st.sidebar.number_input("Institutional Ownership (%)", value=50.0)
max_tickers = st.sidebar.number_input("Max Tickers to Scan", min_value=100, max_value=10000, value=1000, step=100)

# --- DATE RANGE ---
end_date = datetime.utcnow().date()
start_date = end_date - timedelta(days=lookback_days)
benchmark = "SPY"

# --- TICKER CACHING ---
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
            if item.get("primary_exchange") in ["XNYS", "XNAS"] and item.get("type") == "CS":
                tickers.append(item["ticker"])
        url = data.get("next_url")
        if url:
            url += f"&apiKey={API_KEY}"

    with open(TICKER_CACHE_FILE, "w") as f:
        json.dump(tickers, f)

    return tickers

# --- FUNDAMENTALS ---
def get_fundamentals(ticker):
    url = f"https://api.polygon.io/vX/reference/financials?ticker={ticker}&apiKey={API_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json()
    try:
        fundamentals = data['results'][0]
        return {
            "market_cap": fundamentals.get("market_cap", 0),
            "eps_growth": fundamentals.get("eps_growth", 0),
            "eps_growth_5y": fundamentals.get("eps_growth_5y", 0),
            "sales_growth_5y": fundamentals.get("sales_growth_5y", 0),
            "roi": fundamentals.get("roi", 0),
            "institutional_ownership": fundamentals.get("institutional_ownership", 0)
        }
    except:
        return None

# --- PRICE & EMA DATA ---
def get_pct_change_and_emas(ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        results = data.get("results", [])
        if len(results) < 200:
            return None
        closes = [bar["c"] for bar in results]
        vols = [bar["v"] for bar in results]
        pct = (closes[-1] - closes[0]) / closes[0]
        ema_50 = pd.Series(closes).ewm(span=50).mean().iloc[-1]
        ema_200 = pd.Series(closes).ewm(span=200).mean().iloc[-1]
        avg_vol = sum(vols) / len(vols)
        return {
            "ticker": ticker,
            "pct": pct,
            "avg_vol": avg_vol,
            "price": closes[-1],
            "ema_50": ema_50,
            "ema_200": ema_200
        }
    except:
        return None

# --- MAIN EXECUTION ---
with st.spinner("Fetching data and calculating relative strength..."):
    tickers = get_ticker_list()
    tickers = tickers[:max_tickers]

    st.subheader("🔍 Debug: Benchmark (SPY) Fetch")
    try:
        spy_url = f"https://api.polygon.io/v2/aggs/ticker/{benchmark}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
        spy_response = requests.get(spy_url, timeout=10)
        st.code(f"Request URL:\n{spy_url}")
        st.write("Polygon Raw Response:", spy_response.status_code, spy_response.reason)
        spy_data = spy_response.json()
        st.json(spy_data)

        if "results" not in spy_data or len(spy_data["results"]) < 200:
            st.error("❌ SPY data has fewer than 200 candles or missing 'results'.")
            benchmark_data = None
        else:
            closes = [bar["c"] for bar in spy_data["results"]]
            vols = [bar["v"] for bar in spy_data["results"]]
            pct = (closes[-1] - closes[0]) / closes[0]
            ema_50 = pd.Series(closes).ewm(span=50).mean().iloc[-1]
            ema_200 = pd.Series(closes).ewm(span=200).mean().iloc[-1]
            avg_vol = sum(vols) / len(vols)

            benchmark_data = {
                "ticker": benchmark,
                "pct": pct,
                "avg_vol": avg_vol,
                "price": closes[-1],
                "ema_50": ema_50,
                "ema_200": ema_200
            }

            st.success("✅ Benchmark data fetched successfully.")
            st.json(benchmark_data)

    except Exception as e:
        st.error(f"❌ Error while fetching SPY data: {e}")
        benchmark_data = None
