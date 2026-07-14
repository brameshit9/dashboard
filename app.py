bank nifty

# =========================================================
# Nifty Bank Premarket (NSE Pre-Open) Tracker — for Google Colab
# =========================================================
# Run each cell in order. NSE pre-open session is live
# 9:00–9:08 AM IST (then matching continues to ~9:15 AM).
# Outside that window this will return empty/stale data.
#
# NOTE: NSE blocks many datacenter IPs (including Colab's).
# If you get a 401/403, try running locally instead, or
# rerun a couple of times — NSE's bot-check is inconsistent.
#
# CHANGE FROM F&O VERSION: uses NSE's "BANKNIFTY" pre-open bucket
# (NOT "NIFTYBANK" — that key doesn't exist and silently returns
# zero rows) so you get exactly the Nifty Bank index constituents,
# no F&O-wide fetch + filter needed.
# =========================================================

# Cell 1: Install/import
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import pytz

# Cell 1b: Nifty Bank index constituents (14, per SEBI's 2025 rule change
# that raised the minimum from 12 to 14 and capped top-stock weight at 20%)
SECURITIES_BANKNIFTY = [
    'HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK',
    'BANKBARODA', 'UNIONBANK', 'PNB', 'CANBK', 'FEDERALBNK',
    'AUBANK', 'INDUSINDBK', 'YESBANK', 'IDFCFIRSTB',
]

# Cell 2: Create a browser-like session (needed to get past NSE's basic bot check)
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
    # Hitting the homepage first sets the cookies NSE checks on the API call
    session.get("https://www.nseindia.com", timeout=10)
    time.sleep(1)
    return session

# Cell 3: Fetch pre-open data
# key options (mirrors the "Category" dropdown on NSE's pre-open page):
#   "NIFTY" (Nifty50), "BANKNIFTY", "NIFTYNEXT50", "FO" (Securities in F&O),
#   "ALL", "SME", "OTHERS"
# NOTE: the Bank Nifty bucket's key is "BANKNIFTY", not "NIFTYBANK" —
# "NIFTYBANK" returns no rows.
def fetch_preopen_data(session, key="BANKNIFTY", retries=3):
    url = f"https://www.nseindia.com/api/market-data-pre-open?key={key}"
    last_json = None
    for attempt in range(retries):
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            try:
                last_json = resp.json()
            except ValueError:
                # NSE sometimes returns an HTML bot-check page with a 200 status
                print(f"⚠️  Attempt {attempt+1}: got 200 but non-JSON response "
                      f"(likely bot-check page). First 200 chars:\n{resp.text[:200]}")
                time.sleep(2)
                session = get_nse_session()
                continue
            # A healthy response has a non-empty "data" list. An empty/missing
            # "data" usually means we got a valid-looking JSON shell but no
            # real rows (e.g. blocked request, wrong key, or truly no data).
            if last_json.get("data"):
                return last_json
            print(f"⚠️  Attempt {attempt+1}: response had no 'data' rows for key={key!r}. "
                  f"Raw response keys: {list(last_json.keys())}")
        else:
            print(f"⚠️  Attempt {attempt+1}: HTTP {resp.status_code}")
        time.sleep(2)
        session = get_nse_session()  # refresh cookies and retry

    if last_json is not None:
        print("⚠️  All retries exhausted. Last raw JSON received:")
        print(last_json)
        return last_json  # return it anyway so caller can inspect/handle
    resp.raise_for_status()

# Cell 4: Parse into a clean DataFrame (only fields that are actually populated pre-market)
PREOPEN_COLUMNS = [
    "Symbol", "PrevClose", "IEP", "Change", "PctChange", "YearHigh", "YearLow",
    "FinalQuantity", "TotalTradedVolume", "TotalTurnover", "MarketCap",
    "TotalBuyQuantity", "TotalSellQuantity",
]

def parse_preopen(data):
    rows = []
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
    if rows:
        df = pd.DataFrame(rows)
    else:
        # No rows returned — build an empty frame with the right columns so
        # downstream code (df["Symbol"], filters, etc.) doesn't KeyError.
        df = pd.DataFrame(columns=PREOPEN_COLUMNS)
    return df

# Cell 4a: Add extra trade-relevant metrics on top of the raw NSE fields
# These are the numbers traders actually glance at before deciding buy/sell:
#   - OrderImbalance: (Buy Qty - Sell Qty) / (Buy Qty + Sell Qty) at the indicative price.
#       Close to +1 = heavy buy-side pressure building, close to -1 = heavy sell-side pressure.
#   - BuySellRatio: simple buy/sell quantity ratio (>1 = more buyers queued, <1 = more sellers).
#   - DistFrom52WHighPct / DistFrom52WLowPct: how close IEP is to the stock's 52-week range.
#       Near 0% from high = testing a fresh high; near 0% from low = testing a fresh low.
#   - NearCircuitFlag: NSE doesn't expose circuit limits in this API, so this is approximated
#       as a flag when |PctChange| is unusually large (>=9%), since most NSE band-1 circuits
#       are 5/10/20% — a stock already near 9%+ in premarket deserves a manual circuit check.
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

    # Simple composite "watch" score — bigger absolute move + stronger order imbalance
    # in the SAME direction = more conviction behind the premarket move.
    df["WatchScore"] = df["PctChange"].abs() * (1 + df["OrderImbalance"].abs().fillna(0))

    return df

# Cell 4b: Print the FULL detail table — every stock, every populated column
def print_full_details(df, sort_by="PctChange", ascending=False):
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.expand_frame_repr", False)
    out = df.sort_values(sort_by, ascending=ascending)
    print(out.to_string(index=False))
    return out

# Cell 5: Summary — count up/down/flat
def is_preopen_session_live():
    """NSE pre-open session runs ~9:00-9:15 AM IST on trading days.
    Outside this window the API still responds, but with a STALE
    (previous session's) snapshot, not live data."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= 5:  # Sat/Sun
        return False, "Weekend — market closed, data is stale."
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if start <= now <= end:
        return True, "Live pre-open window."
    return False, "Outside 9:00-9:15 AM IST window — this is a STALE/previous-session snapshot, not live premarket."

def summarize(df):
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S IST")
    live, note = is_preopen_session_live()

    up = int((df["PctChange"] > 0).sum())
    down = int((df["PctChange"] < 0).sum())
    flat = int((df["PctChange"] == 0).sum())
    total = len(df)

    print(f"Snapshot time : {now_ist}")
    if not live:
        print(f"⚠️  WARNING: {note}")
    print(f"Total stocks  : {total}")
    if total > 0:
        print(f"Up            : {up}  ({up/total*100:.1f}%)")
        print(f"Down          : {down}  ({down/total*100:.1f}%)")
    else:
        print("Up            : 0")
        print("Down          : 0")
    print(f"Flat          : {flat}")
    print("-" * 45)
    return {"time": now_ist, "live": live, "up": up, "down": down, "flat": flat, "total": total}

# Cell 5b: "Must-check" watchlist — the stocks worth a manual look before placing a buy/sell
# Ranks by WatchScore (move size + order-imbalance conviction) and surfaces why each one
# made the list, plus a NearCircuitFlag callout. This is descriptive, not a recommendation —
# always confirm price/quantity live before placing an order.
def print_watchlist(df, top_n=14):
    cols = ["Symbol", "IEP", "PctChange", "OrderImbalance", "BuySellRatio",
            "DistFrom52WHighPct", "DistFrom52WLowPct", "NearCircuitFlag", "WatchScore"]
    cols = [c for c in cols if c in df.columns]
    watch = df.dropna(subset=["WatchScore"]).sort_values("WatchScore", ascending=False).head(top_n)

    print(f"\n=== MUST-CHECK WATCHLIST (Top {len(watch)} by move + order-imbalance conviction) ===")
    print(watch[cols].round(2).to_string(index=False))

    circuit_hits = df[df["NearCircuitFlag"] == True]
    if len(circuit_hits) > 0:
        print(f"\n⚠️  {len(circuit_hits)} stock(s) showing premarket move ≥9% — verify circuit limit before trading:")
        print(circuit_hits[["Symbol", "PctChange"]].round(2).to_string(index=False))

    return watch

# Cell 5c: Filter the fetched universe down to exactly SECURITIES_BANKNIFTY,
# and report any symbols from your list that NSE didn't return data for
# (e.g. newly listed/delisted, or a typo in the list). In practice the
# "BANKNIFTY" key should already return exactly these 14 — this filter is
# a safety net in case NSE ever changes what that bucket includes.
def filter_to_banknifty_universe(df, universe=SECURITIES_BANKNIFTY):
    if df.empty or "Symbol" not in df.columns:
        print("⚠️  No pre-open data to filter — NSE returned zero rows this call "
              "(common outside the 9:00-9:15 AM IST window, or if the request got "
              "blocked). Skipping filter and returning an empty frame.")
        return pd.DataFrame(columns=PREOPEN_COLUMNS)

    universe_set = set(universe)
    filtered = df[df["Symbol"].isin(universe_set)].copy()

    found = set(filtered["Symbol"])
    missing = sorted(universe_set - found)
    if missing:
        print(f"⚠️  {len(missing)} symbol(s) in SECURITIES_BANKNIFTY had no premarket data returned "
              f"(check spelling / listing status):")
        print(", ".join(missing))

    return filtered

# Cell 6: Run it
session = get_nse_session()
raw = fetch_preopen_data(session, key="BANKNIFTY")
df = parse_preopen(raw)
df = filter_to_banknifty_universe(df)
df = df.dropna(subset=["PctChange"]).sort_values("PctChange", ascending=False)

if df.empty:
    raise SystemExit(
        "No usable pre-open data was returned for SECURITIES_BANKNIFTY. "
        "Most likely cause: you're outside the 9:00-9:15 AM IST pre-open window "
        "(NSE serves stale/empty data then), or the request got bot-blocked. "
        "Check the ⚠️ messages printed above for details, then rerun."
    )

df = add_trade_signals(df)

stats = summarize(df)

print("\n=== FULL PREMARKET DATA — ALL STOCKS, ALL FIELDS ===")
full_df = print_full_details(df, sort_by="PctChange", ascending=False)

watchlist_df = print_watchlist(df, top_n=14)

gainers = df[df["PctChange"] > 0].sort_values("PctChange", ascending=False)
losers = df[df["PctChange"] < 0].sort_values("PctChange", ascending=True)

print(f"\nUp Stocks (premarket) — {len(gainers)}:")
print(gainers[["Symbol", "PrevClose", "IEP", "PctChange"]].to_string(index=False))

print(f"\nDown Stocks (premarket) — {len(losers)}:")
print(losers[["Symbol", "PrevClose", "IEP", "PctChange"]].to_string(index=False))

# Cell 7 (optional): Auto-refresh every 30s during the 9:00–9:08 AM window
def track_live(key="BANKNIFTY", interval_sec=30, duration_min=10):
    """Polls the pre-open API repeatedly and prints up/down counts each time."""
    history = []
    end_time = time.time() + duration_min * 60
    session = get_nse_session()
    while time.time() < end_time:
        try:
            raw = fetch_preopen_data(session, key=key)
            df_live = parse_preopen(raw)
            df_live = filter_to_banknifty_universe(df_live)
            df_live = df_live.dropna(subset=["PctChange"])
            df_live = add_trade_signals(df_live)
            stats = summarize(df_live)
            print_watchlist(df_live, top_n=14)
            history.append(stats)
        except Exception as e:
            print("Error, retrying:", e)
            session = get_nse_session()
        time.sleep(interval_sec)
    return pd.DataFrame(history)

# Example usage (uncomment to run live tracking for 10 minutes):
# history_df = track_live(key="BANKNIFTY", interval_sec=30, duration_min=10)
# history_df

# =========================================================
# Cell 8: GRAPHICAL VIEW — bar chart + up/down donut chart
# (bars now show % change AND ₹ price change)
# =========================================================
import matplotlib.pyplot as plt

def plot_premarket(df):
    plot_df = df.dropna(subset=["PctChange"]).sort_values("PctChange", ascending=True)
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in plot_df["PctChange"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, max(6, len(plot_df) * 0.5)),
                              gridspec_kw={"width_ratios": [3, 1]})

    # --- Horizontal bar chart: every stock's % change ---
    ax1 = axes[0]
    bars = ax1.barh(plot_df["Symbol"], plot_df["PctChange"], color=colors)
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_xlabel("% Change (Premarket vs Prev Close)")
    ax1.set_title("Nifty Bank Premarket Movement — All Stocks", fontsize=13, fontweight="bold")
    ax1.tick_params(axis="y", labelsize=9)
    ax1.grid(axis="x", linestyle="--", alpha=0.4)

    # Give a little headroom on both sides so labels don't get clipped
    max_abs = plot_df["PctChange"].abs().max()
    pad = max_abs * 0.15 if max_abs > 0 else 1
    ax1.set_xlim(plot_df["PctChange"].min() - pad, plot_df["PctChange"].max() + pad)

    # --- Add % change + ₹ price change label at the end of each bar ---
    has_change = "Change" in plot_df.columns
    for bar, (_, row) in zip(bars, plot_df.iterrows()):
        width = bar.get_width()
        y = bar.get_y() + bar.get_height() / 2

        pct_txt = f"{width:+.2f}%"
        if has_change and pd.notna(row.get("Change")):
            label = f"{pct_txt}  (₹{row['Change']:+.2f})"
        else:
            label = pct_txt

        # Positive bars: label to the right of the bar end.
        # Negative bars: label to the left of the bar end (since bar extends leftward).
        offset = pad * 0.06
        if width >= 0:
            ax1.text(width + offset, y, label, va="center", ha="left",
                      fontsize=8, fontweight="bold", color="#1a7a3c")
        else:
            ax1.text(width - offset, y, label, va="center", ha="right",
                      fontsize=8, fontweight="bold", color="#a82c1a")

    # --- Donut chart: Up / Down / Flat counts ---
    ax2 = axes[1]
    up = (df["PctChange"] > 0).sum()
    down = (df["PctChange"] < 0).sum()
    flat = (df["PctChange"] == 0).sum()
    sizes = [up, down, flat]
    labels = [f"Up ({up})", f"Down ({down})", f"Flat ({flat})"]
    colors_pie = ["#2ecc71", "#e74c3c", "#95a5a6"]
    # drop zero-size slices so the chart doesn't break
    nonzero = [(s, l, c) for s, l, c in zip(sizes, labels, colors_pie) if s > 0]
    sizes, labels, colors_pie = zip(*nonzero)
    ax2.pie(sizes, labels=labels, colors=colors_pie, autopct="%1.0f%%",
            startangle=90, wedgeprops={"width": 0.4})
    ax2.set_title("Market Breadth", fontsize=13, fontweight="bold")

    plt.tight_layout()
    plt.show()

plot_premarket(df)
