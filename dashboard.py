import time
import streamlit as st
import sqlite3
import pandas as pd

DB_FILE = "oi_live.db"

st.set_page_config(page_title="NIFTY OI Live", layout="wide")
st.title("📊 NIFTY Live OI Dashboard")

# -------- DB connection --------
@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

conn = get_conn()

# -------- Controls --------
refresh = st.sidebar.slider("Auto refresh (seconds)", 10, 300, 60)

expiry = st.sidebar.text_input("Expiry (leave blank = auto)", "")

st.sidebar.markdown("---")
st.sidebar.caption("Data source: NSE Option Chain")

# -------- Load data --------
query = """
SELECT *
FROM oi_data
ORDER BY time DESC
LIMIT 500
"""
df = pd.read_sql(query, conn)

if df.empty:
    st.warning("No data yet. Let collector run.")
    st.stop()

if expiry:
    df = df[df["expiry"] == expiry]

df["time"] = pd.to_datetime(df["time"])

# -------- Metrics --------
latest = df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("ATM Strike", latest["strike"])
col2.metric("CE OI", latest["ce_oi"])
col3.metric("PE OI", latest["pe_oi"])

# -------- Table --------
st.subheader("Near-ATM OI Data")
st.dataframe(
    df.sort_values("time"),
    width='stretch',
    height=400
)

# -------- Charts --------
st.subheader("NET OI vs Time")

chart_df = (
    df.groupby("time", as_index=False)["net_oi"]
    .mean()
    .sort_values("time")
)

st.line_chart(chart_df.set_index("time"))

# -------- Auto refresh --------
st.caption(f"Auto-refresh every {refresh} seconds")
time.sleep(refresh)
st.rerun()
