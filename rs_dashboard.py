# streamlit_app.py

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta

# --- SETTINGS ---
API_KEY = "YOUR_POLYGON_API_KEY"
LOOKBACK_DAYS = 252  # approx 12 months
TOP_PERCENTILE = 90

st.title("📈 Relative Strength (RS) Rank – Top 10% Performers")

@st.cache_data(ttl=3600)
def get_ticker_list():
    exchanges = ["XNAS", "XNYS"]
    tickers = []
    for exchange in exchanges:
        url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&exchange={exchange}&active=true&limit=1000&apiKey={API_KEY}"
        response = requests.get(url).json()
        tickers += [item["ticker"] for item in response["results"] if item["type"] == "CS"]
    return list(set(tickers))

@st.cache_data(ttl=86400)
def fetch_price_data(ticker):
    end = datetime.now()
    start = end - timedelta(days=LOOKBACK_DAYS * 1.5)  # buffer for weekends/holidays
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start.date()}/{end.date()}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json().get("results", [])
    if len(data) < LOOKBACK_DAYS:
        return None
    return data

def calculate_rs(tickers):
    records = []
    for ticker in tickers:
        data = fetch_price_data(ticker)
        if data:
            start_price = data[0]["c"]
            end_price = data[-1]["c"]
            pct_change = (end_price - start_price) / start_price
            records.append((ticker, pct_change))
    df = pd.DataFrame(records, columns=["Ticker", "Percent_Change"])
    df["RS_Rank"] = df["Percent_Change"].rank(pct=True) * 100
    top_df = df[df["RS_Rank"] >= TOP_PERCENTILE].sort_values("RS_Rank", ascending=False)
    return top_df

# --- RUN ---
with st.spinner("Fetching tickers..."):
    tickers = get_ticker_list()

with st.spinner("Calculating RS Rankings... This may take a few minutes."):
    rs_df = calculate_rs(tickers)

st.success(f"Top {100 - TOP_PERCENTILE}% performers out of {len(tickers)} stocks.")
st.dataframe(rs_df.reset_index(drop=True), use_container_width=True)
