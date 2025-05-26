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
        results = data["results"]
        closes = [bar["c"] for bar in results]
        vols = [bar["v"] for bar in results]
        if len(closes) < 200:
            return None
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

    benchmark_data = get_pct_change_and_emas(benchmark)

    # 🐞 DEBUG BLOCK
    if not benchmark_data:
        st.error("❌ Benchmark data (SPY) fetch failed.")
    else:
        st.info(f"✅ SPY Benchmark Debug Info: Price={benchmark_data['price']:.2f}, "
                f"EMA50={benchmark_data['ema_50']:.2f}, EMA200={benchmark_data['ema_200']:.2f}, "
                f"Return={benchmark_data['pct']*100:.2f}%")

        rs_list = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(get_pct_change_and_emas, ticker): ticker for ticker in tickers}
            for i, future in enumerate(as_completed(futures)):
                result = future.result()
                if result is None:
                    continue

                fundamentals = get_fundamentals(result["ticker"])
                if fundamentals is None:
                    continue

                if (
                    result["price"] >= min_price and
                    result["avg_vol"] >= min_avg_volume and
                    fundamentals["market_cap"] >= min_market_cap and
                    fundamentals["eps_growth"] >= min_eps_growth and
                    fundamentals["eps_growth_5y"] >= min_eps_5y_growth and
                    fundamentals["sales_growth_5y"] >= min_sales_5y_growth and
                    fundamentals["roi"] >= min_roi and
                    fundamentals["institutional_ownership"] >= min_inst_ownership and
                    result["price"] > result["ema_50"] and
                    result["price"] > result["ema_200"]
                ):
                    rs_score = result["pct"] / benchmark_data["pct"]
                    rs_list.append({
                        "Ticker": result["ticker"],
                        "Price": round(result["price"], 2),
                        "Return %": round(result["pct"] * 100, 2),
                        "Avg Volume": int(result["avg_vol"]),
                        "RS Score": round(rs_score, 2),
                        "Market Cap ($B)": round(fundamentals["market_cap"] / 1e9, 2),
                        "EPS Growth Y": fundamentals["eps_growth"],
                        "EPS Growth 5Y": fundamentals["eps_growth_5y"],
                        "Sales Growth 5Y": fundamentals["sales_growth_5y"],
                        "RoI": fundamentals["roi"],
                        "Inst. Ownership %": fundamentals["institutional_ownership"]
                    })

                progress = (i + 1) / len(tickers)
                progress_bar.progress(progress)
                status_text.text(f"Scanning ({i + 1}/{len(tickers)}): {futures[future]}")

        status_text.text("✅ Done scanning tickers.")
        df = pd.DataFrame(rs_list).sort_values("RS Score", ascending=False)
        top_n = int(len(df) * 0.1)
        top_df = df.head(max(1, top_n))

        if not top_df.empty:
            st.success(f"Top {len(top_df)} stocks by RS (vs {benchmark})")
            st.dataframe(top_df, use_container_width=True)
            st.download_button("📥 Download CSV", top_df.to_csv(index=False), file_name="top_relative_strength.csv")
        else:
            st.warning("No stocks matched your filter criteria.")
