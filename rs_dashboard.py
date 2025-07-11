import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# === SETTINGS ===
API_KEY = "cXcAYHG065BCC9xr6iTMMyhFlhZ2M7Uh"
LOOKBACK_DAYS = 252  # Approx. 12 months
TOP_PERCENTILE = 90

st.title("📈 Relative Strength (RS) Rank – Top 10% Performers")

@st.cache_data(ttl=3600)
def get_ticker_list():
    exchanges = ["XNAS", "XNYS"]
    tickers = []

    for exchange in exchanges:
        base_url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&exchange={exchange}&active=true&limit=1000&apiKey={API_KEY}"
        next_url = base_url

        while next_url:
            try:
                response = requests.get(next_url)
                data = response.json()

                if response.status_code != 200 or "results" not in data:
                    st.warning(f"Polygon API error ({exchange}): {data.get('error', 'Unknown error')}")
                    break

                for item in data["results"]:
                    if item.get("type") == "CS":  # Common Stock only
                        tickers.append(item["ticker"])

                next_url = data.get("next_url")
                if next_url:
                    next_url += f"&apiKey={API_KEY}"

            except Exception as e:
                st.error(f"Exception while fetching from {exchange}: {e}")
                break

    return list(set(tickers))

@st.cache_data(ttl=86400)
def fetch_price_data(ticker):
    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS * 1.5)
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start.date()}/{end.date()}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code != 200:
            return None
        data = res.json().get("results", [])
        if len(data) < LOOKBACK_DAYS:
            return None
        return data
    except:
        return None

@st.cache_data(ttl=86400)
def fetch_fundamentals(ticker):
    url = f"https://api.polygon.io/vX/reference/financials?ticker={ticker}&limit=1&apiKey={API_KEY}"
    try:
        res = requests.get(url)
        data = res.json().get("results", [])
        if not data:
            return None
        metrics = data[0].get("metrics", {})
        return {
            "market_cap": metrics.get("market_cap"),
            "avg_volume": metrics.get("vol_avg"),
            "price": metrics.get("close")
        }
    except:
        return None

def calculate_rs(tickers, max_threads=15):
    records = []
    fundamentals_data = []

    def process_ticker(ticker):
        data = fetch_price_data(ticker)
        fundamentals = fetch_fundamentals(ticker)
        if data and fundamentals:
            try:
                end_price = data[-1]["c"]
                price_21d = data[-21]["c"]
                price_63d = data[-63]["c"]
                price_126d = data[-126]["c"]
                price_252d = data[-252]["c"]

                w1 = (end_price - price_21d) / price_21d
                w2 = (end_price - price_63d) / price_63d
                w3 = (end_price - price_126d) / price_126d
                w4 = (end_price - price_252d) / price_252d

                weighted_score = (0.3 * w1 + 0.25 * w2 + 0.25 * w3 + 0.2 * w4)

                closes = [bar["c"] for bar in data]
                above_ema_50 = end_price > np.mean(closes[-50:])
                above_ema_200 = end_price > np.mean(closes[-200:])

                return {
                    "Ticker": ticker,
                    "Weighted_RS": weighted_score,
                    "Above_50EMA": above_ema_50,
                    "Above_200EMA": above_ema_200,
                    "market_cap": fundamentals.get("market_cap"),
                    "avg_volume": fundamentals.get("avg_volume"),
                    "price": fundamentals.get("price")
                }
            except:
                return None
        return None

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_ticker, ticker): ticker for ticker in tickers}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                records.append(result)
            if i % 50 == 0:
                st.info(f"Processed {i}/{len(tickers)} tickers")

    df = pd.DataFrame(records)
    df["RS_Rank"] = df["Weighted_RS"].rank(pct=True) * 100

    # Final filter applied after RS rank calculation
    filtered_df = df[
        (df["market_cap"] >= 300_000_000) &
        (df["avg_volume"] >= 500_000) &
        (df["price"] >= 5) &
        (df["Above_50EMA"]) &
        (df["Above_200EMA"])
    ]

    top_df = filtered_df[filtered_df["RS_Rank"] >= TOP_PERCENTILE].sort_values("RS_Rank", ascending=False)
    return top_df

# === RUN ===
with st.spinner("Fetching tickers..."):
    tickers = get_ticker_list()

with st.spinner("Calculating RS Rankings... This may take a few minutes."):
    rs_df = calculate_rs(tickers)

st.success(f"Top {100 - TOP_PERCENTILE}% RS stocks that passed your filters.")
st.dataframe(rs_df.reset_index(drop=True), use_container_width=True)

# Optional export
st.download_button("Download CSV", data=rs_df.to_csv(index=False), file_name="top_rs_stocks.csv", mime="text/csv")
