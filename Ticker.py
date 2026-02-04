import os
import time
import random
import datetime as dt

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Ticker Crypto", layout="wide")

BACKUP_PATH = "crypto_backup.csv"

# =========================
# 1) Fetch Yahoo (anti 429)
# =========================
@st.cache_data(ttl=6 * 60 * 60)  # cache 6 jam supaya jarang hit Yahoo
def fetch_yahoo_crypto_table():
    url = "https://finance.yahoo.com/crypto"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    }

    # retry 3x jika 429 / gangguan sementara
    last_status = None
    for attempt in range(3):
        r = requests.get(url, headers=headers, timeout=15)
        last_status = r.status_code

        if r.status_code == 200:
            tables = pd.read_html(r.text)
            df = tables[0]
            df.columns = [str(c).strip() for c in df.columns]
            return df

        if r.status_code == 429:
            # exponential backoff + random jitter
            wait = (2 ** attempt) * 3 + random.uniform(0, 2)
            time.sleep(wait)
            continue

        r.raise_for_status()

    raise Exception(f"Kena rate limit Yahoo (HTTP {last_status}). Coba lagi beberapa menit.")


# =========================================
# 2) Ambil data dengan fallback ke backup
# =========================================
def get_table_with_fallback():
    try:
        df = fetch_yahoo_crypto_table()
        # simpan backup setiap berhasil
        df.to_csv(BACKUP_PATH, index=False)
        return df, "LIVE (Yahoo Finance)"
    except Exception as e:
        if os.path.exists(BACKUP_PATH):
            df = pd.read_csv(BACKUP_PATH)
            return df, f"BACKUP (karena: {e})"
        # kalau tidak ada backup sama sekali, lempar error
        raise e


# =========================
# UI
# =========================
st.title("Daftar Ticker Crypto")

# cooldown refresh biar user gak spam
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = 0.0

top1, top2, top3 = st.columns([1.2, 1.8, 4])

with top1:
    if st.button("🔄 Refresh Data"):
        now = time.time()
        if now - st.session_state.last_refresh < 60:
            st.warning("Tunggu 60 detik sebelum refresh lagi (hindari HTTP 429).")
        else:
            st.session_state.last_refresh = now
            st.cache_data.clear()
            st.rerun()

with top2:
    st.caption(f"Update: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ambil data (live atau backup)
try:
    df, source_info = get_table_with_fallback()
except Exception as err:
    st.error("Gagal mengambil data dari Yahoo Finance dan tidak ada backup lokal.")
    st.code(str(err))
    st.stop()

st.info(f"Sumber data: **{source_info}**")

# =========================
# Filter & Tampilan
# =========================
df_show = df.copy()

# deteksi kolom symbol/name (lebih tahan perubahan)
symbol_col = "Symbol" if "Symbol" in df_show.columns else df_show.columns[0]
name_col = "Name" if "Name" in df_show.columns else None

c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    q = st.text_input("🔎 Cari (symbol / nama)", "")
with c2:
    only_usd = st.checkbox("Hanya pair -USD", value=True)
with c3:
    view_mode = st.selectbox("Mode tampilan", ["Tabel", "Kartu"])

if only_usd:
    df_show = df_show[df_show[symbol_col].astype(str).str.endswith("-USD", na=False)]

if q.strip():
    q_low = q.strip().lower()
    mask_symbol = df_show[symbol_col].astype(str).str.lower().str.contains(q_low, na=False)
    if name_col:
        mask_name = df_show[name_col].astype(str).str.lower().str.contains(q_low, na=False)
        df_show = df_show[mask_symbol | mask_name]
    else:
        df_show = df_show[mask_symbol]

st.caption(f"Total tampil: **{len(df_show)}** ticker")

if view_mode == "Tabel":
    st.dataframe(df_show, use_container_width=True, hide_index=True)
else:
    # Mode kartu dibatasi agar ringan
    show_limit = 200
    cols = df_show.columns.tolist()

    for _, row in df_show.head(show_limit).iterrows():
        sym = row.get(symbol_col, "")
        nm = row.get(name_col, "") if name_col else ""

        # kolom-kolom Yahoo bisa beda nama, jadi pakai fallback key
        price = row.get("Price (Intraday)", row.get("Price", ""))
        chg = row.get("Change", "")
        pct = row.get("% Change", row.get("Change %", ""))
        mcap = row.get("Market Cap", "")
        vol = row.get("Volume in Currency (Since 0:00 UTC)", row.get("Volume", ""))

        st.markdown(
            f"""
            <div style="padding:12px;border:1px solid #ddd;border-radius:12px;margin-bottom:10px;">
              <div style="font-size:18px;font-weight:700;">{sym}
                <span style="font-weight:400;color:#666;">{nm}</span>
              </div>
              <div style="margin-top:6px;">
                <b>Price:</b> {price} &nbsp; | &nbsp;
                <b>Change:</b> {chg} ({pct}) &nbsp; | &nbsp;
                <b>Vol:</b> {vol} &nbsp; | &nbsp;
                <b>MCAP:</b> {mcap}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.info(f"Mode kartu dibatasi {show_limit} item pertama supaya tidak berat.")
