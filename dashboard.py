import time
import streamlit as st
import sqlite3
import pandas as pd
import numpy as np

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

# UI: delta display mode and highlight intensity
delta_mode = st.sidebar.selectbox("Delta mode", ["Absolute", "% Percentage"], index=0)
highlight_intensity = st.sidebar.slider("Highlight intensity", 0, 100, 60)
highlight_atm = st.sidebar.checkbox("Highlight ATM row", value=True)

# map intensity slider to alpha values for backgrounds/borders
bg_alpha = round(0.02 + (highlight_intensity / 100.0) * 0.28, 3)
atm_bg_alpha = round(0.06 + (highlight_intensity / 100.0) * 0.24, 3)
atm_border_alpha = round(0.12 + (highlight_intensity / 100.0) * 0.28, 3)

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

df["time"] = pd.to_datetime(df["time"])

if expiry:
    df = df[df["expiry"] == expiry]

# use the latest timestamp snapshot (all strikes at the most recent scrape)
latest_time = df["time"].max()
snapshot = df[df["time"] == latest_time]

if snapshot.empty:
    st.warning("No data for the selected expiry/time.")
    st.stop()

# Compute ATM strike: prefer stored `spot` if available, otherwise fallback to max combined OI
if "spot" in snapshot.columns and snapshot["spot"].notna().any():
    spot = snapshot["spot"].mode().iloc[0]
    atm_idx = (snapshot["strike"] - spot).abs().idxmin()
    atm_row = snapshot.loc[atm_idx]
else:
    # fallback: choose strike with maximum total OI (ce_oi + pe_oi)
    snapshot = snapshot.copy()
    snapshot["total_oi"] = snapshot.get("ce_oi", 0).fillna(0) + snapshot.get("pe_oi", 0).fillna(0)
    atm_row = snapshot.loc[snapshot["total_oi"].idxmax()]

# --- compute previous snapshot for delta comparisons (if available)
unique_times = df["time"].sort_values(ascending=False).unique()
prev_time = unique_times[1] if len(unique_times) > 1 else None

if prev_time is not None:
    prev_snapshot = df[df["time"] == prev_time][["strike", "ce_oi", "pe_oi"]].copy()
    prev_snapshot = prev_snapshot.rename(columns={"ce_oi": "ce_oi_prev", "pe_oi": "pe_oi_prev"})
    snapshot = snapshot.merge(prev_snapshot, on="strike", how="left")
else:
    snapshot = snapshot.copy()
    snapshot["ce_oi_prev"] = 0
    snapshot["pe_oi_prev"] = 0

if delta_mode == "% Percentage":
    # percent change vs previous (avoid division by zero)
    snapshot["ce_delta"] = np.where(
        snapshot["ce_oi_prev"] != 0,
        (snapshot.get("ce_oi", 0).fillna(0) - snapshot.get("ce_oi_prev", 0).fillna(0)) / snapshot.get("ce_oi_prev", 0).replace(0, np.nan) * 100,
        0,
    )
    snapshot["pe_delta"] = np.where(
        snapshot["pe_oi_prev"] != 0,
        (snapshot.get("pe_oi", 0).fillna(0) - snapshot.get("pe_oi_prev", 0).fillna(0)) / snapshot.get("pe_oi_prev", 0).replace(0, np.nan) * 100,
        0,
    )
else:
    snapshot["ce_delta"] = snapshot.get("ce_oi", 0).fillna(0) - snapshot.get("ce_oi_prev", 0).fillna(0)
    snapshot["pe_delta"] = snapshot.get("pe_oi", 0).fillna(0) - snapshot.get("pe_oi_prev", 0).fillna(0)

# prepare display strings with arrows
def arrow_str(v, mode="Absolute"):
    # mode: "Absolute" or "% Percentage"
    try:
        val = float(v)
    except Exception:
        return "0"

    sign = ""
    if val > 0:
        sign = "▲"
    elif val < 0:
        sign = "▼"

    if mode == "% Percentage":
        # show one decimal place for percent
        return f"{sign}{abs(val):.1f}%" if val != 0 else "0"
    else:
        # absolute integer
        try:
            ival = int(val)
            return f"{sign}{ival}" if ival != 0 else "0"
        except Exception:
            return f"{sign}{abs(val):.1f}"

# (we keep numeric deltas in `ce_delta` and `pe_delta` and do not display the arrow-only columns)

# Metrics with delta shown as change from previous scrape for the ATM strike
atm_strike = int(atm_row["strike"])
atm_snapshot = snapshot[snapshot["strike"] == atm_strike].iloc[0]
col1, col2, col3 = st.columns(3)
col1.metric("ATM Strike", int(atm_snapshot["strike"]))
col2.metric("CE OI", int(atm_snapshot.get("ce_oi", 0)), delta=int(atm_snapshot.get("ce_delta", 0)))
col3.metric("PE OI", int(atm_snapshot.get("pe_oi", 0)), delta=int(atm_snapshot.get("pe_delta", 0)))

# -------- Table --------
st.subheader("Near-ATM OI Data")
# include numeric delta columns plus display strings; remove spot/atm as requested
display_cols = [
    "time",
    "expiry",
    "strike",
    # CE: current OI, NSE 'change in OI' and its arrow
    "ce_oi",
    "ce_delta",
    "ce_oi_change",
    "ce_oi_change_disp",
    # PE: current OI, NSE 'change in OI' and its arrow
    "pe_oi",
    "pe_delta",
    "pe_oi_change",
    "pe_oi_change_disp",
    "net_oi",
]

# Ensure the original NSE change columns exist (they come from DB as ce_oi_change / pe_oi_change)
if "ce_oi_change" not in snapshot.columns:
    snapshot["ce_oi_change"] = 0
if "pe_oi_change" not in snapshot.columns:
    snapshot["pe_oi_change"] = 0

# display arrows for the NSE-provided change-in-OI
snapshot["ce_oi_change_disp"] = snapshot["ce_oi_change"].apply(lambda x: arrow_str(x, "Absolute"))
snapshot["pe_oi_change_disp"] = snapshot["pe_oi_change"].apply(lambda x: arrow_str(x, "Absolute"))

display_df = snapshot.sort_values("strike").reset_index(drop=True)[display_cols]

# Styling: color delta text green for positive, red for negative; also color CE/PE cells based on delta
def color_delta_text(val):
    if isinstance(val, str) and val.startswith("▲"):
        return 'color: #10b981; font-weight: 700'
    if isinstance(val, str) and val.startswith("▼"):
        return 'color: #ef4444; font-weight: 700'
    return ''

def highlight_oi_cells(row):
    styles = [""] * len(row)
    # columns: time, expiry, strike, ce_oi, ce_delta_disp, pe_oi, pe_delta_disp, net_oi, spot, atm
    # determine sign of delta from the numeric delta columns (ce_delta / pe_delta)
    ce_sign = 0
    pe_sign = 0
    try:
        ce_val = float(row.get("ce_delta", 0))
        if ce_val > 0:
            ce_sign = 1
        elif ce_val < 0:
            ce_sign = -1
    except Exception:
        ce_sign = 0
    try:
        pe_val = float(row.get("pe_delta", 0))
        if pe_val > 0:
            pe_sign = 1
        elif pe_val < 0:
            pe_sign = -1
    except Exception:
        pe_sign = 0

    # index mapping with new display_cols:
    # 0 time,1 expiry,2 strike,3 ce_oi,4 ce_delta_disp,5 ce_oi_change,6 ce_oi_change_disp,
    # 7 pe_oi,8 pe_delta_disp,9 pe_oi_change,10 pe_oi_change_disp,11 net_oi
    # use slider-controlled alpha for background intensity
    if ce_sign > 0:
        styles[3] = f'background-color: rgba(16,185,129,{bg_alpha})'
        styles[4] = 'color: #10b981; font-weight:700'
    elif ce_sign < 0:
        styles[3] = f'background-color: rgba(239,68,68,{bg_alpha})'
        styles[4] = 'color: #ef4444; font-weight:700'

    # highlight NSE 'change in OI' column for CE (index 5) and color its arrow (6)
    try:
        ce_change_val = int(row.get("ce_oi_change", 0))
    except Exception:
        ce_change_val = 0
    if ce_change_val > 0:
        styles[5] = f'background-color: rgba(16,185,129,{bg_alpha})'
        styles[6] = 'color: #10b981; font-weight:700'
    elif ce_change_val < 0:
        styles[5] = f'background-color: rgba(239,68,68,{bg_alpha})'
        styles[6] = 'color: #ef4444; font-weight:700'

    # PE columns: current OI at 7, delta arrow at 8, NSE change at 9, its arrow at 10
    if pe_sign > 0:
        styles[7] = f'background-color: rgba(16,185,129,{bg_alpha})'
        styles[8] = 'color: #10b981; font-weight:700'
    elif pe_sign < 0:
        styles[7] = f'background-color: rgba(239,68,68,{bg_alpha})'
        styles[8] = 'color: #ef4444; font-weight:700'

    try:
        pe_change_val = int(row.get("pe_oi_change", 0))
    except Exception:
        pe_change_val = 0
    if pe_change_val > 0:
        styles[9] = f'background-color: rgba(16,185,129,{bg_alpha})'
        styles[10] = 'color: #10b981; font-weight:700'
    elif pe_change_val < 0:
        styles[9] = f'background-color: rgba(239,68,68,{bg_alpha})'
        styles[10] = 'color: #ef4444; font-weight:700'

    # Full-row highlight for ATM strike to make it visually prominent (toggleable)
    try:
        if highlight_atm and int(row.get("strike", -9999)) == int(atm_strike):
            atm_style = f'background-color: rgba(99,102,241,{atm_bg_alpha}); border: 1px solid rgba(99,102,241,{atm_border_alpha});'
            for i in range(len(styles)):
                # merge with existing style for that cell if present
                if styles[i]:
                    styles[i] = styles[i] + ";" + atm_style
                else:
                    styles[i] = atm_style
    except Exception:
        pass

    return styles

styled = display_df.style.apply(highlight_oi_cells, axis=1).applymap(
    color_delta_text,
    subset=["ce_oi_change_disp", "pe_oi_change_disp"],
)

st.dataframe(styled, width='stretch', height=400)

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
