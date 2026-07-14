import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

BG = '#F5F7FA'
CARD = '#FFFFFF'
BORDER = '#E7EBF0'
PRIMARY = '#4F46E5'
UP = '#16A34A'
DOWN = '#DC2626'
UP_SOFT = '#DCFCE7'
DOWN_SOFT = '#FEE2E2'
TEXT = '#1E293B'
MUTED = '#64748B'

NIFTY50 = [
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK',
    'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BEL', 'BHARTIARTL',
    'CIPLA', 'COALINDIA', 'DRREDDY', 'EICHERMOT', 'ETERNAL',
    'GRASIM', 'HCLTECH', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO',
    'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 'ITC', 'INDUSINDBK',
    'INFY', 'JSWSTEEL', 'JIOFIN', 'KOTAKBANK', 'LT',
    'M&M', 'MARUTI', 'MAXHEALTH', 'NESTLEIND', 'NTPC',
    'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SHRIRAMFIN',
    'SBIN', 'SUNPHARMA', 'TCS', 'TATACONSUM', 'TATAMOTORS',
    'TATASTEEL', 'TECHM', 'TITAN', 'TRENT', 'ULTRACEMCO',
    'WIPRO', 'INDIGO'
]


@st.cache_resource
def get_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/market-data/pre-open-market-cotd",
    })
    s.get("https://www.nseindia.com", timeout=5)
    return s


def fetch_preopen(session):
    url = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"
    try:
        r = session.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        session.cookies.clear()
        session.get("https://www.nseindia.com", timeout=5)
        r = session.get(url, timeout=5)
        r.raise_for_status()
        return r.json()


def to_dataframe(raw, symbols):
    rows = [
        {
            "symbol": item["metadata"]["symbol"],
            "price": item["metadata"]["lastPrice"],
            "change": item["metadata"]["pChange"],
        }
        for item in raw["data"]
        if item["metadata"]["symbol"] in symbols
    ]
    df = pd.DataFrame(rows)
    return df.sort_values("change", ascending=True).reset_index(drop=True)


st.set_page_config(page_title="Nifty50 Pre-Market Dashboard", layout="wide", page_icon="📊")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
}}

.stApp {{
    background-color: {BG};
}}

#MainMenu, footer, header {{visibility: hidden;}}

.block-container {{
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}}

.dash-title {{
    font-size: 28px;
    font-weight: 800;
    color: {TEXT};
    margin-bottom: 2px;
}}
.dash-sub {{
    font-size: 14px;
    color: {MUTED};
    font-weight: 500;
}}
.live-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: {UP};
    margin-right: 6px;
}}

.kpi-card {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 18px 20px;
    height: 100%;
    box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04), 0 1px 2px rgba(16, 24, 40, 0.06);
}}
.kpi-label {{
    font-size: 12px;
    color: {MUTED};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}}
.kpi-value {{
    font-size: 24px;
    font-weight: 700;
    color: {TEXT};
}}
.kpi-value.up {{ color: {UP}; }}
.kpi-value.down {{ color: {DOWN}; }}
.kpi-badge {{
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    margin-top: 8px;
}}
.kpi-badge.up {{ background-color: {UP_SOFT}; color: {UP}; }}
.kpi-badge.down {{ background-color: {DOWN_SOFT}; color: {DOWN}; }}

.chart-panel {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 24px;
    margin-top: 20px;
    box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04), 0 1px 2px rgba(16, 24, 40, 0.06);
}}
.panel-heading {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
    margin-bottom: 16px;
}}

div.stButton > button {{
    background-color: {PRIMARY};
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    padding: 8px 22px;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}}
div.stButton > button:hover {{
    background-color: #4338CA;
    color: #FFFFFF;
}}

.footer-note {{
    font-size: 12px;
    color: {MUTED};
    margin-top: 18px;
}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_data():
    session = get_session()
    raw = fetch_preopen(session)
    return to_dataframe(raw, NIFTY50)


header_col1, header_col2 = st.columns([5, 1])
with header_col1:
    st.markdown('<div class="dash-title">Nifty50 Pre-Market Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="dash-sub">NSE India &nbsp;·&nbsp; Pre-Open Session Overview</div>', unsafe_allow_html=True)
with header_col2:
    st.write("")
    if st.button("↻ Refresh", use_container_width=True):
        st.cache_data.clear()

try:
    df = load_data()
except Exception as e:
    st.markdown(f"""
    <div class="chart-panel">
        <div class="panel-heading" style="color:{DOWN};">Unable to fetch data</div>
        <div style="color:{TEXT};">{e}</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

top_loser = df.iloc[0]
top_gainer = df.iloc[-1]
timestamp = datetime.now().strftime("%d %b %Y, %H:%M:%S")
up_count = int((df["change"] >= 0).sum())
down_count = int((df["change"] < 0).sum())
ratio = up_count / down_count if down_count > 0 else float('inf')

st.markdown(
    f'<div class="dash-sub"><span class="live-dot"></span>Last updated {timestamp} IST</div>',
    unsafe_allow_html=True
)
st.write("")

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Advancers</div>
        <div class="kpi-value up">{up_count}</div>
        <div class="kpi-badge up">of 50 stocks</div></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Decliners</div>
        <div class="kpi-value down">{down_count}</div>
        <div class="kpi-badge down">of 50 stocks</div></div>""", unsafe_allow_html=True)
with k3:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">A/D Ratio</div>
        <div class="kpi-value">{ratio:.2f}</div>
        <div class="kpi-badge up" style="background-color:#EEF2FF; color:{PRIMARY};">advance / decline</div></div>""",
        unsafe_allow_html=True)
with k4:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Top Gainer</div>
        <div class="kpi-value up">{top_gainer['symbol']}</div>
        <div class="kpi-badge up">+{top_gainer['change']:.2f}%</div></div>""", unsafe_allow_html=True)
with k5:
    st.markdown(f"""<div class="kpi-card">
        <div class="kpi-label">Top Loser</div>
        <div class="kpi-value down">{top_loser['symbol']}</div>
        <div class="kpi-badge down">{top_loser['change']:.2f}%</div></div>""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])

with col1:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-heading">Premarket Movement — % Change</div>', unsafe_allow_html=True)
    fig1, ax1 = plt.subplots(figsize=(10, 11))
    fig1.patch.set_facecolor(CARD)
    colors = [UP if c >= 0 else DOWN for c in df["change"]]
    ax1.set_facecolor(CARD)
    ax1.barh(df["symbol"], df["change"], color=colors, height=0.6)
    ax1.axvline(0, color=BORDER, linewidth=1)
    ax1.tick_params(colors=MUTED, labelsize=9)
    for label in ax1.get_yticklabels():
        label.set_color(TEXT)
    for spine in ax1.spines.values():
        spine.set_visible(False)
    ax1.grid(axis='x', color=BORDER, linewidth=0.8)
    ax1.set_axisbelow(True)
    for i, change in enumerate(df["change"]):
        ax1.text(change, i, f' {change:+.2f}%', va='center',
                  color=TEXT, fontsize=8,
                  ha='left' if change >= 0 else 'right')
    st.pyplot(fig1, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    st.markdown('<div class="panel-heading">Market Breadth</div>', unsafe_allow_html=True)
    fig2, ax2 = plt.subplots(figsize=(5, 5))
    fig2.patch.set_facecolor(CARD)
    ax2.set_facecolor(CARD)
    wedges, texts, autotexts = ax2.pie(
        [up_count, down_count],
        labels=[f"Up\n{up_count}", f"Down\n{down_count}"],
        colors=[UP, DOWN], wedgeprops={"width": 0.42, "edgecolor": CARD, "linewidth": 3},
        autopct="%1.0f%%", startangle=90,
        textprops={"color": TEXT, "fontsize": 10, "fontweight": "bold"}
    )
    for at in autotexts:
        at.set_color('#FFFFFF')
        at.set_fontweight('bold')
    st.pyplot(fig2, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="footer-note">Data source: NSE India &nbsp;·&nbsp; Auto-refreshes every 60 seconds &nbsp;·&nbsp; '
    'Click Refresh for an immediate update</div>',
    unsafe_allow_html=True
)
