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

def calculate_rs(tickers, max_threads=15):
    records = []

    def process_ticker(ticker):
        data = fetch_price_data(ticker)
        if data:
            start_price = data[0]["c"]
            end_price = data[-1]["c"]
            pct_change = (end_price - start_price) / start_price
            return ticker, pct_change
        return None

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_ticker, ticker): ticker for ticker in tickers}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                records.append(result)
            if i % 50 == 0:
                st.info(f"Processed {i}/{len(tickers)} tickers")

    df = pd.DataFrame(records, columns=["Ticker", "Percent_Change"])
    df["RS_Rank"] = df["Percent_Change"].rank(pct=True) * 100
    top_df = df[df["RS_Rank"] >= TOP_PERCENTILE].sort_values("RS_Rank", ascending=False)
    return top_df

# === RUN ===
with st.spinner("Fetching tickers..."):
    tickers = get_ticker_list()

with st.spinner("Calculating RS Rankings... This may take a few minutes."):
    rs_df = calculate_rs(tickers)

st.success(f"Top {100 - TOP_PERCENTILE}% performers out of {len(tickers)} stocks.")
st.dataframe(rs_df.reset_index(drop=True), use_container_width=True)

# Optional export
st.download_button("Download CSV", data=rs_df.to_csv(index=False), file_name="top_rs_stocks.csv", mime="text/csv")
