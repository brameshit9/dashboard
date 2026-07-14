# =========================================================
# Nifty Bank Premarket (NSE Pre-Open) Tracker — Streamlit App
# =========================================================
# Run locally with:  streamlit run streamlit_app.py
# Deploy for free on Streamlit Community Cloud (see README.md)
#
# NSE pre-open session is live 9:00-9:15 AM IST on trading days.
# Outside that window this will show stale/empty data.
#
# NOTE: NSE blocks many datacenter/cloud IPs (including some
# Streamlit Cloud egress ranges). If you get repeated 401/403s
# after deploying, see the "If NSE blocks the server" section
# in README.md for workarounds.
# =========================================================

import time
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
import requests
import streamlit as st
import plotly.graph_objects as go

# ---------------------------------------------------------
# Config
# ---------------------------------------------------------
st.set_page_config(page_title="Nifty Bank Premarket Tracker", layout="wide")

SECURITIES_BANKNIFTY = [
    'HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK',
    'BANKBARODA', 'UNIONBANK', 'PNB', 'CANBK', 'FEDERALBNK',
    'AUBANK', 'INDUSINDBK', 'YESBANK', 'IDFCFIRSTB',
]

PREOPEN_COLUMNS = [
    "Symbol", "PrevClose", "IEP", "Change", "PctChange", "YearHigh", "YearLow",
    "FinalQuantity", "TotalTradedVolume", "TotalTurnover", "MarketCap",
    "TotalBuyQuantity", "TotalSellQuantity",
]

# ---------------------------------------------------------
# Data fetching (cached briefly so repeated reruns don't hammer NSE)
# ---------------------------------------------------------
def get_nse_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/market-data/pre-open-market-cotation",
    })
    session.get("https://www.nseindia.com", timeout=10)
    time.sleep(1)
    return session


def fetch_preopen_data(key="BANKNIFTY", retries=3):
    session = get_nse_session()
    url = f"https://www.nseindia.com/api/market-data-pre-open?key={key}"
    last_json = None
    errors = []
    for attempt in range(retries):
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            try:
                last_json = resp.json()
            except ValueError:
                errors.append(f"Attempt {attempt+1}: got 200 but non-JSON (bot-check page).")
                time.sleep(2)
                session = get_nse_session()
                continue
            if last_json.get("data"):
                return last_json, errors
            errors.append(f"Attempt {attempt+1}: response had no 'data' rows.")
        else:
            errors.append(f"Attempt {attempt+1}: HTTP {resp.status_code}")
        time.sleep(2)
        session = get_nse_session()
    return last_json, errors


@st.cache_data(ttl=25, show_spinner=False)
def fetch_preopen_data_cached(key="BANKNIFTY"):
    return fetch_preopen_data(key)


def parse_preopen(data):
    rows = []
    if not data:
        return pd.DataFrame(columns=PREOPEN_COLUMNS)
    for item in data.get("data", []):
        meta = item.get("metadata", {})
        pre = item.get("detail", {}).get("preOpenMarket", {})
        rows.append({
            "Symbol": meta.get("symbol"),
            "PrevClose": meta.get("previousClose"),
            "IEP": pre.get("IEP", meta.get("iep")),
            "Change": meta.get("change"),
            "PctChange": meta.get("pChange"),
            "YearHigh": meta.get("yearHigh"),
            "YearLow": meta.get("yearLow"),
            "FinalQuantity": pre.get("finalQuantity"),
            "TotalTradedVolume": pre.get("totalTradedVolume"),
            "TotalTurnover": meta.get("totalTurnover"),
            "MarketCap": meta.get("marketCap"),
            "TotalBuyQuantity": pre.get("totalBuyQuantity"),
            "TotalSellQuantity": pre.get("totalSellQuantity"),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=PREOPEN_COLUMNS)


def filter_to_banknifty_universe(df, universe=SECURITIES_BANKNIFTY):
    if df.empty or "Symbol" not in df.columns:
        return pd.DataFrame(columns=PREOPEN_COLUMNS), sorted(set(universe))
    universe_set = set(universe)
    filtered = df[df["Symbol"].isin(universe_set)].copy()
    found = set(filtered["Symbol"])
    missing = sorted(universe_set - found)
    return filtered, missing


def add_trade_signals(df):
    df = df.copy()
    buy = df["TotalBuyQuantity"].fillna(0)
    sell = df["TotalSellQuantity"].fillna(0)
    total_qty = buy + sell

    df["OrderImbalance"] = np.where(total_qty > 0, (buy - sell) / total_qty, np.nan)
    df["BuySellRatio"] = np.where(sell > 0, buy / sell, np.nan)
    df["DistFrom52WHighPct"] = np.where(
        df["YearHigh"] > 0, (df["IEP"] - df["YearHigh"]) / df["YearHigh"] * 100, np.nan
    )
    df["DistFrom52WLowPct"] = np.where(
        df["YearLow"] > 0, (df["IEP"] - df["YearLow"]) / df["YearLow"] * 100, np.nan
    )
    df["NearCircuitFlag"] = df["PctChange"].abs() >= 9
    df["WatchScore"] = df["PctChange"].abs() * (1 + df["OrderImbalance"].abs().fillna(0))
    return df


def is_preopen_session_live():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False, "Weekend — market closed, data is stale.", now
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if start <= now <= end:
        return True, "Live pre-open window.", now
    return False, "Outside 9:00-9:15 AM IST window — this is a STALE/previous-session snapshot.", now


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.title("🏦 Nifty Bank Premarket Tracker")
st.caption("NSE pre-open data for the 14 Nifty Bank constituents. Live only 9:00-9:15 AM IST on trading days.")

col_a, col_b, col_c = st.columns([1, 1, 2])
with col_a:
    auto_refresh = st.checkbox("Auto-refresh every 30s", value=False)
with col_b:
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
with col_c:
    live, note, now = is_preopen_session_live()
    ist_str = now.strftime("%Y-%m-%d %H:%M:%S IST")
    if live:
        st.success(f"🟢 {ist_str} — {note}")
    else:
        st.warning(f"🟡 {ist_str} — {note}")

raw, errors = fetch_preopen_data_cached(key="BANKNIFTY")

with st.expander("Fetch diagnostics", expanded=False):
    if errors:
        for e in errors:
            st.write("⚠️", e)
    else:
        st.write("No errors on last fetch.")

df = parse_preopen(raw)
df, missing = filter_to_banknifty_universe(df)

if missing:
    st.info(f"No premarket data returned for: {', '.join(missing)}")

df = df.dropna(subset=["PctChange"])

if df.empty:
    st.error(
        "No usable pre-open data available right now. This usually means you're outside "
        "the 9:00-9:15 AM IST window, or NSE is blocking this server's IP. "
        "See the diagnostics above, and the README for workarounds if this persists after deploying."
    )
    st.stop()

df = add_trade_signals(df)
df = df.sort_values("PctChange", ascending=False)

# --- Summary metrics ---
up = int((df["PctChange"] > 0).sum())
down = int((df["PctChange"] < 0).sum())
flat = int((df["PctChange"] == 0).sum())
total = len(df)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total stocks", total)
m2.metric("Up", up, f"{up/total*100:.0f}%" if total else None)
m3.metric("Down", down, f"-{down/total*100:.0f}%" if total else None)
m4.metric("Flat", flat)

# --- Bar chart ---
plot_df = df.sort_values("PctChange", ascending=True)
colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in plot_df["PctChange"]]
text_labels = [
    f"{row.PctChange:+.2f}%  (₹{row.Change:+.2f})" if pd.notna(row.Change) else f"{row.PctChange:+.2f}%"
    for row in plot_df.itertuples()
]

fig = go.Figure(go.Bar(
    x=plot_df["PctChange"],
    y=plot_df["Symbol"],
    orientation="h",
    marker_color=colors,
    text=text_labels,
    textposition="outside",
))
fig.update_layout(
    title="Premarket % Change — All Bank Nifty Stocks",
    xaxis_title="% Change (Premarket vs Prev Close)",
    height=max(400, 40 * len(plot_df)),
    margin=dict(l=10, r=80, t=50, b=10),
)
fig.add_vline(x=0, line_color="black", line_width=1)
st.plotly_chart(fig, use_container_width=True)

# --- Watchlist ---
st.subheader("🔍 Must-check watchlist (move size + order-imbalance conviction)")
cols = ["Symbol", "IEP", "PctChange", "OrderImbalance", "BuySellRatio",
        "DistFrom52WHighPct", "DistFrom52WLowPct", "NearCircuitFlag", "WatchScore"]
cols = [c for c in cols if c in df.columns]
watch = df.dropna(subset=["WatchScore"]).sort_values("WatchScore", ascending=False)
st.dataframe(watch[cols].round(2), use_container_width=True, hide_index=True)

circuit_hits = df[df["NearCircuitFlag"] == True]
if len(circuit_hits) > 0:
    st.warning(f"⚠️ {len(circuit_hits)} stock(s) showing premarket move ≥9% — verify circuit limit before trading.")
    st.dataframe(circuit_hits[["Symbol", "PctChange"]].round(2), hide_index=True)

# --- Full detail table ---
with st.expander("📋 Full premarket data — all fields", expanded=False):
    st.dataframe(df.round(2), use_container_width=True, hide_index=True)

# --- Gainers / Losers ---
g_col, l_col = st.columns(2)
gainers = df[df["PctChange"] > 0].sort_values("PctChange", ascending=False)
losers = df[df["PctChange"] < 0].sort_values("PctChange", ascending=True)
with g_col:
    st.subheader(f"📈 Up ({len(gainers)})")
    st.dataframe(gainers[["Symbol", "PrevClose", "IEP", "PctChange"]].round(2), hide_index=True)
with l_col:
    st.subheader(f"📉 Down ({len(losers)})")
    st.dataframe(losers[["Symbol", "PrevClose", "IEP", "PctChange"]].round(2), hide_index=True)

st.caption("Data source: NSE India pre-open API. Informational only — not investment advice. "
           "Always confirm live price/quantity before placing any order.")

# --- Auto-refresh loop ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
