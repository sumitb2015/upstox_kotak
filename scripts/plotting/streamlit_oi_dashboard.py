import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import upstox_client
from upstox_client.rest import ApiException
import sys
import os
from datetime import datetime, time, timedelta

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.api.market_data import get_ltp, download_nse_market_data, get_market_quotes, get_market_quote_for_instrument
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy

# --- Configuration ---
st.set_page_config(page_title="Upstox Real-time OI Dashboard", layout="wide")

# Custom CSS for premium look
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    [data-testid="stMetric"] {
        background-color: rgba(30, 30, 30, 0.6);
        padding: 15px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: rgba(0, 255, 127, 0.3);
    }
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }
    div[data-testid="stSidebar"] {
        background-color: #161a24;
    }
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: #00ff7f;
        letter-spacing: -0.5px;
    }
    /* Center align header text for metrics */
    [data-testid="stMetricLabel"] {
        text-align: center;
        width: 100%;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.8rem;
        color: #888;
    }
    [data-testid="stMetricValue"] {
        text-align: center;
        width: 100%;
        color: #fff;
    }
    /* Reduce title margins */
    .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 0.1rem !important;
    }
    h1 {
        margin-top: 0rem !important;
        padding-top: 0rem !important;
        font-size: 2rem !important;
    }
    [data-testid="stMetricDelta"] {
        justify-content: center;
    }
    /* Index & Straddle Header Styles */
    .index-card {
        text-align: center;
        padding: 10px 5px;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        min-height: 100px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .index-name { color: #bbb; font-size: 0.9rem; font-weight: 600; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.8px; }
    .index-price { color: #fff; font-size: 1.1rem; font-weight: bold; margin-bottom: 2px; }
    .index-change { font-size: 0.85rem; font-weight: 500; }

    .straddle-header {
        display: flex;
        flex-direction: row;
        justify-content: space-around;
        align-items: center;
        background: rgba(255, 215, 0, 0.05);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(255, 215, 0, 0.1);
        margin-bottom: 20px;
        width: 100%;
    }
    .stat-box {
        flex: 1;
        text-align: center;
        padding: 0 10px;
    }
    .stat-label { color: #888; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
    .stat-value { color: #ffd700; font-size: 1.6rem; font-weight: 800; }
    .stat-delta { font-size: 0.95rem; font-weight: 600; margin-top: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

@st.cache_data(ttl=3600)
def get_tokens():
    """
    Retrieve the Upstox access token from the local filesystem.
    
    Returns:
        str: Access token if found, else None.
    """
    token_path = os.path.join(PROJECT_ROOT, "lib/core/accessToken.txt")
    if not os.path.exists(token_path):
        st.error("❌ Access token file not found.")
        return None
    with open(token_path, "r") as f:
        return f.read().strip()

@st.cache_data(ttl=3600)
def get_cached_nse_data():
    """
    Download and cache NSE market data for instrument mapping.
    
    Returns:
        pd.DataFrame: Master instrument data.
    """
    return download_nse_market_data()

@st.cache_data(ttl=60) # Cache for 60 seconds to match refresh interval
def get_v3_intraday_data(instrument_key, api_instance_token):
    """
    Fetch 1-minute intraday candle data from Upstox V3 API.
    Fallback to last available trading day if today (holiday/weekend) is empty.
    
    Args:
        instrument_key (str): The instrument key (e.g., "NSE_FO|49229")
        api_instance_token (str): The Upstox access token
        
    Returns:
        pd.DataFrame: DataFrame with timestamp, OHLCV and OI data
    """
    configuration = upstox_client.Configuration()
    configuration.access_token = api_instance_token
    api_instance = upstox_client.HistoryApi(upstox_client.ApiClient(configuration))
    
    try:
        # 1. Try Intraday first
        api_response = api_instance.get_intra_day_candle_data(instrument_key, "1minute", "2.0")
        if api_response.status == 'success' and api_response.data.candles:
            df = pd.DataFrame(api_response.data.candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            df = df.sort_values('timestamp')
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']]
            
        # 2. Fallback: Historical (Last 5 days to find recent session)
        # st.toast(f"Intraday empty for {instrument_key}, fetching historical backup...", icon="🔄")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)
        
        # We need to manually call the historical endpoint since upstox-client might not have easy helper here
        # Using the same logic as lib.api.historical.get_historical_data_v3 but inline for Streamlit
        import urllib.parse as urlparse
        import requests
        
        encoded_key = urlparse.quote(instrument_key, safe='')
        url = f"https://api.upstox.com/v3/historical-candle/{encoded_key}/minutes/1/{to_date.strftime('%Y-%m-%d')}/{from_date.strftime('%Y-%m-%d')}"
        headers = {'Accept': 'application/json', 'Authorization': f'Bearer {api_instance_token}'}
        
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success' and data.get('data', {}).get('candles'):
                candles = data['data']['candles']
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None) # History is usually naive or UTC, verify? 
                # Upstox history is typically offset-naive ISO8601 or similar. 
                # Let's simple-parse and assume it matches
                df = df.sort_values('timestamp')
                
                # Filter for only the LAST available date
                last_date = df['timestamp'].dt.date.iloc[-1]
                df = df[df['timestamp'].dt.date == last_date]
                
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi']]
                
        return pd.DataFrame()
    except Exception as e:
        # st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def calculate_vwap(df):
    """
    Calculate standard VWAP: Cumulative(Price * Volume) / Cumulative(Volume).
    Used for single instrument plots.
    
    Args:
        df (pd.DataFrame): DataFrame containing 'close' and 'volume' columns
        
    Returns:
        pd.Series: The VWAP series
    """
    if df.empty: return None
    # Use average price of candle (HLC/3) or just close for simplicity in straddle combined
    # For straddle, close is standard
    v = df['volume'].cumsum()
    vp = (df['close'] * df['volume']).cumsum()
    return vp / v

@st.cache_data(ttl=60)
def get_iv_history(symbol, expiry, day_str=None):
    """
    Fetch historical Implied Volatility (IV) data from local CSV storage.
    
    Args:
        symbol (str): Trading symbol (NIFTY/BANKNIFTY).
        expiry (str): Expiry date in YYYY-MM-DD format.
        day_str (str, optional): Specific date to fetch for. Defaults to today.
        
    Returns:
        pd.DataFrame: IV history dataframe.
    """
    if day_str is None:
        day_str = datetime.now().strftime('%Y-%m-%d')
    
    file_path = os.path.join(PROJECT_ROOT, f"data/iv_history/iv_history_{day_str}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path)
        # Ensure timestamp is comparable
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        # Filter for symbol and expiry
        df = df[(df['symbol'] == symbol) & (df['expiry'] == expiry)]
        return df
    except Exception as e:
        return pd.DataFrame()

# --- Main Dashboard ---

def main():
    """
    Main entry point for the Streamlit dashboard.
    Handles navigation, data fetching, and page-specific rendering for:
    1. Market Overview (Option Chain)
    2. OI Trend Analysis (Multi-Strike plotting)
    3. Straddle Analysis (Combined Premium tracking)
    """
    st.title("🔥 Upstox Professional OI Dashboard")
    
    # Sidebar Refresh
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 120, 60)
    st_autorefresh(interval=refresh_interval * 1000, key="oi_refresh")

    access_token = get_tokens()
    if not access_token:
        return

    # Sidebar Navigation
    nse_data = get_cached_nse_data() # Initialize globally
    st.sidebar.header("🗺️ Navigation")
    page = st.sidebar.radio("Go to", ["Market Overview", "OI Trend Analysis", "Trending OI", "Straddle Analysis", "Strangle Analysis", "PCR by Strike"], index=0)
    
    # Sidebar Filters
    st.sidebar.header("🎯 Filters")
    symbol = st.sidebar.selectbox("Symbol", ["NIFTY", "BANKNIFTY", "FINNIFTY"], index=0)
    
    # 1. Fetch All Expiries
    from lib.api.option_chain import get_expiries
    with st.spinner(f"Fetching {symbol} expiries..."):
        INDEX_MAP_KEYS = {"NIFTY": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank", "FINNIFTY": "NSE_INDEX|Nifty Fin Service"}
        raw_expiries = get_expiries(access_token, INDEX_MAP_KEYS[symbol])
    
    if not raw_expiries:
        st.error(f"Could not fetch expiries for {symbol}")
        return
        
    # Convert to string if they are datetime
    expiries = [e.strftime("%Y-%m-%d") if not isinstance(e, str) else e for e in raw_expiries]
    selected_expiry = st.sidebar.selectbox("Select Expiry", expiries, index=0)
    
    # 2. Market Resolution (Multiple Indices)
    MONITOR_INDICES = {
        "Nifty 50": "NSE_INDEX:Nifty 50",
        "Bank Nifty": "NSE_INDEX:Nifty Bank",
        "Nifty IT": "NSE_INDEX:Nifty IT",
        "Nifty Metal": "NSE_INDEX:Nifty Metal",
        "Nifty Pharma": "NSE_INDEX:Nifty Pharma",
        "Nifty FMCG": "NSE_INDEX:Nifty FMCG",
        "Nifty Auto": "NSE_INDEX:Nifty Auto",
        "Nifty Realty": "NSE_INDEX:Nifty Realty"
    }
    
    # Map selected symbol to its specific key for ATM
    INDEX_KEY_MAP = {"NIFTY": "NSE_INDEX|Nifty 50", "BANKNIFTY": "NSE_INDEX|Nifty Bank", "FINNIFTY": "NSE_INDEX|Nifty Fin Service"}
    
    # 1. Fetch current index row
    # Use keys with pipes for the request, but SDK returns colons
    index_quotes = get_market_quotes(access_token, [k.replace(':', '|') for k in MONITOR_INDICES.values()])
    
    # 3. ATM resolution for selected instrument
    selected_key = INDEX_KEY_MAP[symbol]
    selected_quote = next((v for k, v in index_quotes.items() if k.replace(':', '|') == selected_key), None) or get_market_quote_for_instrument(access_token, selected_key)
    
    if selected_quote:
        spot = selected_quote.get('last_price', 0)
        step = 100 if symbol == "BANKNIFTY" else 50
        atm = round(spot / step) * step
    else:
        st.sidebar.error("Could not fetch spot price for calculation.")
        return
        
    # --- Sidebar Content (Page Specific) ---
    st.sidebar.markdown("---")
    
    # Initialize page variables to prevent UnboundLocalError
    show_chain = False
    strikes = []
    opt_types = []
    view_mode = "Single (OI)"
    visible_contracts = []
    straddle_strike = atm
    cum_strikes_range = 10
    ce_strikes = []
    pe_strikes = []
    
    if page == "Market Overview":
        st.sidebar.subheader("👁️ View Controls")
        show_chain = st.sidebar.checkbox("Show Option Chain", value=True)
        
    elif page == "OI Trend Analysis":
        st.sidebar.subheader("🎯 Strike Selection")
        strikes_input = st.sidebar.text_input("Strikes (comma-separated)", value=str(atm))
        strikes = [int(s.strip()) for s in strikes_input.split(",") if s.strip().isdigit()]
        opt_types = st.sidebar.multiselect("Option Types", ["CE", "PE"], default=["CE", "PE"])
        
        st.sidebar.subheader("👁️ Plot Mode")
        view_mode = st.sidebar.radio("Go to", ["Single (OI)", "Split (Price+OI)", "Triple (Price+IV+OI)"], index=0, label_visibility="collapsed")
        
        if strikes and opt_types:
            st.sidebar.subheader("🎯 Visibility")
            visible_contracts = []
            for s in strikes:
                for ot in opt_types:
                    label = f"{s} {ot}"
                    if st.sidebar.checkbox(label, value=True, key=f"vis_{label}"):
                        visible_contracts.append(label)
        else:
            visible_contracts = []
            
    elif page == "Trending OI":
        st.sidebar.subheader("🎯 Strike Selection")
        # Generate a wider range of possible strikes for selection
        step = 100 if symbol == "BANKNIFTY" else 50
        # Offer ATM +/- 20 strikes to cover wide moves
        possible_strikes = [atm + (i * step) for i in range(-20, 21)]
        
        # Default selection: ATM + 6 strikes (User seems to like 7 strikes including ATM)
        default_strikes = [atm + (i * step) for i in range(0, 7)]
        
        target_strikes = st.sidebar.multiselect(
            "Select Strikes", 
            possible_strikes, 
            default=default_strikes
        )
        
        st.sidebar.info(f"Selected {len(target_strikes)} strikes.")

    elif page == "Straddle Analysis":
        st.sidebar.subheader("🧭 Strike Selection")
        # Define a range of strikes for the dropdown around ATM
        straddle_strikes = [atm + (i * (100 if symbol == "BANKNIFTY" else 50)) for i in range(-10, 11)]
        straddle_strike = st.sidebar.selectbox("Select Strike", straddle_strikes, index=10)

    elif page == "Strangle Analysis":
        st.sidebar.subheader("🧭 Strangle Setup")
        step = 100 if symbol == "BANKNIFTY" else 50
        possible_strikes = [atm + (i * step) for i in range(-20, 21)]
        
        ce_strikes = st.sidebar.multiselect("Select CE Strikes", possible_strikes, default=[atm + step])
        pe_strikes = st.sidebar.multiselect("Select PE Strikes", possible_strikes, default=[atm - step])

    # 4. Global Header Metrics
    st.markdown("---")

    # --- Market Overview Page ---
    if page == "Market Overview":
        st.subheader(f"🏛️ Market Overview: {symbol} (ATM: {atm})")
        
        # Display Index LTP Mini-Stats
        if selected_quote:
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Index LTP", f"₹{spot:,.2f}", f"{selected_quote.get('change', 0):+.2f}")
            with c2: st.metric("ATM Strike", f"{atm}")
            with c3: st.metric("Expiry", selected_expiry)

        if show_chain:
            from lib.api.option_chain import get_option_chain_dataframe
            with st.spinner("Fetching full option chain..."):
                df_chain = get_option_chain_dataframe(access_token, INDEX_KEY_MAP[symbol], selected_expiry)
            
            if df_chain is not None and not df_chain.empty:
                # Calculate % Changes
                df_chain['ce_pct'] = ((df_chain['ce_ltp'] - df_chain['ce_close']) / df_chain['ce_close'] * 100).fillna(0)
                df_chain['pe_pct'] = ((df_chain['pe_ltp'] - df_chain['pe_close']) / df_chain['pe_close'] * 100).fillna(0)
                df_chain['ce_oi_pct'] = ((df_chain['ce_oi'] - df_chain['ce_prev_oi']) / df_chain['ce_prev_oi'] * 100).fillna(0)
                df_chain['pe_oi_pct'] = ((df_chain['pe_oi'] - df_chain['pe_prev_oi']) / df_chain['pe_prev_oi'] * 100).fillna(0)
                df_chain['ce_oi_chg'] = df_chain['ce_oi'] - df_chain['ce_prev_oi']
                df_chain['pe_oi_chg'] = df_chain['pe_oi'] - df_chain['pe_prev_oi']

                # Calculation for Buildup
                def calculate_buildup(price_pct, oi_pct):
                    if price_pct > 0 and oi_pct > 0: return "Long Buildup"
                    if price_pct < 0 and oi_pct > 0: return "Short Buildup"
                    if price_pct > 0 and oi_pct < 0: return "Short Covering"
                    if price_pct < 0 and oi_pct < 0: return "Long Unwinding"
                    return "-"

                df_chain['ce_buildup'] = df_chain.apply(lambda x: calculate_buildup(x['ce_pct'], x['ce_oi_pct']), axis=1)
                df_chain['pe_buildup'] = df_chain.apply(lambda x: calculate_buildup(x['pe_pct'], x['pe_oi_pct']), axis=1)

                # Filter for ATM range
                range_val = 1500 if symbol == "BANKNIFTY" else 750
                display_chain = df_chain[(df_chain['strike_price'] >= atm - range_val) & (df_chain['strike_price'] <= atm + range_val)].copy()
                
                # Identify Top 3 Unique OI values for CE and PE INDIVIDUALLY within the ACTIVE viewport
                top_ce_oi_vals = sorted(display_chain['ce_oi'].fillna(0).astype(int).unique(), reverse=True)[:3]
                top_pe_oi_vals = sorted(display_chain['pe_oi'].fillna(0).astype(int).unique(), reverse=True)[:3]
                
                # Format and Style
                display_chain = display_chain.rename(columns={
                    'ce_buildup': 'BUILDUP', 'ce_oi': 'OI', 'ce_oi_chg': 'OI CHG', 'ce_oi_pct': 'OI %', 'ce_ltp': 'PRICE', 'ce_pct': 'CHG %',
                    'strike_price': 'STRIKE', 
                    'pe_pct': 'CHG % ', 'pe_ltp': 'PRICE ', 'pe_oi_pct': 'OI % ', 'pe_oi_chg': 'OI CHG ', 'pe_oi': 'OI ', 'pe_buildup': 'BUILDUP '
                })

                # HTML Style and Table Logic
                style_html = """<style>
    .opt-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; background: rgba(255, 255, 255, 0.02); border-radius: 12px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.1); }
    .opt-table th { background-color: rgba(255, 255, 255, 0.08); padding: 10px 4px; text-align: center; color: #fff; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; border-bottom: 2px solid rgba(255, 255, 255, 0.1); letter-spacing: 0.5px; }
    .opt-table td { padding: 8px 4px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.03); font-size: 0.85rem; color: #eee; font-weight: 500; transition: all 0.2s; }
    .opt-table tr:hover td { background-color: rgba(255, 255, 255, 0.05); }
    .atm-row { background-color: rgba(0, 255, 127, 0.18) !important; border-top: 1px solid rgba(0, 255, 127, 0.3); border-bottom: 1px solid rgba(0, 255, 127, 0.3); }
    .top-oi-ce { background-color: #ff5000 !important; color: #fff !important; font-weight: 900 !important; border: 1.5px solid #fff !important; box-shadow: 0 0 10px rgba(255, 80, 0, 0.4); }
    .top-oi-pe { background-color: #ff5000 !important; color: #fff !important; font-weight: 900 !important; border: 1.5px solid #fff !important; box-shadow: 0 0 10px rgba(255, 80, 0, 0.4); }
    .strike-col { font-weight: 900 !important; color: #ffd700 !important; font-size: 1.1rem !important; background-color: rgba(255, 215, 0, 0.05); border-left: 1px solid rgba(255, 215, 0, 0.1); border-right: 1px solid rgba(255, 215, 0, 0.1); }
    .pos-val { color: #00ff7f; font-weight: 700; }
    .neg-val { color: #ff4b4b; font-weight: 700; }
    </style>"""

                table_rows = []
                for _, row in display_chain.iterrows():
                    is_atm = 'class="atm-row"' if row['STRIKE'] == atm else ""
                    def fmt_pct(v):
                        cls = "pos-val" if v > 0 else ("neg-val" if v < 0 else "")
                        return f'<span class="{cls}">{v:+.2f}%</span>'
                    def fmt_chg(v):
                        cls = "pos-val" if v > 0 else ("neg-val" if v < 0 else "")
                        return f'<span class="{cls}">{int(v):+,}</span>'
                    def fmt_buildup(b):
                        if "-" in b: return "-"
                        cls = "pos-val" if b in ["Long Buildup", "Short Covering"] else "neg-val"
                        return f'<span class="{cls}" style="font-size: 0.85rem;">{b}</span>'

                    ce_oi_class = 'class="top-oi-ce"' if int(row['OI']) in top_ce_oi_vals else ""
                    pe_oi_class = 'class="top-oi-pe"' if int(row['OI ']) in top_pe_oi_vals else ""

                    row_html = f'<tr {is_atm}>'
                    row_html += f'<td>{fmt_buildup(row["BUILDUP"])}</td>'
                    row_html += f'<td {ce_oi_class}>{int(row["OI"]):,}</td>'
                    row_html += f'<td>{fmt_chg(row["OI CHG"])}</td>'
                    row_html += f'<td>{fmt_pct(row["OI %"])}</td>'
                    row_html += f'<td>{row["PRICE"]:,.2f}</td>'
                    row_html += f'<td>{fmt_pct(row["CHG %"])}</td>'
                    row_html += f'<td class="strike-col">{int(row["STRIKE"]):,}</td>'
                    row_html += f'<td>{fmt_pct(row["CHG % "])}</td>'
                    row_html += f'<td>{row["PRICE "]:,.2f}</td>'
                    row_html += f'<td>{fmt_pct(row["OI % "])}</td>'
                    row_html += f'<td>{fmt_chg(row["OI CHG "])}</td>'
                    row_html += f'<td {pe_oi_class}>{int(row["OI "]):,}</td>'
                    row_html += f'<td>{fmt_buildup(row["BUILDUP "])}</td>'
                    row_html += '</tr>'
                    table_rows.append(row_html)
                
                table_header = '<table class="opt-table"><thead><tr>'
                table_header += '<th>BUILDUP</th><th>OI</th><th>OI CHG</th><th>OI %</th><th>LTP</th><th>CHG %</th><th>STRIKE</th><th>CHG %</th><th>LTP</th><th>OI %</th><th>OI CHG</th><th>OI</th><th>BUILDUP</th>'
                table_header += '</tr></thead><tbody>'
                
                full_html = style_html + table_header + "".join(table_rows) + "</tbody></table>"
                st.html(full_html)

    # --- Trending OI Page ---
    if page == "Trending OI":
        st.subheader(f"📈 Trending OI Analysis ({symbol})")
        
        if not target_strikes:
            st.warning("⚠️ Please select at least one strike from the sidebar.")
        else:
            import concurrent.futures

            # Function for parallel execution
            def fetch_strike_timeseries(strike, opt_type):
                key = get_option_instrument_key(symbol, strike, opt_type, nse_data, selected_expiry)
                if key:
                    df = get_v3_intraday_data(key, access_token)
                    if not df.empty:
                        return (strike, opt_type, df[['timestamp', 'oi']].set_index('timestamp'))
                return (strike, opt_type, None)

            # Fetch Index Data for LTP
            with st.spinner("Fetching Index Data..."):
                index_key = INDEX_KEY_MAP[symbol]
                index_df = get_v3_intraday_data(index_key, access_token)
                if not index_df.empty:
                    index_df = index_df.set_index('timestamp')
                    index_df = index_df[~index_df.index.duplicated(keep='first')] # Ensure unique index

            with st.spinner(f"Fetching OI for {len(possible_strikes)} strikes..."):
                nse_data = get_cached_nse_data()
                all_strike_data = {} 
                
                # Prepare tasks
                tasks = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    for strike in possible_strikes:
                        tasks.append(executor.submit(fetch_strike_timeseries, strike, "CE"))
                        tasks.append(executor.submit(fetch_strike_timeseries, strike, "PE"))
                    
                    for future in concurrent.futures.as_completed(tasks):
                        strike, opt_type, df = future.result()
                        if df is not None:
                            if strike not in all_strike_data: all_strike_data[strike] = {'CE': None, 'PE': None}
                            all_strike_data[strike][opt_type] = df

            # Filter data
            ce_dfs = []
            pe_dfs = []
            
            for strike in target_strikes:
                if strike in all_strike_data:
                    if all_strike_data[strike]['CE'] is not None:
                        ce_dfs.append(all_strike_data[strike]['CE'])
                    if all_strike_data[strike]['PE'] is not None:
                        pe_dfs.append(all_strike_data[strike]['PE'])
            
            if not ce_dfs or not pe_dfs:
                st.error("Could not fetch enough data for analysis.")
            else:
                # 1. Aggregate Total OI first
                total_ce_oi = pd.concat(ce_dfs).groupby(level=0).sum().sort_index()
                total_pe_oi = pd.concat(pe_dfs).groupby(level=0).sum().sort_index()
                
                # Align indices
                common_idx = total_ce_oi.index.intersection(total_pe_oi.index)
                if not index_df.empty:
                    common_idx = common_idx.intersection(index_df.index)
                
                final_df = pd.DataFrame(index=common_idx)
                final_df['Total CE OI'] = total_ce_oi.loc[common_idx]['oi']
                final_df['Total PE OI'] = total_pe_oi.loc[common_idx]['oi']
                if not index_df.empty:
                    final_df['LTP'] = index_df.loc[common_idx]['close']
                else:
                    final_df['LTP'] = 0

                # 2. Calculate Change in OI
                # Toggle for Calculation Mode (Broker dependent)
                calc_mode = st.sidebar.radio("Change Reference", ["vs Yesterday Close", "vs Today Open (09:15)"], index=0)
                
                prev_ce = 0
                prev_pe = 0
                
                if calc_mode == "vs Yesterday Close":
                    from lib.api.option_chain import get_option_chain_dataframe
                    # Fetch Option Chain Snapshot for Prev OI
                    with st.spinner("Fetching Option Chain Snapshot for Reference OI..."):
                        snapshot_chain = get_option_chain_dataframe(access_token, INDEX_KEY_MAP[symbol], selected_expiry)
                    
                    if snapshot_chain is not None and not snapshot_chain.empty:
                        snap_subset = snapshot_chain[snapshot_chain['strike_price'].astype(int).isin(target_strikes)]
                        prev_ce = snap_subset['ce_prev_oi'].sum()
                        prev_pe = snap_subset['pe_prev_oi'].sum()
                        
                        # Debug Info
                        with st.expander("🔍 Debug: Reference OI (Yesterday Close)"):
                            st.write(f"Strikes: {target_strikes}")
                            st.write(f"Total CE Prev OI: {prev_ce:,.0f}")
                            st.write(f"Total PE Prev OI: {prev_pe:,.0f}")
                            st.dataframe(snap_subset[['strike_price', 'ce_prev_oi', 'pe_prev_oi']])
                    else:
                        st.warning("⚠️ Could not fetch Previous OI snapshot. Falling back to day open.")
                        prev_ce = final_df['Total CE OI'].iloc[0]
                        prev_pe = final_df['Total PE OI'].iloc[0]
                else:
                    # vs Today Open (09:15)
                    prev_ce = final_df['Total CE OI'].iloc[0]
                    prev_pe = final_df['Total PE OI'].iloc[0]
                    with st.expander("🔍 Debug: Reference OI (09:15 Open)"):
                         st.write(f"Total CE Open OI: {prev_ce:,.0f}")
                         st.write(f"Total PE Open OI: {prev_pe:,.0f}")
                
                final_df['Chng CE OI'] = final_df['Total CE OI'] - prev_ce
                final_df['Chng PE OI'] = final_df['Total PE OI'] - prev_pe
                final_df['Net Change'] = final_df['Chng PE OI'] - final_df['Chng CE OI'] # Bullish if Positive
                final_df['PCR'] = final_df['Total PE OI'] / final_df['Total CE OI'] # PCR on Total OI
                
                # 3. Visualization
                
                # Top Row: Dual Charts
                c1, c2 = st.columns(2)
                
                with c1:
                    # Chart 1: Trending OI Sentiment (Net Change vs LTP)
                    fig_sent = make_subplots(specs=[[{"secondary_y": True}]])
                    
                    # Net Change (Area)
                    fig_sent.add_trace(go.Scatter(
                        x=final_df.index, y=final_df['Net Change'],
                        mode='lines', name='Net OI Change',
                        line=dict(color='#00ff00', width=1),
                        fill='tozeroy',
                        fillcolor='rgba(0, 255, 0, 0.1)'
                    ), secondary_y=False)
                    
                    # LTP (Line)
                    fig_sent.add_trace(go.Scatter(
                        x=final_df.index, y=final_df['LTP'],
                        mode='lines', name='Index LTP',
                        line=dict(color='#ffd700', width=2)
                    ), secondary_y=True)
                    
                    fig_sent.update_layout(
                        title="Trending OI Sentiment (Net vs Price)",
                        template="plotly_dark", height=400,
                        margin=dict(l=10, r=10, t=60, b=40),
                        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor='center'),
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_sent, use_container_width=True)
                    
                with c2:
                    # Chart 2: Trending OI (Call Chg vs Put Chg)
                    fig_trend = go.Figure()
                    fig_trend.add_trace(go.Scatter(
                        x=final_df.index, y=final_df['Chng CE OI'],
                        mode='lines', name='Call OI Chg',
                        line=dict(color='#ff4b4b', width=2)
                    ))
                    fig_trend.add_trace(go.Scatter(
                        x=final_df.index, y=final_df['Chng PE OI'],
                        mode='lines', name='Put OI Chg',
                        line=dict(color='#00ff7f', width=2)
                    ))
                    fig_trend.add_hline(y=0, line_dash="dash", line_color="gray")
                    
                    fig_trend.update_layout(
                        title="Trending OI (Call Change vs Put Change)",
                        template="plotly_dark", height=400,
                        margin=dict(l=10, r=10, t=60, b=40),
                        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor='center'),
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_trend, use_container_width=True)

                # 4. Detailed Data Table
                # 4. Detailed Data Table
                st.subheader("📋 Trending OI Data")
                
                # Reverse order for table (Latest first)
                table_df = final_df.sort_index(ascending=False).copy()
                
                # Format Columns & Rename to match user request
                # User Columns: Time, LTP, Chng. In Call OI, Chng. In Put OI, Diff. In OI, Direct. Of chng, Chng. In Direction, Direction of Chng %, PCR
                
                table_df['Time'] = table_df.index.strftime('%H:%M:%S') # User showed seconds
                
                # 1. Diff. In OI (Net Change)
                table_df['Diff. In OI'] = table_df['Net Change']
                
                # 2. Direct. Of chng (Signal)
                def get_direction(val):
                    return "BUY 🟢" if val > 0 else "SELL 🔴"
                table_df['Direct. Of chng'] = table_df['Diff. In OI'].apply(get_direction)
                
                # 3. Chng. In Direction (Diff of Net Change)
                # Next row is previous time, so Current - Next = Change from Previous
                table_df['Chng. In Direction'] = table_df['Diff. In OI'].diff(-1)
                
                # 4. Direction of Chng %
                # Formula: (Chng In Direction / Abs(Previous Diff. In OI)) * 100
                # Using Abs() for denominator to keep sign logic consistent with direction?
                # User's example: 11L / 5Cr (negative) = -2.26%.
                # If Chng is +11L and base is -5Cr. 
                # Let's use simple % change formula relative to previous value magnitude?
                # Actually, standard % change is (New - Old) / |Old|.
                # Here 'New' is Current Diff, 'Old' is Prev Diff.
                # (Current - Prev) is 'Chng In Direction'.
                # So Chng / |Prev|.
                prev_diff = table_df['Diff. In OI'].shift(-1)
                table_df['Direction of Chng %'] = (table_df['Chng. In Direction'] / prev_diff.abs() * 100).replace([float('inf'), -float('inf')], 0)
                
                # Filter/Rename for Display
                display_cols = ['LTP', 'Chng CE OI', 'Chng PE OI', 'Diff. In OI', 'Direct. Of chng', 'Chng. In Direction', 'Direction of Chng %', 'PCR']
                display_df = table_df[display_cols].copy()
                
                # Rename internal cols to display cols
                display_df = display_df.rename(columns={
                    'Chng CE OI': 'Chng. In Call OI',
                    'Chng PE OI': 'Chng. In Put OI'
                })
                
                # Apply Formatting
                # User uses 1,00,000.00 format (Indian? or just commas with decimals)
                # We'll use standard comma with 2 decimals for now.
                display_df['LTP'] = display_df['LTP'].map('{:,.2f}'.format)
                display_df['Chng. In Call OI'] = display_df['Chng. In Call OI'].map('{:+,.2f}'.format)
                display_df['Chng. In Put OI'] = display_df['Chng. In Put OI'].map('{:+,.2f}'.format)
                display_df['Diff. In OI'] = display_df['Diff. In OI'].map('{:+,.2f}'.format)
                display_df['Chng. In Direction'] = display_df['Chng. In Direction'].fillna(0).map('{:+,.2f}'.format)
                display_df['Direction of Chng %'] = display_df['Direction of Chng %'].fillna(0).map('{:+.2f}%'.format)
                display_df['PCR'] = display_df['PCR'].map('{:.2f}'.format)
                
                # Final Selection & Ordering
                final_table = display_df[['LTP', 'Chng. In Call OI', 'Chng. In Put OI', 'Diff. In OI', 'Direct. Of chng', 'Chng. In Direction', 'Direction of Chng %', 'PCR']]
                
                # Use st.dataframe with styling
                st.dataframe(
                    final_table,
                    use_container_width=True,
                    height=500
                )



    # --- Straddle Analysis Page ---
    if page == "Straddle Analysis":
        st.subheader(f"🧘‍♂️ {symbol} Straddle Analysis")
        
        with st.spinner(f"Fetching Straddle data for {straddle_strike}..."):
            # Get instrument keys
            ce_key = get_option_instrument_key(symbol, straddle_strike, "CE", nse_data, selected_expiry)
            pe_key = get_option_instrument_key(symbol, straddle_strike, "PE", nse_data, selected_expiry)
            
            # Fetch intraday data
            ce_data = get_v3_intraday_data(ce_key, access_token)
            pe_data = get_v3_intraday_data(pe_key, access_token)
            
            if not ce_data.empty and not pe_data.empty:
                # Merge on timestamp to get combined premium
                straddle_df = pd.merge(ce_data, pe_data, on='timestamp', suffixes=('_ce', '_pe'))
                straddle_df['combined_premium'] = straddle_df['close_ce'] + straddle_df['close_pe']
                straddle_df['combined_volume'] = straddle_df['volume_ce'] + straddle_df['volume_pe']
                
                # Calculate Straddle VWAP
                straddle_df['vwap'] = (straddle_df['combined_premium'] * straddle_df['combined_volume']).cumsum() / straddle_df['combined_volume'].cumsum()
                
                # Stats calculation
                curr_price = straddle_df['combined_premium'].iloc[-1]
                open_price = straddle_df['combined_premium'].iloc[0]
                day_high = straddle_df['combined_premium'].max()
                day_low = straddle_df['combined_premium'].min()
                diff = curr_price - open_price
                pct = (diff / open_price * 100) if open_price != 0 else 0
                color = "#00ff7f" if diff >= 0 else "#ff4b4b"
                
                # Display sleek stats above chart
                st.markdown(f"""
                <div class="straddle-header">
                    <div class="stat-box">
                        <div class="stat-label">Current Premium</div>
                        <div class="stat-value">₹{curr_price:,.2f}</div>
                        <div class="stat-delta" style="color: {color};">{diff:+.2f} ({pct:+.2f}%)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Intraday High</div>
                        <div class="stat-value">₹{day_high:,.2f}</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">Intraday Low</div>
                        <div class="stat-value">₹{day_low:,.2f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Plot Straddle Price
                fig = go.Figure()
                
                # Combined Premium Line
                fig.add_trace(go.Scatter(
                    x=straddle_df['timestamp'], y=straddle_df['combined_premium'],
                    mode='lines', name=f'Straddle Price',
                    line=dict(color='#ffd700', width=2.5)
                ))
                
                # VWAP Line
                fig.add_trace(go.Scatter(
                    x=straddle_df['timestamp'], y=straddle_df['vwap'],
                    mode='lines', name='Straddle VWAP',
                    line=dict(color='#ff4b4b', width=1.5, dash='dash')
                ))
                
                fig.update_layout(
                    title=f"Straddle Premium & VWAP: {straddle_strike}",
                    xaxis_title="Time", yaxis_title="Price (₹)",
                    yaxis=dict(autorange=True, fixedrange=False),
                    template="plotly_dark", height=700,
                    margin=dict(l=20, r=20, t=50, b=20),
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Could not fetch data for both legs of the straddle.")

    # --- Strangle Analysis Page ---
    if page == "Strangle Analysis":
        st.subheader(f"🦅 {symbol} Strangle Analysis")
        
        if not ce_strikes and not pe_strikes:
            st.warning("⚠️ Please select at least one CE or PE strike from the sidebar.")
        else:
            with st.spinner(f"Fetching Strangle data for {len(ce_strikes)} CE and {len(pe_strikes)} PE legs..."):
                import concurrent.futures
                
                def fetch_leg_data(strike, opt_type):
                    key = get_option_instrument_key(symbol, strike, opt_type, nse_data, selected_expiry)
                    if not key: return None
                    df = get_v3_intraday_data(key, access_token)
                    if df.empty: return None
                    # We only need close and volume for premium calculation
                    return df[['timestamp', 'close', 'volume']]

                all_leg_data = []
                tasks = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    for s in ce_strikes: tasks.append(executor.submit(fetch_leg_data, s, "CE"))
                    for s in pe_strikes: tasks.append(executor.submit(fetch_leg_data, s, "PE"))
                    
                    for future in concurrent.futures.as_completed(tasks):
                        res = future.result()
                        if res is not None:
                            all_leg_data.append(res)
                
                if not all_leg_data:
                    st.error("❌ No data found for any of the selected strikes.")
                else:
                    # Merge all legs to calculate cumulative premium
                    # Ensure indices match for addition
                    for i in range(len(all_leg_data)):
                        all_leg_data[i] = all_leg_data[i].set_index('timestamp')
                    
                    # Sum all close prices and volumes across timestamps
                    # concat + groupby(level=0).sum() handles missing timestamps in some legs gracefully
                    combined_df = pd.concat(all_leg_data).groupby(level=0).sum().sort_index()
                    
                    # Calculate Combined VWAP
                    combined_df['vwap'] = (combined_df['close'] * combined_df['volume']).cumsum() / combined_df['volume'].cumsum()
                    
                    # Stats calculation
                    curr_price = combined_df['close'].iloc[-1]
                    open_price = combined_df['close'].iloc[0]
                    day_high = combined_df['close'].max()
                    day_low = combined_df['close'].min()
                    diff = curr_price - open_price
                    pct = (diff / open_price * 100) if open_price != 0 else 0
                    color = "#00ff7f" if diff >= 0 else "#ff4b4b"
                    
                    # Display metrics header
                    st.markdown(f"""
                    <div class="straddle-header">
                        <div class="stat-box">
                            <div class="stat-label">Cumulative Premium</div>
                            <div class="stat-value">₹{curr_price:,.2f}</div>
                            <div class="stat-delta" style="color: {color};">{diff:+.2f} ({pct:+.2f}%)</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Strangle High</div>
                            <div class="stat-value">₹{day_high:,.2f}</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-label">Strangle Low</div>
                            <div class="stat-value">₹{day_low:,.2f}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Plot Strangle Price
                    fig = go.Figure()
                    
                    # Cumulative Premium Line
                    fig.add_trace(go.Scatter(
                        x=combined_df.index, y=combined_df['close'],
                        mode='lines', name='Cumulative Premium',
                        line=dict(color='#ffd700', width=2.5)
                    ))
                    
                    # VWAP Line
                    fig.add_trace(go.Scatter(
                        x=combined_df.index, y=combined_df['vwap'],
                        mode='lines', name='Combined VWAP',
                        line=dict(color='#ff4b4b', width=1.5, dash='dash')
                    ))
                    
                    fig.update_layout(
                        title=f"Strangle Analysis: {len(ce_strikes)} CE | {len(pe_strikes)} PE (ATM: {atm})",
                        xaxis_title="Time", yaxis_title="Price (₹)",
                        template="plotly_dark", height=700,
                        margin=dict(l=20, r=20, t=50, b=20),
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig, use_container_width=True)

    # --- Trend Page ---
    if page == "OI Trend Analysis":
        combined_df = pd.DataFrame() # Initialize early
        # Fetching Logic (Restored)
        all_data = [] # List of DataFrames
        
        if strikes and opt_types:
            with st.spinner(f"Fetching data for {len(strikes) * len(opt_types)} contracts..."):
                nse_data = get_cached_nse_data()
                import concurrent.futures
                
                def fetch_contract(strike, opt_type, nse_data_for_fetch):
                    key = get_option_instrument_key(symbol, strike, opt_type, nse_data_for_fetch, selected_expiry)
                    if not key: return None
                    
                    df = get_v3_intraday_data(key, access_token)
                    if df.empty: return None
                    
                    # Prepare DF
                    df['label'] = f"{strike} {opt_type}"
                    # Simulate IV if needed or fetch
                    # fetching IV history for triple view
                    if view_mode == "Triple (Price+IV+OI)":
                        iv_df = get_iv_history(symbol, selected_expiry)
                        if not iv_df.empty:
                            # Merge IV? This is complex. 
                            # For now, let's skip IV merging to keep it simple and fix the NameError first.
                            pass
                    return df
                
                # Fetch Sequentially or Parallel? Parallel is better
                # But to keep it simple and consistent with previous working code (which was likely inside loop):
                for strike in strikes:
                    for opt_type in opt_types:
                        label = f"{strike} {opt_type}"
                        # Check visibility
                        if visible_contracts and label not in visible_contracts:
                            continue
                            
                        df = fetch_contract(strike, opt_type, nse_data)
                        if df is not None:
                            all_data.append(df)
                            
        if not all_data:
            st.warning("No data found for selected contracts.")
        
        # --- Chart Section ---
        if view_mode == "Split (Price+OI)":
            st.subheader("📊 Split View: Price & OI Trend")
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.05,
                subplot_titles=("Options Price (LTP)", "Open Interest (OI)"),
                row_heights=[0.5, 0.5]
            )
        elif view_mode == "Triple (Price+IV+OI)":
            st.subheader("📊 Triple View: Price, IV & OI Trend")
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.04,
                subplot_titles=("Options Price (LTP)", "Implied Volatility (IV)", "Open Interest (OI)"),
                row_heights=[0.33, 0.33, 0.34]
            )
        else:
            fig = go.Figure()
        
        for df in all_data:
            label = df['label'].iloc[0]
            color = '#00ff7f' if "CE" in label else '#ff4b4b'
            
            # Add OI Trace
            oi_trace = go.Scatter(
                x=df['timestamp'], 
                y=df['oi'], 
                mode='lines', 
                name=f"{label} OI",
                line=dict(width=3, color=color if len(strikes) == 1 else None),
                legendgroup=label,
                hovertemplate="<b>%{x}</b><br>OI: %{y:,.0f}<extra></extra>"
            )
            
            if view_mode != "Single (OI)":
                # Add OI to Bottom Pane
                fig.add_trace(oi_trace, row=3 if view_mode == "Triple (Price+IV+OI)" else 2, col=1)
                
                # Add Price to Top Pane
                fig.add_trace(go.Scatter(
                    x=df['timestamp'], 
                    y=df['close'], 
                    mode='lines', 
                    name=f"{label} Price",
                    line=dict(width=2, dash='dot', color=color if len(strikes) == 1 else None),
                    legendgroup=label,
                    showlegend=False,
                    hovertemplate="LTP: ₹%{y:,.2f}<extra></extra>"
                ), row=1, col=1)
                
                # Add IV to Middle Pane (if Triple)
                if view_mode == "Triple (Price+IV+OI)" and 'iv' in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df['timestamp'], 
                        y=df['iv'], 
                        mode='lines', 
                        name=f"{label} IV",
                        line=dict(width=2, dash='dash', color='#00d4ff' if len(strikes) == 1 else None),
                        legendgroup=label,
                        showlegend=False,
                        hovertemplate="IV: %{y:,.2f}%<extra></extra>"
                    ), row=2, col=1)
            else:
                fig.add_trace(oi_trace)

        # Combine Data for Raw Table
        combined_df = pd.concat(all_data) if all_data else pd.DataFrame()

        # Fix Market Hours on X-axis (Optional: Remove if data might span days or different date)
        # fig.update_xaxes(range=[mkt_start, mkt_end]) # Disabled to allow flexible range

        fig.update_layout(
            template="plotly_dark",
            # xaxis_range=[mkt_start, mkt_end], # Removed hardcoded range
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=900 if view_mode == "Triple (Price+IV+OI)" else (800 if view_mode == "Split (Price+OI)" else 600),
            margin=dict(l=20, r=20, t=60, b=20)
        )

        if view_mode != "Single (OI)":
            last_row = 3 if view_mode == "Triple (Price+IV+OI)" else 2
            fig.update_yaxes(title_text="Open Interest", row=last_row, col=1)
            fig.update_xaxes(title_text="Time", row=last_row, col=1)
            if view_mode == "Triple (Price+IV+OI)":
                fig.update_yaxes(title_text="IV (%)", row=2, col=1)
        
        fig.update_xaxes(
            tickformat="%I:%M %p",
            dtick=1800000, # 30 mins
            gridcolor='#333'
        )
        fig.update_yaxes(gridcolor='#333')

        st.plotly_chart(fig, use_container_width=True)

        # --- Data Table Section ---
        if st.checkbox("Show Raw Data Table"):
            st.dataframe(combined_df.pivot(index='timestamp', columns='label', values='oi').sort_index(ascending=False))

    # --- PCR by Strike Page ---
    if page == "PCR by Strike":
        st.subheader(f"📊 PCR by Strike Analysis ({symbol})")
        
        # Inputs
        selected_expiry = st.sidebar.selectbox("Select Expiry", expiries, index=0)
        
        # Custom CSS for Small Grid
        st.markdown("""
        <style>
        .pcr-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 12px;
            padding: 10px 0;
        }
        .pcr-box {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 10px;
            text-align: center;
            transition: transform 0.2s;
        }
        .pcr-box:hover {
            transform: translateY(-3px);
            border-color: rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .pcr-strike {
            font-size: 0.9rem;
            font-weight: 700;
            color: #ccc;
            margin-bottom: 4px;
        }
        .pcr-value {
            font-size: 1.4rem;
            font-weight: 900;
            margin-bottom: 4px;
        }
        .pcr-label {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .bullish { color: #00ff7f; }
        .bearish { color: #ff4b4b; }
        .neutral { color: #888; }
        
        /* Tooltip container */
        .tooltip {
            position: relative;
            display: inline-block;
        }
        .tooltip .tooltiptext {
            visibility: hidden;
            width: 140px;
            background-color: #1e1e1e;
            color: #fff;
            text-align: center;
            border-radius: 6px;
            padding: 8px;
            position: absolute;
            z-index: 1;
            bottom: 125%;
            left: 50%;
            margin-left: -70px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 0.75rem;
            border: 1px solid #333;
            box-shadow: 0 4px 6px rgba(0,0,0,0.4);
        }
        .tooltip:hover .tooltiptext {
            visibility: visible;
            opacity: 1;
        }
        </style>
        """, unsafe_allow_html=True)
        
        from lib.api.option_chain import get_option_chain_dataframe
        
        data_placeholder = st.empty()
        
        # Main Data Loop
        with st.spinner("Calculating PCR Matrix..."):
            df_chain = get_option_chain_dataframe(access_token, INDEX_KEY_MAP[symbol], selected_expiry)
            
            if df_chain is not None and not df_chain.empty:
                # Filter Range (ATM +/- 15 Strikes)
                step = 100 if symbol == "BANKNIFTY" else 50
                range_mask = (df_chain['strike_price'] >= atm - (15 * step)) & (df_chain['strike_price'] <= atm + (15 * step))
                df_view = df_chain[range_mask].copy()
                
                # Render Grid
                html_content = '<div class="pcr-grid">'
                
                for _, row in df_view.iterrows():
                    ce_oi = row['ce_oi'] if row['ce_oi'] > 0 else 1
                    pe_oi = row['pe_oi'] if row['pe_oi'] > 0 else 0
                    
                    pcr = pe_oi / ce_oi
                    
                    # Sentiment Logic
                    if pcr >= 1.0:
                        sentiment = "BULLISH"
                        color_cls = "bullish"
                        desc = "Put Writers Dominating<br>(Support)"
                    else:
                        sentiment = "BEARISH"
                        color_cls = "bearish"
                        desc = "Call Writers Dominating<br>(Resistance)"
                        
                    # ATM Highlight
                    border_style = 'style="border: 1px solid #ffd700; background: rgba(255, 215, 0, 0.05);"' if row['strike_price'] == atm else ''
                    
                    box_html = f"""
                    <div class="pcr-box tooltip" {border_style}>
                        <div class="pcr-strike">{int(row['strike_price'])}</div>
                        <div class="pcr-value {color_cls}">{pcr:.2f}</div>
                        <div class="pcr-label {color_cls}">{sentiment}</div>
                        <span class="tooltiptext">{desc}<br>PE: {int(pe_oi/1000)}k | CE: {int(ce_oi/1000)}k</span>
                    </div>
                    """
                    html_content += box_html
                    
                html_content += "</div>"
                
                data_placeholder.markdown(html_content, unsafe_allow_html=True)
                
                # Add Legend/Help
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.info("**Green (> 1.0)**: Bullish Sentiment. Puts are being sold more aggressively, indicating support.")
                c2.error("**Red (< 1.0)**: Bearish Sentiment. Calls are being sold more aggressively, indicating resistance.")
                c3.warning("**ATM Highlight**: The box with the Gold border indicates the At-The-Money strike.")

if __name__ == "__main__":
    main()
