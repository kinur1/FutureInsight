import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from io import StringIO
from datetime import timedelta

st.title('Data & chart Viewer')

# User input for tickers
ticker_input = st.text_input("Masukan Ticker (Seperti BTC-USD, BNB-USD):", 'BTC-USD, BNB-USD')
tickers = [ticker.strip().upper() for ticker in ticker_input.split(',') if ticker.strip()]

# User input for date range
default_start = (pd.to_datetime('today') - pd.DateOffset(years=1)).date()
default_end = pd.to_datetime('today').date()

start_date = st.date_input("Select start date", default_start)
end_date = st.date_input("Select end date", default_end)

if pd.to_datetime(start_date) >= pd.to_datetime(end_date):
    st.error("Tanggal akhir harus lebih besar dari tanggal mulai.")
    st.stop()

# Helper: flatten MultiIndex columns -> strings
def flatten_columns(columns):
    flat = []
    for col in columns:
        if isinstance(col, tuple):
            parts = [str(c) for c in col if c not in ("", None)]
            flat.append("_".join(parts) if parts else "")
        else:
            flat.append(str(col))
    return flat

# Helper: prepare DF for plotting, return (df_flattened, y_col)
def prepare_df_for_plot(df, ticker):
    df_reset = df.reset_index()

    # Flatten MultiIndex columns
    if isinstance(df_reset.columns, pd.MultiIndex):
        df_reset.columns = flatten_columns(df_reset.columns)
    else:
        df_reset.columns = [str(c) for c in df_reset.columns]

    # Pastikan kolom 'Date' ada
    if 'Date' not in df_reset.columns and 'index' in df_reset.columns:
        df_reset = df_reset.rename(columns={'index': 'Date'})

    # Cari kandidat kolom y untuk Close
    candidates = [
        f'Close_{ticker}',
        'Close',
        f'Adj Close_{ticker}',
        'Adj Close'
    ]
    y_col = next((c for c in candidates if c in df_reset.columns), None)
    return df_reset, y_col

# Helper: pilih kolom OHLC yang benar (bisa Close atau Close_TICKER)
def pick_col(df, base, ticker):
    for c in [f"{base}_{ticker}", base]:
        if c in df.columns:
            return c
    return None

# Download data untuk tiap ticker
data = {}
for ticker in tickers:
    try:
        stock_data = yf.download(
            ticker,
            start=pd.to_datetime(start_date),
            end=pd.to_datetime(end_date) + timedelta(days=1),  # end inclusive
            progress=False,
            group_by="column",
            auto_adjust=False,
            threads=False
        )
        if stock_data is not None and not stock_data.empty:
            data[ticker] = stock_data
        else:
            st.warning(f"No data found for ticker: {ticker}")
    except Exception as e:
        st.error(f"Error downloading data for ticker: {ticker}. Error: {e}")

st.write("Ticker berhasil dimuat:", list(data.keys()))

# Tampilkan table, chart, dan tombol unduh
for ticker, stock_data in data.items():
    st.subheader(f'Data for {ticker}')

    df_plot, y_col = prepare_df_for_plot(stock_data, ticker)

    # Tampilkan tabel yang sudah rapi (kolom flatten)
    st.dataframe(df_plot)

    # Candlestick membutuhkan OHLC
    open_col  = pick_col(df_plot, "Open", ticker)
    high_col  = pick_col(df_plot, "High", ticker)
    low_col   = pick_col(df_plot, "Low", ticker)
    close_col = pick_col(df_plot, "Close", ticker)

    st.subheader(f'Candlestick Chart for {ticker}')

    if "Date" not in df_plot.columns:
        st.warning(f"Kolom Date tidak ditemukan untuk {ticker}.")
        continue

    if not all([open_col, high_col, low_col, close_col]):
        st.warning(f"OHLC tidak lengkap untuk {ticker}. Kolom yang ada: {df_plot.columns.tolist()}")
        continue

    # ===== ATH / ATL (berdasarkan data yang dipilih) =====
    if high_col and low_col:
        ath = df_plot[high_col].max()
        atl = df_plot[low_col].min()

        ath_date = df_plot.loc[df_plot[high_col].idxmax(), "Date"]
        atl_date = df_plot.loc[df_plot[low_col].idxmin(), "Date"]

        c1, c2 = st.columns(2)
        c1.metric(
            label="All-Time High (range dipilih)",
            value=f"${ath:,.4f}",
            help=f"Tanggal: {ath_date}"
        )
        c2.metric(
            label="All-Time Low (range dipilih)",
            value=f"${atl:,.4f}",
            help=f"Tanggal: {atl_date}"
        )
    else:
        st.warning("Tidak bisa menghitung ATH / ATL (kolom High / Low tidak ditemukan).")
        ath, atl = None, None  # biar aman

    # ===== Candlestick =====
    fig = go.Figure(data=[go.Candlestick(
        x=df_plot["Date"],
        open=df_plot[open_col],
        high=df_plot[high_col],
        low=df_plot[low_col],
        close=df_plot[close_col],
        increasing_line_color="green",
        decreasing_line_color="red",
        increasing_fillcolor="green",
        decreasing_fillcolor="red",
        name=ticker
    )])

    # ===== Garis ATH & ATL =====
    if ath is not None and atl is not None:
        fig.add_hline(
            y=ath,
            line_dash="dot",
            line_color="green",
            annotation_text="ATH",
            annotation_position="top left"
        )
        fig.add_hline(
            y=atl,
            line_dash="dot",
            line_color="red",
            annotation_text="ATL",
            annotation_position="bottom left"
        )

    fig.update_layout(
        title=f"{ticker} Candlestick",
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_dark",
        xaxis_rangeslider_visible=False
    )

    st.plotly_chart(fig, use_container_width=True)

    # Download CSV pakai df_plot (kolom sudah rata)
    csv_buffer = StringIO()
    df_plot.to_csv(csv_buffer, index=False)
    csv_data = csv_buffer.getvalue()

