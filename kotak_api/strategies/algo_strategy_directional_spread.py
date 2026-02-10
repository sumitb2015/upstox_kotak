import os
import sys
import re
import time
import threading
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
from dotenv import load_dotenv
import json
from neo_api_client import NeoAPI
import pyotp

# Terminal encoding
if sys.stdout.encoding != 'UTF-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "algo_strategy_directional_spread.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Directional_Algo")
load_dotenv()

# ================== CONFIGURATION ==================
# Directory Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # c:\Kotakv2_env
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP", "GC6A75CPAEY5WBWTQGMOGKQ2DE")
MPIN = os.getenv("KOTAK_MPIN")

STATE_FILE = os.path.join(DATA_DIR, "algo_strategy_state.json")

# Strategy Parameters
LOT_MULTIPLIER = 1
SUPERTREND_PERIOD = 10
SUPERTREND_MULTIPLIER = 2.0
ADX_PERIOD = 14
ADX_THRESHOLD = 15   # Lowered for high-frequency (was 20)
RSI_PERIOD = 14
EMA_PERIODS = [9, 20, 200]
CHART_INTERVAL = "5m"  # Signal Timeframe
YF_REFRESH_INTERVAL = 60
START_TIME = "09:20"   # Avoid 9:15-9:30 whipsaw
STOP_ENTRY_TIME = "14:30" # Avoid gamma spikes after 2:30 PM
AUTO_EXIT_TIME = "15:20"
DRY_RUN = False  # Set to False for live trading

# Strike Selection
STRIKE_OFFSET = 300  # Offset for Short Leg (OTM)
HEDGE_OFFSET = 200   # Offset for Hedge Leg (Buy) from Short Leg
# Risk Management (Tightened for high-frequency scalping)
INITIAL_SL_PCT = 0.08  # 8% Initial Stop Loss (tighter)
SL_PCT = 0.20          # 20% Stop Loss (with structure break requirement)
TRAIL_SL_PCT = 0.12    # 12% Trailing SL (tighter)
TARGET_PCT = None      # Disabled - ride the trend
PROFIT_TRIGGER_PCT = 0.30  # Trigger Lock at 30% (lowered from 40%)
PROFIT_LOCK_PCT = 0.20     # Lock 20% (lowered from 25%)

# Pyramiding (DISABLED for high-frequency)
PYRAMID_ENABLED = False  # Disable pyramiding for faster capital rotation
PYRAMID_STEP = 25    # Not used when disabled
MAX_PYRAMID_COUNT = 0 # Disabled

# ================== GLOBALS ==================
client = None
master_df = None
data_store = None

# ================== UTILITIES ==================
class DataStore:
    """Thread-safe price cache."""
    def __init__(self):
        self.prices = {}
        self.lock = threading.Lock()
        self.last_activity = time.time()

    def update(self, token, ltp):
        with self.lock:
            # Store dict with ltp and oi
            if str(token) not in self.prices:
                self.prices[str(token)] = {'ltp': 0, 'oi': 0}
            
            # Update provided fields
            if ltp > 0: self.prices[str(token)]['ltp'] = ltp
            self.last_activity = time.time()

    def update_full(self, token, ltp, oi):
        with self.lock:
            if str(token) not in self.prices:
                self.prices[str(token)] = {'ltp': 0, 'oi': 0}
            
            if ltp > 0: self.prices[str(token)]['ltp'] = ltp
            if oi > 0: self.prices[str(token)]['oi'] = oi
            self.last_activity = time.time()

    def get(self, token):
        with self.lock:
            return self.prices.get(str(token), {'ltp': 0, 'oi': 0})

    def get_ltp(self, token):
        return self.get(token).get('ltp', 0)

    def get_oi(self, token):
        return self.get(token).get('oi', 0)

def get_kotak_client():
    global client
    if client: return client
    try:
        client = NeoAPI(consumer_key=CONSUMER_KEY, environment='prod')
        client.totp_login(mobile_number=MOBILE_NUMBER, ucc=UCC, totp=pyotp.TOTP(TOTP).now())
        client.totp_validate(mpin=MPIN)
        print("[SUCCESS] Kotak Neo API Logged In!")
        return client
    except Exception as e:
        print(f"[ERROR] Login Failed: {e}")
        return None

def load_master_data(api_client=None):
    global master_df
    segments = ['nse_fo.csv', 'nse_cm.csv']
    
    if api_client:
        # Check if files exist in DATA_DIR
        missing = [f for f in segments if not os.path.exists(os.path.join(DATA_DIR, f))]
        if missing:
            print("[INFO] Downloading master files...")
            try:
                # API usually downloads to CWD. We might need to move them.
                # For simplicity, let's try downloading and moving or just trust the API writes to CWD and we move them?
                # The NeoAPI `scrip_master` usually writes to current folder. 
                # Let's let it write to CWD, then we move/read.
                # Actually, better to read from DATA_DIR.
                if len(missing) > 0:
                   # This part is tricky if API hardcodes path. Assuming standard behavior:
                   api_client.scrip_master(exchange_segment="nse_fo")
                   api_client.scrip_master(exchange_segment="nse_cm")
                   # Move them to data dir if they appeared in CWD
                   for f in segments:
                       if os.path.exists(f):
                           import shutil
                           shutil.move(f, os.path.join(DATA_DIR, f))
            except: pass

    dfs = []
    for filename in segments:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, low_memory=False)
                df.columns = df.columns.str.strip()
                dfs.append(df)
            except: pass
    
    master_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    print(f"[INFO] Master data: {len(master_df)} rows")
    return master_df

def get_nifty_token():
    if master_df is None or master_df.empty: return None
    try:
        df = master_df[(master_df['pExchSeg'].str.lower() == 'nse_cm') & 
                       (master_df['pTrdSymbol'].str.upper() == 'NIFTY')]
        if not df.empty:
            return int(df.iloc[0]['pSymbol'])
    except: pass
    return None

def get_nearest_expiry():
    """Get nearest weekly expiry from master data."""
    if master_df is None or master_df.empty:
        print("[ERROR] Master data not loaded.")
        return None
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    expiry_dates = set()
    
    for sym in master_df[master_df['pTrdSymbol'].str.match(r'^NIFTY\d{2}[1-9OND]\d{2}', na=False)]['pTrdSymbol']:
        match = re.match(r'^NIFTY(\d{2})([1-9OND])(\d{2})', sym)
        if match:
            try:
                yy = int(match.group(1))
                m_char = match.group(2)
                dd = int(match.group(3))
                m = int(m_char) if m_char.isdigit() else {'O':10, 'N':11, 'D':12}[m_char]
                
                exp_date = datetime(2000 + yy, m, dd)
                if exp_date >= today:
                    expiry_dates.add(exp_date)
            except: pass
    
    if not expiry_dates:
        print("[ERROR] No expiry dates found.")
        return None
    
    sorted_exp = sorted(list(expiry_dates))
    
    # Logic: If nearest expiry is today (0) or tomorrow (1), skip it to avoid Gamma risk
    # User Note: Nifty Expiry is Tuesdays
    nearest = sorted_exp[0]
    days_to_expiry = (nearest - today).days
    
    if days_to_expiry <= 1:
        if len(sorted_exp) > 1:
            print(f"[SMART ROLL] Expiry {nearest.strftime('%Y-%m-%d')} is {days_to_expiry} days away. Skipping to next.")
            nearest = sorted_exp[1]
        else:
            print(f"[WARN] Only one expiry found ({nearest}). Trading despite low DTE.")
            
    print(f"[INFO] Expiry: {nearest.strftime('%Y-%m-%d')} (DTE: {(nearest - today).days})")
    return nearest

def get_option_token(strike, opt_type, expiry):
    """Get option token from master data."""
    if master_df is None or master_df.empty or expiry is None:
        return None, None
    
    m_code = str(expiry.month) if expiry.month <= 9 else {10:'O', 11:'N', 12:'D'}[expiry.month]
    weekly_sym = f"NIFTY{expiry.strftime('%y')}{m_code}{expiry.strftime('%d')}{int(strike)}{opt_type}"
    monthly_sym = f"NIFTY{expiry.strftime('%y%b').upper()}{int(strike)}{opt_type}"
    
    for sym in [weekly_sym, monthly_sym]:
        result = master_df[(master_df['pTrdSymbol'] == sym) & 
                           (master_df['pExchSeg'].str.lower() == 'nse_fo')]
        if not result.empty:
            return int(result.iloc[0]['pSymbol']), sym
    
    return None, None

def get_lot_size():
    if master_df is None or master_df.empty: return 65
    try:
        df = master_df[(master_df['pTrdSymbol'].str.startswith('NIFTY', na=False)) & 
                       (master_df['pExchSeg'].str.lower() == 'nse_fo')]
        if not df.empty:
            for col in ['lLotSize', 'lLotsize', 'pLotSize']:
                if col in df.columns: 
                    return int(df.iloc[0][col])
    except: pass
    return 65

# ================== STRATEGY ==================
class DirectionalStrategy:
    def __init__(self):
        self.client = get_kotak_client()
        if not self.client:
            self.running = False
            return
            
        load_master_data(self.client)
        self.nifty_token = get_nifty_token()
        self.expiry = get_nearest_expiry()
        
        if not self.nifty_token or not self.expiry:
            print("[CRITICAL] Failed to initialize. Exiting.")
            self.running = False
            return
        
        # Indicators
        self.pcr = 0
        self.supertrend_5m = 0
        self.supertrend_dir_5m = 0
        self.supertrend_15m = 0
        self.supertrend_dir_15m = 0
        self.adx_5m = 0
        self.rsi_5m = 0
        self.pdh = 0
        self.pdl = 0
        self.oi_subscribed = False
        self.last_yf_refresh = 0
        self.atr_5m = 0
        self.daily_atr = 0
        
        # Candle tracking for confirmation
        self.prev_candle_open = 0
        self.prev_candle_close = 0
        
        # Position tracking
        self.position = None
        self.running = True
        
        # Reconciliation
        self.reconcile_positions()

        
        print(f"[CONFIG] CONSERVATIVE MODE | 5m+15m Alignment + Candle + RSI | ADX>={ADX_THRESHOLD}")
        print(f"[CONFIG] Initial SL:{INITIAL_SL_PCT*100}% | Trail SL:{TRAIL_SL_PCT*100}%")
        print(f"[ENTRY] Bullish: 5m ST + 15m Bull + RSI<70 + Candle Green + Above/InRange PDL")
        print(f"[ENTRY] Bearish: 5m ST + 15m Bear + RSI>30 + Candle Red + Below/InRange PDH")
        print(f"[EXIT] Pyramiding: {'ENABLED' if PYRAMID_ENABLED else 'DISABLED'} | Target: {'DISABLED' if TARGET_PCT is None else f'{TARGET_PCT*100}%'}")
        
        self.load_state()

    def check_order_status(self, order_id):
        """Check status of a specific order."""
        try:
            print(f"  🔍 Checking status for Order ID: {order_id}")
            report = self.client.order_report()
            
            if not report or not isinstance(report, dict):
                return "Unknown"
                
            data = report.get('data', [])
            for order in data:
                if str(order.get('nOrdNo')) == str(order_id):
                    status = order.get('ordSt', 'Unknown')
                    print(f"  ℹ️ Order {order_id} Status: {status}")
                    return status
            
            return "NotFound"
        except Exception as e:
            print(f"  ❌ Error checking status: {e}")
            return "Error"

    def save_state(self):
        """Save position state to JSON."""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.position, f, indent=4)
        except Exception as e:
            print(f"[ERROR] Save State: {e}")

    def load_state(self):
        """Load position state from JSON."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    self.position = json.load(f)
                if self.position:
                    print(f"[STATE] Restored Position: {self.position.get('type')} Spread")
                    # Re-subscribe to tokens
                    try:
                        short_tok = str(self.position['short']['token'])
                        hedge_tok = str(self.position['hedge']['token'])
                        self.client.subscribe(instrument_tokens=[
                            {"instrument_token": short_tok, "exchange_segment": "nse_fo"},
                            {"instrument_token": hedge_tok, "exchange_segment": "nse_fo"}
                        ], isIndex=False, isDepth=False)
                        print(f"[STATE] Re-subscribed to tokens: {short_tok}, {hedge_tok}")
                    except: pass
            except Exception as e:
                print(f"[ERROR] Load State: {e}")


    def fetch_indicators(self):
        """Fetch yfinance data for 1m and 15m."""
        try:
            # 1. Fetch 5m Data (Signal)
            df_5m = yf.download("^NSEI", period="10d", interval="5m", progress=False)
            if df_5m.empty: return False
            if isinstance(df_5m.columns, pd.MultiIndex): df_5m.columns = df_5m.columns.get_level_values(0)
            df_5m = df_5m.dropna()
            
            st5 = df_5m.ta.supertrend(length=SUPERTREND_PERIOD, multiplier=SUPERTREND_MULTIPLIER)
            if st5 is not None:
                self.supertrend_5m = st5.iloc[-1, 0]
                self.supertrend_dir_5m = st5.iloc[-1, 1]
            
            # ADX on 5m
            adx = df_5m.ta.adx(length=ADX_PERIOD)
            if adx is not None and not adx.empty:
                self.adx_5m = adx[f"ADX_{ADX_PERIOD}"].iloc[-1]
                
            # ATR on 5m (for Pyramiding)
            atr = df_5m.ta.atr(length=14)
            if atr is not None: self.atr_5m = atr.iloc[-1]
            
            # RSI on 5m
            rsi = df_5m.ta.rsi(length=RSI_PERIOD)
            if rsi is not None:
                self.rsi_5m = rsi.iloc[-1]
            
            # Store previous candle for confirmation (use -2 for completed candle)
            if len(df_5m) >= 2:
                self.prev_candle_open = df_5m['Open'].iloc[-2]
                self.prev_candle_close = df_5m['Close'].iloc[-2]

            # 2. Fetch 15m Data (Trend Filter)
            df_15m = yf.download("^NSEI", period="20d", interval="15m", progress=False)
            if not df_15m.empty:
                if isinstance(df_15m.columns, pd.MultiIndex): df_15m.columns = df_15m.columns.get_level_values(0)
                df_15m = df_15m.dropna()
                st15 = df_15m.ta.supertrend(length=SUPERTREND_PERIOD, multiplier=SUPERTREND_MULTIPLIER)
                if st15 is not None:
                    self.supertrend_15m = st15.iloc[-1, 0]
                    self.supertrend_dir_15m = st15.iloc[-1, 1]

            # 3. Fetch Daily Data (PDH/PDL + Daily ATR)
            # Need enough data for ATR(14)
            df_1d = yf.download("^NSEI", period="30d", interval="1d", progress=False)
            if not df_1d.empty:
                if isinstance(df_1d.columns, pd.MultiIndex): df_1d.columns = df_1d.columns.get_level_values(0)
                df_1d = df_1d.dropna()
                self.pdh = df_1d['High'].iloc[-2]  # Previous Day High
                self.pdl = df_1d['Low'].iloc[-2]   # Previous Day Low
                
                # Daily ATR
                atr_d = df_1d.ta.atr(length=14)
                if atr_d is not None: 
                    self.daily_atr = atr_d.iloc[-1]
                    # print(f"[INFO] Daily ATR: {self.daily_atr:.2f}")

            self.last_yf_refresh = time.time()
            
            dir_5m = "BULL" if self.supertrend_dir_5m == 1 else "BEAR"
            dir_15m = "BULL" if self.supertrend_dir_15m == 1 else "BEAR"
            print(f"[YF] 5m:{dir_5m} 15m:{dir_15m} ADX:{self.adx_5m:.1f} RSI:{self.rsi_5m:.1f} PCR:{self.pcr:.2f} | PDH:{self.pdh:.0f} PDL:{self.pdl:.0f} | ATR(D):{self.daily_atr:.0f}")
            return True
        except Exception as e:
            print(f"[ERROR] YFinance: {e}")
            return False


    def on_message(self, message):
        """Handle WebSocket ticks."""
        try:
            ticks = message.get('data', []) if isinstance(message, dict) else message
            if not isinstance(ticks, list): ticks = [ticks]
            
            for tick in ticks:
                if not isinstance(tick, dict): continue
                token = str(tick.get('tk', tick.get('instrument_token', '')))
                ltp = float(tick.get('ltp', 0) or 0)
                oi = int(tick.get('oi', 0) or 0)
                
                if token:
                    data_store.update_full(token, ltp, oi)
        except: pass

    def start_websocket(self):
        self.client.on_message = self.on_message
        self.client.on_error = lambda e: logger.error(f"WS Error: {e}")
        self.client.on_close = lambda m: logger.info("WS Closed")
        self.client.on_open = lambda m: logger.info("WS Opened")
        self.client.subscribe(
            instrument_tokens=[{"instrument_token": str(self.nifty_token), "exchange_segment": "nse_cm"}],
            isIndex=False, isDepth=False
        )
        print(f"[WS] Subscribed to Nifty ({self.nifty_token})")

    def subscribe_oi_chain(self, nifty_price):
        """Subscribe to ATM +/- 5 strikes for OI calc."""
        try:
            atm = round(nifty_price / 50) * 50
            strikes = [atm + (i * 50) for i in range(-5, 6)]
            
            tokens = []
            self.oi_tokens = []
            
            for strike in strikes:
                for o_type in ["CE", "PE"]:
                    tok, _ = get_option_token(strike, o_type, self.expiry)
                    if tok:
                        tokens.append({"instrument_token": str(tok), "exchange_segment": "nse_fo"})
                        self.oi_tokens.append({'token': tok, 'type': o_type})
            
            if tokens:
                self.client.subscribe(instrument_tokens=tokens, isIndex=False, isDepth=False)
                self.oi_subscribed = True
                print(f"[OI] Subscribed to {len(tokens)} option tokens for OI calculation.")
        except Exception as e:
            print(f"[ERROR] OI Sub: {e}")

    def calculate_pcr(self):
        """Calculate PCR from subscribed tokens."""
        if not hasattr(self, 'oi_tokens') or not self.oi_tokens:
            return
            
        ce_oi = 0
        pe_oi = 0
        
        for item in self.oi_tokens:
            oi = data_store.get_oi(item['token'])
            if item['type'] == 'CE':
                ce_oi += oi
            else:
                pe_oi += oi
                
        if ce_oi > 0:
            self.pcr = pe_oi / ce_oi
        else:
            self.pcr = 0
            
    def _calculate_strike_offset(self, multiplier=0.9, min_offset=100):
        """Calculate dynamic strike offset based on ATR."""
        if self.daily_atr > 0:
            return max(round((self.daily_atr * multiplier) / 50) * 50, min_offset)
        return STRIKE_OFFSET
    
    def get_strike(self, nifty_price, option_type):
        """Calculate strike with offset (Dynamic ATR or Fixed)."""
        atm = round(nifty_price / 50) * 50
        offset = self._calculate_strike_offset()
        
        if option_type == "CE":
            return atm + offset  # OTM Call (above ATM)
        else:
            return atm - offset  # OTM Put (below ATM)

    def check_signals(self, price):
        """Check entry/exit signals with Supertrend + PDH/PDL context filter."""
        if self.supertrend_5m == 0: 
            return
        
        # ADX Filter (lowered threshold for more trades)
        if self.adx_5m < ADX_THRESHOLD:
            if not self.position: return
        
        # 5m Supertrend Signal
        is_bullish = price > self.supertrend_5m and self.supertrend_dir_5m == 1
        is_bearish = price < self.supertrend_5m and self.supertrend_dir_5m == -1
        
        if not self.position:
            # Time Filter: Only enter between 09:30 and 14:30
            curr_time = datetime.now().strftime("%H:%M")
            if curr_time < START_TIME or curr_time > STOP_ENTRY_TIME:
                return

            # Entry with PDH/PDL Context Filter + Conservative Confirmation
            if is_bullish:
                # CONSERVATIVE FILTER 1: 15m Trend Alignment
                if self.supertrend_dir_15m != 1:
                    print(f"[SKIP] Bullish signal but 15m trend NOT bullish (15m dir={self.supertrend_dir_15m})")
                    return
                
                # CONSERVATIVE FILTER 2: RSI Extreme Check (avoid exhausted moves)
                if self.rsi_5m > 70:
                    print(f"[SKIP] Bullish signal but RSI overbought ({self.rsi_5m:.1f} > 70)")
                    return
                
                # CONSERVATIVE FILTER 3: Previous Candle Confirmation
                if self.prev_candle_close > 0 and self.prev_candle_open > 0:
                    prev_candle_bullish = self.prev_candle_close > self.prev_candle_open
                    if not prev_candle_bullish:
                        print(f"[SKIP] Bullish signal but previous 5m candle was BEARISH (O:{self.prev_candle_open:.0f} C:{self.prev_candle_close:.0f})")
                        return
                
                # PDH/PDL Context Check for Bullish
                if price < self.pdl and self.pdl > 0:
                    # Bullish signal but below PDL (weak context) - skip
                    print(f"[SKIP] Bullish signal but price {price:.0f} < PDL {self.pdl:.0f} (weak context)")
                    return
                
                # Valid bullish entry - check if breakout or range
                if price > self.pdh and self.pdh > 0:
                    print(f"[SIGNAL] 🚀 BULLISH BREAKOUT (Above PDH {self.pdh:.0f}) + 15m Aligned -> Sell PE Spread")
                else:
                    print(f"[SIGNAL] BULLISH (5m+15m Aligned, Candle Confirmed) -> Sell PE Spread")
                
                self.enter_position(price, "PE")
                
            elif is_bearish:
                # CONSERVATIVE FILTER 1: 15m Trend Alignment
                if self.supertrend_dir_15m != -1:
                    print(f"[SKIP] Bearish signal but 15m trend NOT bearish (15m dir={self.supertrend_dir_15m})")
                    return
                
                # CONSERVATIVE FILTER 2: RSI Extreme Check (avoid exhausted moves)
                if self.rsi_5m < 30:
                    print(f"[SKIP] Bearish signal but RSI oversold ({self.rsi_5m:.1f} < 30)")
                    return
                
                # CONSERVATIVE FILTER 3: Previous Candle Confirmation
                if self.prev_candle_close > 0 and self.prev_candle_open > 0:
                    prev_candle_bearish = self.prev_candle_close < self.prev_candle_open
                    if not prev_candle_bearish:
                        print(f"[SKIP] Bearish signal but previous 5m candle was BULLISH (O:{self.prev_candle_open:.0f} C:{self.prev_candle_close:.0f})")
                        return
                
                # PDH/PDL Context Check for Bearish
                if price > self.pdh and self.pdh > 0:
                    # Bearish signal but above PDH (weak context) - skip
                    print(f"[SKIP] Bearish signal but price {price:.0f} > PDH {self.pdh:.0f} (weak context)")
                    return
                
                # Valid bearish entry - check if breakdown or range
                if price < self.pdl and self.pdl > 0:
                    print(f"[SIGNAL] 🚀 BEARISH BREAKDOWN (Below PDL {self.pdl:.0f}) + 15m Aligned -> Sell CE Spread")
                else:
                    print(f"[SIGNAL] BEARISH (5m+15m Aligned, Candle Confirmed) -> Sell CE Spread")
                
                self.enter_position(price, "CE")
        else:
            # Check for pyramiding (if enabled)
            if PYRAMID_ENABLED:
                self.check_pyramiding(price)
            # Check for exit
            self.check_exit(price, is_bullish, is_bearish)

    def check_pyramiding(self, price):
        """Pyramiding disabled for high-frequency scalping."""
        return  # Early exit - pyramiding disabled for faster capital rotation

    def pyramid_entry(self, underlying_price):
        """Add same quantity to existing position."""
        if not self.position: return
        
        qty = get_lot_size() * LOT_MULTIPLIER # Add base quantity
        short_sym = self.position['short']['symbol']
        hedge_sym = self.position['hedge']['symbol']
        
        # Check prices
        short_price = data_store.get_ltp(self.position['short']['token'])
        hedge_price = data_store.get_ltp(self.position['hedge']['token'])
        
        current_spread = short_price - hedge_price
        
        print(f"  [PYRAMID EXEC] Adding {qty} Qty @ Spread {current_spread:.2f}")

        # Execute Orders
        if self.place_order(hedge_sym, qty, "B"):
            if self.place_order(short_sym, qty, "S"):
                # Update Position State
                old_qty = self.position['qty']
                new_qty = old_qty + qty
                
                # Weighted Average Entry Spread
                old_spread = self.position['entry_spread']
                avg_spread = ((old_spread * old_qty) + (current_spread * qty)) / new_qty
                
                self.position['qty'] = new_qty
                self.position['entry_spread'] = avg_spread
                self.position['best_spread'] = avg_spread  # Reset best to new average
                self.position['pyramid_count'] = self.position.get('pyramid_count', 0) + 1
                self.position['last_scale_price'] = underlying_price # Update reference for next step
                
                self.save_state()
                print(f"  [PYRAMID SUCCESS] Total Qty: {new_qty} | Avg Spread: {avg_spread:.2f}")
            else:
                print(f"[CRITICAL] Pyramid Short Failed! Closing Hedge Buy...")
                self.place_order(hedge_sym, qty, "S") # Cleanup -> Sell back the hedge we just bought

    def enter_position(self, nifty_price, option_type):
        """Enter Credit Spread (Directional)."""
        # 1. Calculate Strikes
        short_strike = self.get_strike(nifty_price, option_type)
        hedge_offset = self._calculate_strike_offset(multiplier=0.5, min_offset=50)
        
        if option_type == "PE":
            hedge_strike = short_strike - hedge_offset  # Lower Put for Hedge
        else:
            hedge_strike = short_strike + hedge_offset  # Higher Call for Hedge
            
        # 2. Get Tokens
        short_tok, short_sym = get_option_token(short_strike, option_type, self.expiry)
        hedge_tok, hedge_sym = get_option_token(hedge_strike, option_type, self.expiry)
        
        if not short_tok or not hedge_tok:
            print(f"[ERROR] Cannot find options: Short {short_strike}, Hedge {hedge_strike}")
            return
        
        qty = get_lot_size() * LOT_MULTIPLIER
        
        # 3. Subscribe & Get Prices
        self.client.subscribe(instrument_tokens=[
            {"instrument_token": str(short_tok), "exchange_segment": "nse_fo"},
            {"instrument_token": str(hedge_tok), "exchange_segment": "nse_fo"}
        ], isIndex=False, isDepth=False)
        time.sleep(1)
        
        short_price = data_store.get_ltp(short_tok)
        hedge_price = data_store.get_ltp(hedge_tok)
        
        # Wait for prices if needed
        if short_price == 0 or hedge_price == 0:
            print(f"[WARN] Waiting for prices... {short_sym}, {hedge_sym}")
            time.sleep(2)
            short_price = data_store.get_ltp(short_tok)
            hedge_price = data_store.get_ltp(hedge_tok)
        
        spread_premium = short_price - hedge_price  # Net Credit
        
        # Validate Credit Spread (must be positive)
        if spread_premium <= 0:
            print(f"[ERROR] Invalid Credit Spread! Short:{short_price:.2f} <= Hedge:{hedge_price:.2f}")
            print(f"  Premium: {spread_premium:.2f} - This would be a DEBIT spread, not credit!")
            print(f"  Aborting entry to avoid losing trade setup.")
            return
        
        # Calculate Initial Risk per Lot
        # Risk = Width - Credit
        strike_width = abs(short_strike - hedge_strike)
        risk_per_lot = strike_width - spread_premium
        initial_total_risk = risk_per_lot * qty
        
        print(f"\n[ENTRY] Credit Spread ({option_type})")
        print(f"  Short: {short_sym} @ {short_price:.2f}")
        print(f"  Hedge: {hedge_sym} @ {hedge_price:.2f}")
        print(f"  Net Credit: {spread_premium:.2f} | Width: {strike_width} | Max Risk: {risk_per_lot:.2f}")

        # 4. Execute Orders (BUY First for Margin Benefit)
        if self.place_order(hedge_sym, qty, "B"):
            if self.place_order(short_sym, qty, "S"):
                self.position = {
                    'type': option_type,
                    'short': {'token': short_tok, 'symbol': short_sym, 'price': short_price},
                    'hedge': {'token': hedge_tok, 'symbol': hedge_sym, 'price': hedge_price},
                    'entry_spread': spread_premium,
                    'best_spread': spread_premium,
                    'spread_width': strike_width,
                    'qty': qty,
                    'initial_risk': initial_total_risk,
                    'entry_time': time.time(),
                    'entry_underlying': nifty_price,
                    'last_scale_price': nifty_price,
                    'locked_profit_amt': 0
                }
                self.save_state()
            else:
                print(f"[CRITICAL] Entry Short Failed! Closing Hedge Buy...")
                self.place_order(hedge_sym, qty, "S") # Cleanup -> Sell back the hedge we just bought

    def check_exit(self, nifty_price, is_bullish, is_bearish):
        """Monitor Spread P&L for Exit."""
        if not self.position: return
        
        short_ltp = data_store.get_ltp(self.position['short']['token'])
        hedge_ltp = data_store.get_ltp(self.position['hedge']['token'])
        
        # Calculate Current Spread Value (Cost to Close)
        # We value it as: (Short LTP - Hedge LTP)
        current_spread = short_ltp - hedge_ltp
        entry_spread = self.position['entry_spread']
        best_spread = self.position.get('best_spread', entry_spread)
        
        # Track best spread (lowest cost to close)
        if current_spread < best_spread:
            self.position['best_spread'] = current_spread
            best_spread = current_spread
            self.save_state()
        
        # Determine if position is in profit
        in_profit = current_spread < entry_spread
        
        # Initial Stop Loss (only when NOT in profit)
        if not in_profit:
            initial_sl_val = entry_spread * (1 + INITIAL_SL_PCT)
            if current_spread >= initial_sl_val:
                print(f"[EXIT] INITIAL SL HIT! Spread: {current_spread:.2f} >= {initial_sl_val:.2f}")
                self.exit_position("INITIAL_SL_HIT")
                return
        
        # Trailing Stop Loss (only when IN profit)
        if in_profit:
            # Protect against negative best_spread edge case
            if best_spread < 0:
                best_spread = 0
                self.position['best_spread'] = 0
                self.save_state()
            
            trail_sl_val = best_spread * (1 + TRAIL_SL_PCT)
            if current_spread >= trail_sl_val:
                print(f"[EXIT] TRAILING SL HIT! Spread: {current_spread:.2f} >= {trail_sl_val:.2f}")
                self.exit_position("TRAIL_SL_HIT")
                return


        # Structure-Based SL (20% expansion + structure break required)
        structure_stop_threshold = entry_spread * (1 + SL_PCT)
        if current_spread >= structure_stop_threshold:
            # Check Structure Violation
            option_type = self.position['type']
            structure_broken = False
            
            # Bullish Trade (Sold PE) -> Structure Broken if Price < Supertrend Support
            if option_type == "PE":
                if nifty_price < self.supertrend_5m:
                    structure_broken = True
            # Bearish Trade (Sold CE) -> Structure Broken if Price > Supertrend Resistance  
            elif option_type == "CE":
                if nifty_price > self.supertrend_5m:
                    structure_broken = True
            
            if structure_broken:
                print(f"[EXIT] SL HIT (Dual Trigger)! Spread:{current_spread:.2f} Structure Broken.")
                self.exit_position("SL_HIT")
                return  # Only return if we actually exit
            else:
                print(f"[HOLD] Spread > SL ({current_spread:.2f}) but Structure Intact. Holding...")
                # Continue to check profit lock and reversal - don't return here


        # Target Logic (Disabled for high-frequency)
        # if TARGET_PCT:
        #     target_val = entry_spread * (1 - TARGET_PCT)
        #     if current_spread <= target_val:
        #         print(f"[EXIT] TARGET HIT! Spread: {current_spread:.2f} <= {target_val:.2f}")
        #         self.exit_position("TARGET_HIT")
        #         return
        
        # Relative Profit Lock (Ratchet)
        # Note: Lock is based on theoretical max profit (spread -> 0), not current profit
        max_profit = entry_spread * self.position['qty']
        current_pnl = (entry_spread - current_spread) * self.position['qty']
        
        # 1. Update Lock?
        current_lock = self.position.get('locked_profit_amt', 0)
        
        # Trigger: When current PnL reaches 40% of max theoretical profit
        # Lock: 25% of max theoretical profit (this is ~62.5% of current profit at trigger)
        if current_pnl >= (max_profit * PROFIT_TRIGGER_PCT):
            lock_val = max_profit * PROFIT_LOCK_PCT
            if lock_val > current_lock:
                self.position['locked_profit_amt'] = lock_val
                print(f"[PROFIT LOCK] Ratcheted UP! Locked: {lock_val:.2f} (Curr PnL: {current_pnl:.2f})")
                self.save_state()
                current_lock = lock_val # Update local var for check below
                
        # 2. Check Lock Exit
        if current_lock > 0:
            if current_pnl < current_lock:
                print(f"[EXIT] PROFIT PROTECTION! PnL {current_pnl:.2f} dropped below Locked {current_lock:.2f}")
                self.exit_position("PROFIT_LOCK")
                return

        # Time-in-Trade Exit (Disabled for high-frequency)
        # Removed - let Trailing SL handle stagnant positions
        
        # Reversal Logic
        option_type = self.position['type']
        if (option_type == "PE" and is_bearish) or (option_type == "CE" and is_bullish):
            print(f"[EXIT] Trend Reversal")
            self.exit_position("REVERSAL")

    def exit_position(self, reason):
        """Close Spread (Buy Short, Sell Hedge)."""
        if not self.position: return
        print(f"[EXIT] Closing Position: {reason}")
        
        # Buy back Short
        success_short = self.place_order(self.position['short']['symbol'], self.position['qty'], "B")
        
        # Sell Hedge
        success_hedge = self.place_order(self.position['hedge']['symbol'], self.position['qty'], "S")
        
        if success_short and success_hedge:
            print("[EXIT] All legs closed successfully.")
            self.position = None
            self.save_state()
        else:
            print(f"[CRITICAL] Exit Failed! Short: {success_short}, Hedge: {success_hedge}")
            print("  ⚠️  Manual intervention required.")

    def place_order(self, symbol, qty, side, product="NRML"):
        """Place Market Order with Verification."""
        if DRY_RUN:
            print(f"  [DRY] {side} {qty} {symbol}")
            return True
            
        try:
            res = self.client.place_order(
                exchange_segment="nse_fo", product=product, price="0",
                order_type="MKT", quantity=str(qty), validity="DAY",
                trading_symbol=symbol, transaction_type=side
            )
            
            if res and isinstance(res, dict) and 'nOrdNo' in res:
                order_id = res['nOrdNo']
                print(f"  [ORDER] {side} {symbol} -> {order_id}")
                
                # Check status
                time.sleep(1)
                status = self.check_order_status(order_id)
                
                if status.lower() in ['complete', 'open', 'pending', 'filled']:
                    return True
                else:
                    print(f"  [ORDER REJECTED] Status: {status}")
                    return False
            else:
                print(f"  [ORDER FAIL] API Response: {res}")
                return False
                
        except Exception as e:
            print(f"  [ORDER FAIL] {e}")
            return False

    def reconcile_positions(self):
        """Check if Broker positions match Internal State."""
        try:
            res = self.client.positions()
            broker_pos = [p for p in res.get('data', []) if int(p.get('netQty', 0)) != 0]
            
            if self.position:
                print(f"[RECON] Internal State: OPEN. Broker Open Positions: {len(broker_pos)}")
            else:
                if len(broker_pos) > 0:
                     print(f"[WARN] Internal State: FLATT, but Broker has {len(broker_pos)} Open Positions!")
                     for p in broker_pos:
                         print(f"  -> {p['trdSym']} : {p['netQty']}")
        except: pass



    def run(self):
        """Main loop."""
        print(f"\n{'='*50}")
        print(f"DIRECTIONAL SUPERTREND STRATEGY (MULTI-TF)")
        print(f"ST(10,2) on 1m & 15m | Offset: {STRIKE_OFFSET}")
        print(f"SL: {SL_PCT*100}% | Trail: {TRAIL_SL_PCT*100}%")
        print(f"Auto-Exit: {AUTO_EXIT_TIME} | DRY_RUN: {DRY_RUN}")
        print(f"{'='*50}\n")
        
        if not self.fetch_indicators():
            print("[ERROR] Failed to fetch indicators.")
            return
        
        self.start_websocket()
        last_display = 0
        
        while self.running:
            try:
                time.sleep(1)
                
                # Refresh indicators
                if time.time() - self.last_yf_refresh > YF_REFRESH_INTERVAL:
                    self.fetch_indicators()
                    
                # Refresh OI Subscription if needed once we have a price
                price_check = data_store.get_ltp(self.nifty_token)
                if price_check > 0 and not self.oi_subscribed:
                    self.subscribe_oi_chain(price_check)

                # Calculate PCR
                self.calculate_pcr()

                price = data_store.get_ltp(self.nifty_token)
                
                if price > 0:
                    self.check_signals(price)
                
                # Display every 5s
                if time.time() - last_display > 5:
                    dir_5m = "🟢 BULL" if self.supertrend_dir_5m == 1 else "🔴 BEAR"
                    dir_15m = "🟢 BULL" if self.supertrend_dir_15m == 1 else "🔴 BEAR"
                    
                    # Build status line
                    curr_time = datetime.now().strftime("%H:%M:%S")
                    print(f"\n{'='*80}")
                    print(f"⏰ {curr_time} | Nifty: {price:.2f}")
                    print(f"📊 Trend: 5m={dir_5m} | 15m={dir_15m} | ADX:{self.adx_5m:.1f} RSI:{self.rsi_5m:.1f} PCR:{self.pcr:.2f}")
                    
                    if self.position:
                        s_ltp = data_store.get_ltp(self.position['short']['token'])
                        h_ltp = data_store.get_ltp(self.position['hedge']['token'])
                        curr_spread = s_ltp - h_ltp
                        entry_spread = self.position['entry_spread']
                        best_spread = self.position.get('best_spread', entry_spread)
                        
                        # Calculate P&L
                        pnl = (entry_spread - curr_spread) * self.position['qty']
                        pnl_pct = ((entry_spread - curr_spread) / entry_spread) * 100 if entry_spread > 0 else 0
                        
                        # Determine position status
                        in_profit = curr_spread < entry_spread
                        status_icon = "✅" if in_profit else "⚠️"
                        
                        # Calculate stop levels
                        if in_profit:
                            stop_level = best_spread * (1 + TRAIL_SL_PCT)
                            stop_type = "TSL"
                        else:
                            stop_level = entry_spread * (1 + INITIAL_SL_PCT)
                            stop_type = "Initial SL"
                        
                        distance_to_stop = curr_spread - stop_level
                        
                        print(f"\n{status_icon} POSITION: {self.position['type']} Spread | Qty: {self.position['qty']}")
                        print(f"   Entry: {entry_spread:.2f} | Current: {curr_spread:.2f} | Best: {best_spread:.2f}")
                        print(f"   P&L: ₹{pnl:.2f} ({pnl_pct:+.1f}%)")
                        print(f"   {stop_type}: {stop_level:.2f} | Distance: {distance_to_stop:.2f}")
                        
                        # Pyramid info
                        pyramid_count = self.position.get('pyramid_count', 0)
                        if pyramid_count > 0:
                            print(f"   🔺 Pyramids: {pyramid_count}/{MAX_PYRAMID_COUNT}")
                        
                        # Locked profit
                        locked = self.position.get('locked_profit_amt', 0)
                        if locked > 0:
                            print(f"   🔒 Locked Profit: ₹{locked:.2f}")
                    else:
                        print(f"\n⏸️  WAITING FOR SIGNAL")
                        
                        # Show entry readiness with PDH/PDL context
                        if self.adx_5m >= ADX_THRESHOLD:
                            print(f"   ✓ ADX Strong ({self.adx_5m:.1f} >= {ADX_THRESHOLD})")
                        else:
                            print(f"   ✗ ADX Weak ({self.adx_5m:.1f} < {ADX_THRESHOLD})")
                        
                        # Show PDH/PDL context
                        if price > 0 and self.pdh > 0 and self.pdl > 0:
                            if price > self.pdh:
                                print(f"   📈 Above PDH ({self.pdh:.0f}) - Favor longs")
                            elif price < self.pdl:
                                print(f"   📉 Below PDL ({self.pdl:.0f}) - Favor shorts")
                            else:
                                range_pct = ((price - self.pdl) / (self.pdh - self.pdl)) * 100
                                print(f"   📊 In Range [{self.pdl:.0f}-{self.pdh:.0f}] ({range_pct:.0f}%)")
                    
                    print(f"{'='*80}")
                    last_display = time.time()
                
                # Reconnect if stale
                if time.time() - data_store.last_activity > 30:
                    print("[WARN] Data stale. Reconnecting...")
                    try: self.client.close()
                    except: pass
                    time.sleep(2)
                    self.start_websocket()

                # Auto-exit
                if datetime.now().strftime("%H:%M") >= AUTO_EXIT_TIME:
                    if self.position: self.exit_position("TIME_EXIT")
                    print("[INFO] Auto-exit time.")
                    break
                    
            except KeyboardInterrupt:
                print("\n[INFO] Interrupted.")
                break
            except Exception as e:
                print(f"[ERROR] Loop: {e}")
                time.sleep(5)

def main():
    global data_store
    data_store = DataStore()
    strategy = DirectionalStrategy()
    if strategy.running:
        strategy.run()

if __name__ == "__main__":
    main()
