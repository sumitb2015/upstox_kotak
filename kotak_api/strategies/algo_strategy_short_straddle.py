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

# ================== CONFIGURATION ==================
# Directory Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "algo_strategy_short_straddle.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Straddle_FSM")

load_dotenv()

CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP", "GC6A75CPAEY5WBWTQGMOGKQ2DE")
MPIN = os.getenv("KOTAK_MPIN")

STATE_FILE = os.path.join(DATA_DIR, "straddle_fsm_state.json")

# Strategy Parameters
LOT_MULTIPLIER = 1  # Base Lots
WINDOW_START = "09:15"
WINDOW_END = "15:30"
HARD_EXIT_TIME = "15:10"

# Regime Filters
ADX_THRESHOLD = 18

# Compression Indicators (replacing VWAP logic)
BB_WIDTH_THRESHOLD = 0.02      # 2% Bollinger Band width
ATR_PERCENTILE_THRESHOLD = 0.50 # Current ATR < 50th percentile (relaxed from 25th)

# Rolling Logic (Institutional)
MAX_ROLLS = 2
ROLL_DRIFT_ATR = 0.4    # Drift from Entry
STRIKE_STEP = 50
STRIKE_CHANGE_MIN = 100 # Minimum significant move
HYSTERESIS_PTS = 30     # Flip-flop protection
ROLL_COOL_DOWN = 30     # Seconds

# Risk
SL_RISK_EXIT_ATR = 0.8  # Widened for rolling (~160 pts)
SL_PREMIUM_EXPLOSION = 1.30 # 30% increase
MAX_CUMULATIVE_LOSS = 1.2   # Hard Stop (120% of Initial Premium)
PROFIT_TRIGGER_DECAY = 0.35 # 35% decay
PROFIT_LOCK_PCT = 0.20 # Lock 20%
TIME_EXIT_MINS = 75    # Per Straddle
MAX_CAMPAIGN_TIME = 180 # Total Strategy Time
TIME_EXIT_PROFIT_MIN = 0.15

# ================== GLOBALS ==================
client = None
master_df = None
data_store = None

# ================== UTILITIES ==================
class DataStore:
    """Thread-safe price cache with staleness detection."""
    def __init__(self):
        self.prices = {}  # {token_str: {'ltp': float, 'oi': int, 'timestamp': float}}
        self.lock = threading.Lock()

    def update_full(self, token, ltp, oi):
        """Update price data with timestamp for staleness detection."""
        with self.lock:
            s_tok = str(token)
            if s_tok not in self.prices:
                self.prices[s_tok] = {'ltp': 0, 'oi': 0, 'timestamp': 0}
            
            if ltp > 0:
                self.prices[s_tok]['ltp'] = ltp
                self.prices[s_tok]['timestamp'] = time.time()
            if oi > 0:
                self.prices[s_tok]['oi'] = oi

    def get_ltp(self, token):
        """Get Last Traded Price for a token."""
        with self.lock:
            return self.prices.get(str(token), {}).get('ltp', 0)
            
    def get_oi(self, token):
        """Get Open Interest for a token."""
        with self.lock:
            return self.prices.get(str(token), {}).get('oi', 0)
    
    def get_data_age(self, token):
        """Get age of data in seconds. Returns -1 if no data."""
        with self.lock:
            data = self.prices.get(str(token), {})
            ts = data.get('timestamp', 0)
            if ts == 0:
                return -1
            return time.time() - ts
    
    def get_position_premium(self, ce_token, pe_token):
        """Atomically get combined premium for CE + PE to prevent race conditions."""
        with self.lock:
            ce_ltp = self.prices.get(str(ce_token), {}).get('ltp', 0)
            pe_ltp = self.prices.get(str(pe_token), {}).get('ltp', 0)
            ce_age = time.time() - self.prices.get(str(ce_token), {}).get('timestamp', 0)
            pe_age = time.time() - self.prices.get(str(pe_token), {}).get('timestamp', 0)
            return ce_ltp, pe_ltp, ce_ltp + pe_ltp, max(ce_age, pe_age)

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
    dfs = []
    
    # Check/Download
    if api_client:
        missing = [f for f in segments if not os.path.exists(os.path.join(DATA_DIR, f))]
        if missing:
            print("[INFO] Downloading master files...")
            try:
                api_client.scrip_master(exchange_segment="nse_fo")
                api_client.scrip_master(exchange_segment="nse_cm")
                for f in segments:
                    if os.path.exists(f):
                        import shutil
                        shutil.move(f, os.path.join(DATA_DIR, f))
            except: pass

    for filename in segments:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, low_memory=False)
                df.columns = df.columns.str.strip()
                dfs.append(df)
            except: pass
    
    master_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    return master_df

def get_lot_size():
    if master_df is None or master_df.empty: return 65 # Default logic
    try:
        df = master_df[(master_df['pTrdSymbol'].str.startswith('NIFTY', na=False)) & 
                       (master_df['pExchSeg'].str.lower() == 'nse_fo')]
        if not df.empty:
            for col in ['lLotSize', 'lLotsize', 'pLotSize']:
                if col in df.columns: return int(df.iloc[0][col])
    except: pass
    return 65

def get_nearest_expiry():
    if master_df is None or master_df.empty: return None
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
                if exp_date >= today: expiry_dates.add(exp_date)
            except: pass
    # Smart Roll?
    # FSM spec implies Day Trading. Standard weekly expiry is likely fine.
    # We will use the base logic: skip if < 1 DTE? Or stick to current.
    # Institutional normally trades current week unless DTE=0.
    if not expiry_dates: return None
    sorted_exp = sorted(list(expiry_dates))
    return sorted_exp[0]

def get_nifty_spot_token():
    """Get Nifty 50 Spot Index Token from master data."""
    if master_df is None or master_df.empty:
        return 26000  # Default Nifty 50 token
    
    try:
        # Look for Nifty 50 in nse_cm segment
        result = master_df[
            (master_df['pTrdSymbol'] == 'Nifty 50') & 
            (master_df['pExchSeg'] == 'nse_cm')
        ]
        if not result.empty:
            token = int(result.iloc[0]['pSymbol'])
            print(f"[INFO] Nifty Spot Token: {token}")
            return token
    except Exception as e:
        print(f"[WARN] Nifty token lookup failed: {e}, using default 26000")
    
    return 26000

def get_option_token(strike, opt_type, expiry):
    # (Same as Directional Strategy)
    if master_df is None or expiry is None: return None, None
    m_code = str(expiry.month) if expiry.month <= 9 else {10:'O', 11:'N', 12:'D'}[expiry.month]
    weekly_sym = f"NIFTY{expiry.strftime('%y')}{m_code}{expiry.strftime('%d')}{int(strike)}{opt_type}"
    monthly_sym = f"NIFTY{expiry.strftime('%y%b').upper()}{int(strike)}{opt_type}"
    for sym in [weekly_sym, monthly_sym]:
        result = master_df[(master_df['pTrdSymbol'] == sym) & (master_df['pExchSeg'].str.lower() == 'nse_fo')]
        if not result.empty: return int(result.iloc[0]['pSymbol']), sym
    return None, None

# ================== FSM STRATEGY ==================
class ShortStraddleStrategy:
    def __init__(self):
        self.state = "INIT"
        self.client = get_kotak_client()
        global data_store
        data_store = DataStore()
        
        if not self.client:
            self.state = "DONE"
            return
            
        load_master_data(self.client)
        
        self.expiry = get_nearest_expiry()
        
        # Validate expiry is not in the past
        if self.expiry and self.expiry < datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
            print(f"[ERROR] Expiry {self.expiry} is in the past! Cannot trade expired options.")
            self.state = "DONE"
            return
        
        self.nifty_token = get_nifty_spot_token()  # Nifty Spot Index
        
        # State Variables
        self.position = {}
        self.today_trade_taken = False
        self.entry_combined_premium = 0
        self.best_combined_premium = 0
        self.locked_profit = 0
        self.roll_count = 0
        
        # Cumulative State
        self.initial_entry_premium = 0  # Baseline for Max Loss
        self.cumulative_pnl = 0         # Realized from closed legs
        self.campaign_start_time = 0    # Total time tracker
        
        # Indicators
        self.adx_5m = 0
        self.adx_slope = 0
        self.atr_5m = 0
        self.daily_atr = 0
        self.vix_pct_change = 0.0
        
        # Compression Indicators (replacing VWAP)
        self.bb_width = 0
        self.atr_5m_percentile_threshold = 0
        
        # Price Tracking
        self.nifty_ltp = 0
        self.entry_nifty = 0
        
        # Retry counters (simple limits to prevent infinite loops)
        self.indicator_failures = 0
        self.entry_retries = 0
        
        self.running = True
        self.load_state()
        
        # Validate configuration
        if LOT_MULTIPLIER <= 0:
            print(f"[ERROR] LOT_MULTIPLIER must be > 0, got {LOT_MULTIPLIER}")
            self.state = "DONE"
            return
        
        print(f"[INIT] Expiry: {self.expiry} | Nifty Token: {self.nifty_token}")

    def save_state(self):
        try:
            data = {
                'state': self.state,
                'position': self.position,
                'today_trade_taken': self.today_trade_taken,
                'locked_profit': self.locked_profit,
                'entry_premium': self.entry_combined_premium,
                'best_premium': self.best_combined_premium,
                'roll_count': self.roll_count,
                'initial_premium': self.initial_entry_premium,
                'cumulative_pnl': self.cumulative_pnl,
                'campaign_start': self.campaign_start_time
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except: pass

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.state = data.get('state', "INIT")
                    self.position = data.get('position', {})
                    self.today_trade_taken = data.get('today_trade_taken', False)
                    self.locked_profit = data.get('locked_profit', 0)
                    self.entry_combined_premium = data.get('entry_premium', 0)
                    self.best_combined_premium = data.get('best_premium', 0)
                    self.roll_count = data.get('roll_count', 0)
                    self.initial_entry_premium = data.get('initial_premium', 0)
                    self.cumulative_pnl = data.get('cumulative_pnl', 0)
                    self.campaign_start_time = data.get('campaign_start', 0)
                    
                    # Migrate old state files
                    if 'entry_fut' in self.position and 'entry_nifty' not in self.position:
                        self.position['entry_nifty'] = self.position['entry_fut']
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")

    def fetch_snapshot(self, tokens):
        """Fallback: Get LTP/VWAP via API for a list of tokens."""
        if not tokens: return
        if not isinstance(tokens, list): tokens = [tokens]
        
        try:
            instrument_tokens = [{"instrument_token": str(t), "exchange_segment": "nse_fo"} for t in tokens]
            res = self.client.quotes(instrument_tokens=instrument_tokens)
            
            # Structure check
            data_list = []
            if isinstance(res, list): data_list = res
            elif isinstance(res, dict) and 'message' in res: 
                if isinstance(res['message'], list): data_list = res['message']
                else: data_list = [res['message']]
            
            for data in data_list:
                tk = int(data.get('instrument_token', data.get('exchange_token', 0)))
                ltp = float(data.get('ltp', 0) or 0)
                
                if tk > 0 and ltp > 0:
                    data_store.update_full(tk, ltp, 0)
                    print(f"[SNAPSHOT] Token {tk} LTP:{ltp}")
            
            if len(data_list) == 0:
                print(f"[WARN] Snapshot returned 0 results for tokens {tokens}")
                    
        except Exception as e:
            print(f"[ERROR] Snapshot: {e}")

    def fetch_indicators(self):
        """Fetch and calculate regime indicators including compression metrics."""
        try:
            print("[DEBUG] Fetching indicators from yfinance...")
            # 1. Fetch Nifty Spot historical data
            df_5m = yf.download("^NSEI", period="5d", interval="5m", progress=False)
            df_1d = yf.download("^NSEI", period="25d", interval="1d", progress=False)
            
            # 2. Fetch India VIX for Stability Check
            df_vix = yf.download("^INDIAVIX", period="2d", interval="1d", progress=False)

            # Fix MultiIndex for all
            for df in [df_5m, df_1d, df_vix]:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
            
            print(f"[DEBUG] Data fetched: 5m={len(df_5m)} rows, Daily={len(df_1d)} rows, VIX={len(df_vix)} rows")

            if not df_5m.empty:
                print(f"[DEBUG] Calculating 5m indicators...")
                # ADX (Trend Strength)
                adx = df_5m.ta.adx(length=14)
                if adx is not None: 
                    self.adx_5m = adx['ADX_14'].iloc[-1]
                    self.adx_slope = adx['ADX_14'].iloc[-1] - adx['ADX_14'].iloc[-2]
                    print(f"[DEBUG] ADX calculated: {self.adx_5m:.1f}")
                else:
                    print("[DEBUG] ADX calculation returned None!")
                
                # Bollinger Band Width (Compression Indicator)
                bbands = df_5m.ta.bbands(length=20, std=2)
                if bbands is not None:
                    print(f"[DEBUG] BBands calculated, columns: {bbands.columns.tolist()}")
                    # Column names have doubled suffix: BBU_20_2.0_2.0
                    bb_upper = bbands['BBU_20_2.0_2.0'].iloc[-1]
                    bb_lower = bbands['BBL_20_2.0_2.0'].iloc[-1]
                    bb_middle = bbands['BBM_20_2.0_2.0'].iloc[-1]
                    if bb_middle > 0:
                        self.bb_width = (bb_upper - bb_lower) / bb_middle
                        print(f"[DEBUG] BB Width: {self.bb_width:.3f}")
                    else:
                        self.bb_width = 999  # Invalid data - blocks entry
                        print(f"[DEBUG] BB middle is 0, setting sentinel")
                else:
                    self.bb_width = 999  # Calculation failed - blocks entry
                    print("[DEBUG] BBands calculation returned None!")
                
                # ATR 5m (for percentile comparison)
                atr_5m_series = df_5m.ta.atr(length=14)
                if atr_5m_series is not None and len(atr_5m_series) >= 4:
                    self.atr_5m = atr_5m_series.iloc[-1]
                    self.atr_5m_percentile_threshold = atr_5m_series.quantile(ATR_PERCENTILE_THRESHOLD)
                    print(f"[DEBUG] ATR 5m: {self.atr_5m:.1f}, {int(ATR_PERCENTILE_THRESHOLD*100)}th percentile: {self.atr_5m_percentile_threshold:.1f}")
                else:
                    self.atr_5m_percentile_threshold = 999  # Insufficient data - blocks entry
                    print(f"[DEBUG] ATR 5m insufficient: series={atr_5m_series is not None}, len={len(atr_5m_series) if atr_5m_series is not None else 0}")
            else:
                print("[DEBUG] df_5m is empty!")
            
            if not df_1d.empty:
                print(f"[DEBUG] Calculating daily ATR...")
                # Daily ATR
                atr_d = df_1d.ta.atr(length=14)
                if atr_d is not None:
                    self.daily_atr = atr_d.iloc[-1]
                    print(f"[DEBUG] Daily ATR: {self.daily_atr:.0f}")
                else:
                    print("[DEBUG] Daily ATR calculation returned None!")
            else:
                print("[DEBUG] df_1d is empty!")
            
            # Calculate VIX Change
            self.vix_pct_change = 0.0
            if not df_vix.empty and len(df_vix) >= 2:
                prev_close = df_vix['Close'].iloc[-2]
                curr_vix = df_vix['Close'].iloc[-1]
                self.vix_pct_change = ((curr_vix - prev_close) / prev_close) * 100
            
            # Print Indicator Summary
            print(f"[YF] ADX:{self.adx_5m:.1f} Slope:{self.adx_slope:.2f} "
                  f"ATR(D):{self.daily_atr:.0f} VIX_Chg:{self.vix_pct_change:.2f}% "
                  f"BB_Width:{self.bb_width:.3f} ATR_5m:{self.atr_5m:.1f} "
                  f"({int(ATR_PERCENTILE_THRESHOLD*100)}th%:{self.atr_5m_percentile_threshold:.1f})")
            return True
        except Exception as e: 
            print(f"[ERROR] Fetch Indicators: {e}")
            return False

    # --- ROLLING LOGIC ---
    def get_atm_strike(self, price):
        """Institutional ATM Selection: Round to nearest 50 deterministically."""
        return int((price + (STRIKE_STEP / 2)) // STRIKE_STEP) * STRIKE_STEP

    def check_roll_conditions(self, nifty_ltp, current_premium):
        """Verify if a roll is structurally justified (Institutional 'AND' Gate)."""
        if self.roll_count >= MAX_ROLLS:
            return False, "Max Rolls Reached"
        
        # 1. Structural Drift Check (Trigger)
        entry_nifty = self.position.get('entry_nifty', 0)
        if entry_nifty == 0:
            return False, "No entry price recorded"
        
        drift = abs(nifty_ltp - entry_nifty)
        if drift < (ROLL_DRIFT_ATR * self.daily_atr):
            return False, "Insufficient Drift"
        
        # 2. Compression Check (BB Width)
        if self.bb_width >= BB_WIDTH_THRESHOLD:
            return False, f"Not Compressed (BB:{self.bb_width:.3f} >= {BB_WIDTH_THRESHOLD})"
        
        # 3. Regime Check (Must be sideways)
        if self.adx_5m >= ADX_THRESHOLD or self.adx_slope > 0:
            return False, f"Trend Active (ADX:{self.adx_5m:.1f} Slope:{self.adx_slope:.2f})"
        
        # 4. Strike Validity Check
        old_atm = self.get_atm_strike(entry_nifty)
        new_atm = self.get_atm_strike(nifty_ltp)
        
        if new_atm == old_atm:
            return False, "Same Strike"
        if abs(new_atm - old_atm) < STRIKE_STEP:
            return False, "Strike change < 50"
        
        # 5. PnL Guard (Don't roll deeply losing trades)
        current_loss = self.entry_combined_premium - current_premium
        if current_loss < 0 and abs(current_loss) > (0.5 * self.initial_entry_premium):
            return False, f"Too Deep Loss ({abs(current_loss):.1f} > 50% of Initial)"
        
        return True, f"Rolling {old_atm} → {new_atm} (Drift {drift:.1f})"

    def roll_position(self, nifty_ltp):
        """Execute the Roll: Exit Old -> Cool Down -> Re-Validate -> Enter New."""
        print("[ROLL] Initiating Straddle Roll...")
        
        # 1. Exit Current Legs
        ce_ltp = data_store.get_ltp(self.position['ce_tok'])
        pe_ltp = data_store.get_ltp(self.position['pe_tok'])
        exit_premium = ce_ltp + pe_ltp
        leg_pnl = self.entry_combined_premium - exit_premium
        
        self.exit_trades()
        self.cumulative_pnl += leg_pnl
        print(f"[ROLL STEP 1] Old Leg Closed. PnL: {leg_pnl:.2f} | Cum PnL: {self.cumulative_pnl:.2f}")
        
        # 2. Cool Down (Regime Validation)
        print(f"[ROLL STEP 2] Cooling Down ({ROLL_COOL_DOWN}s)...")
        time.sleep(ROLL_COOL_DOWN)
        
        # 3. Re-Validate Conditions
        self.fetch_indicators()  # Refresh ADX and BB Width
        current_nifty = data_store.get_ltp(self.nifty_token)
        
        valid = True
        reason = ""
        if self.adx_5m >= ADX_THRESHOLD:
            valid = False; reason = "ADX Spiked"
        elif self.bb_width >= BB_WIDTH_THRESHOLD:
            valid = False; reason = "Compression Lost"
        
        if not valid:
            print(f"[ROLL ABORTED] Regime Invalid after Cool Down: {reason}")
            self.state = "DONE"
            return
        
        # 4. Calculate New ATM
        new_atm = self.get_atm_strike(current_nifty)
        
        # 5. Get New Tokens
        ce_tok, ce_sym = get_option_token(new_atm, "CE", self.expiry)
        pe_tok, pe_sym = get_option_token(new_atm, "PE", self.expiry)
        
        if not (ce_tok and pe_tok):
            print("[ROLL FAIL] Token Lookup Failed.")
            self.state = "DONE"
            return
            
        # 6. Subscribe & Enter with Retry Logic
        self.client.subscribe(
            instrument_tokens=[
                {"instrument_token": str(ce_tok), "exchange_segment": "nse_fo"},
                {"instrument_token": str(pe_tok), "exchange_segment": "nse_fo"}
            ], isIndex=False, isDepth=False
        )
        print("[ROLL STEP 4] Subscribed to new options. Waiting for data...")
        time.sleep(5)  # Increased from 2s to 5s for network latency
        
        # Mandatory Snapshot Fetch (not conditional)
        print("[ROLL STEP 5] Fetching snapshot prices (mandatory)...")
        self.fetch_snapshot([ce_tok, pe_tok])
        time.sleep(1)
        
        # Retry Logic with Exponential Backoff
        max_retries = 3
        retry_count = 0
        ce_ltp = 0
        pe_ltp = 0
        
        while retry_count < max_retries:
            ce_ltp = data_store.get_ltp(ce_tok)
            pe_ltp = data_store.get_ltp(pe_tok)
            
            if ce_ltp > 0 and pe_ltp > 0:
                print(f"[ROLL STEP 6] Prices received: CE={ce_ltp:.2f} PE={pe_ltp:.2f}")
                break
            
            retry_count += 1
            wait_time = retry_count * 2  # 2s, 4s, 6s
            print(f"[ROLL RETRY {retry_count}/{max_retries}] Waiting {wait_time}s for prices...")
            time.sleep(wait_time)
            
            # Re-fetch snapshot on each retry
            self.fetch_snapshot([ce_tok, pe_tok])
        
        if ce_ltp == 0 or pe_ltp == 0:
            print(f"[ROLL FAIL] Could not get valid prices after {max_retries} retries. Aborting.")
            self.state = "DONE"
            return
        
        new_premium = ce_ltp + pe_ltp
        
        qty = get_lot_size() * LOT_MULTIPLIER
        
        print(f"[ROLL EXEC] Selling Straddle {new_atm} | Combined: {new_premium:.2f}")
        if self.enter_trades(ce_sym, pe_sym, qty):
             # Update State - Keep initial_entry_premium constant!
             self.position = {
                 'ce': ce_sym, 'pe': pe_sym, 
                 'ce_tok': ce_tok, 'pe_tok': pe_tok, 
                 'qty': qty, 
                 'entry_time': self.position.get('entry_time', time.time()),
                 'entry_nifty': current_nifty
             }
             self.entry_combined_premium = new_premium
             self.best_combined_premium = new_premium
             # locked_profit from previous leg is now "banked" in cumulative
             # Reset current locked
             self.locked_profit = 0 
             
             self.roll_count += 1
             self.state = "IN_TRADE"
             self.save_state()
             print(f"[ROLL SUCCESS] Count: {self.roll_count}/{MAX_ROLLS}")
        else:
             print("[CRITICAL] Roll Re-Entry Failed. Returning to entry check.")
             self.today_trade_taken = False  # Allow fresh entry
             self.state = "REGIME_CHECK"

    def on_message(self, message):
        """WebSocket message handler with proper error logging."""
        try:
            ticks = message.get('data', [])
            if not isinstance(ticks, list):
                ticks = [ticks]
            
            for tick in ticks:
                tk = str(tick.get('tk', ''))
                ltp = float(tick.get('ltp', 0) or 0)
                oi = int(tick.get('oi', 0) or 0)
                
                if tk and ltp > 0:
                    data_store.update_full(tk, ltp, oi)
                    # Track Nifty LTP
                    if tk == str(self.nifty_token):
                        self.nifty_ltp = ltp
        except Exception as e:
            logger.error(f"WebSocket message error: {e}")

    def start_websocket(self):
        self.client.on_message = self.on_message
        self.client.on_error = lambda e: logger.error(f"WS Error: {e}")
        self.client.on_close = lambda m: logger.info("WS Closed")
        self.client.on_open = lambda m: logger.info("WS Opened")
        
        self.client.subscribe(
            instrument_tokens=[{"instrument_token": str(self.nifty_token), "exchange_segment": "nse_cm"}],
            isIndex=True, isDepth=False
        )
        print(f"[WS] Subscribed to Nifty Spot Index ({self.nifty_token})")

    # --- RISK CHECK METHODS (Extracted for clarity) ---
    def check_hard_stop(self, current_premium):
        """Check if cumulative loss exceeds hard stop threshold."""
        if self.initial_entry_premium == 0:
            return False, ""
        
        current_unrealized = self.entry_combined_premium - current_premium
        total_pnl = self.cumulative_pnl + current_unrealized
        
        if total_pnl <= -(MAX_CUMULATIVE_LOSS * self.initial_entry_premium):
            return True, f"Cumulative Loss {total_pnl:.2f} > {MAX_CUMULATIVE_LOSS}x Initial Premium ({self.initial_entry_premium:.1f})"
        return False, ""
    
    def check_directional_risk(self, nifty_ltp):
        """Check if index price has deviated beyond risk threshold."""
        if self.daily_atr == 0:
            return False, "ATR not available"
        
        entry_nifty = self.position.get('entry_nifty', 0)
        if entry_nifty == 0:
            return False, "No entry price"
        
        deviation = abs(nifty_ltp - entry_nifty)
        threshold = SL_RISK_EXIT_ATR * self.daily_atr
        
        if deviation >= threshold:
            return True, f"Directional Risk: Nifty moved {deviation:.1f} pts (>{threshold:.1f}, {SL_RISK_EXIT_ATR}x ATR)"
        return False, ""
    
    def check_premium_explosion(self, current_premium):
        """Check if premium has exploded beyond acceptable level."""
        if self.entry_combined_premium == 0:
            return False, ""
        
        threshold = self.entry_combined_premium * SL_PREMIUM_EXPLOSION
        if current_premium >= threshold:
            return True, f"Premium Explosion: {current_premium:.2f} >= {threshold:.1f} ({SL_PREMIUM_EXPLOSION}x entry)"
        return False, ""
    
    def check_profit_protection(self, current_premium):
        """Check if locked profit is being violated."""
        if self.locked_profit == 0:
            return False, ""
        
        # For short straddle: profit = entry_premium - current_premium
        # Higher entry - lower current = profit
        current_pnl = self.entry_combined_premium - current_premium
        total_pnl = self.cumulative_pnl + current_pnl
        
        if total_pnl < self.locked_profit:
            return True, f"Profit Protection: Total PnL {total_pnl:.2f} < Locked {self.locked_profit:.2f}"
        return False, ""
    
    def check_time_exit(self):
        """Check if time-based exit is triggered."""
        entry_time = self.position.get('entry_time', 0)
        if entry_time == 0:
            return False, ""
        
        mins_in_trade = (time.time() - entry_time) / 60
        if mins_in_trade >= TIME_EXIT_MINS:
            return True, f"Time Exit: {mins_in_trade:.1f}m in trade (>{TIME_EXIT_MINS}m)"
        return False, ""

    # --- EXECUTION HELPERS ---
    def place_order(self, symbol, qty, side, product="NRML"):
        """Place Market Order."""
        try:
            res = self.client.place_order(
                exchange_segment="nse_fo", product=product, price="0",
                order_type="MKT", quantity=str(qty), validity="DAY",
                trading_symbol=symbol, transaction_type=side
            )
            print(f"  [ORDER] {side} {symbol} -> {res.get('nOrdNo', 'N/A')}")
            return True
        except Exception as e:
            print(f"  [ORDER FAIL] {e}")
            return False

    def enter_trades(self, ce_sym, pe_sym, qty):
        # 1. Sell CE
        if self.place_order(ce_sym, qty, "S"):
            # 2. Sell PE
            if self.place_order(pe_sym, qty, "S"):
                return True
        return False

    def exit_trades(self):
        ce_sym = self.position.get('ce')
        pe_sym = self.position.get('pe')
        qty = self.position.get('qty')
        if ce_sym and pe_sym and qty:
            print("[EXIT] Squaring off CE/PE...")
            self.place_order(ce_sym, qty, "B")
            self.place_order(pe_sym, qty, "B")
            self.position = {}
            self.save_state()

    # --- FSM STATES ---
    def run_fsm(self):
        print(f"[FSM] Starting Loop. Initial State: {self.state}")
        
        while self.running:
            time.sleep(1)
            
            # --- GLOBAL CHECKS ---
            now_str = datetime.now().strftime("%H:%M")
            if now_str >= HARD_EXIT_TIME:
                 if self.state == "IN_TRADE":
                     print("[HARD EXIT] Time Reached.")
                     self.state = "EXIT"
                 elif self.state in ["REGIME_CHECK", "READY_TO_ENTER", "ENTER_STRADDLE"]:
                     print(f"[HARD EXIT] Time Reached in {self.state}. Stopping.")
                     self.state = "DONE"
            
            if self.state == "INIT":
                print("[FSM] >> INIT")
                self.fetch_indicators()
                self.fetch_snapshot([self.nifty_token])  # Get Nifty Spot price
                self.start_websocket()
                self.state = "WAIT_FOR_WINDOW"
                self.save_state()
            
            elif self.state == "WAIT_FOR_WINDOW":
                if now_str >= WINDOW_START and now_str <= WINDOW_END:
                    print(f"\n{'='*70}")
                    print(f"[FSM] >> Window Open ({now_str}). Moving to REGIME_CHECK.")
                    print(f"{'='*70}\n")
                    self.fetch_snapshot([self.nifty_token])  # Refresh before check
                    self.state = "REGIME_CHECK"
                elif now_str > WINDOW_END:
                    print(f"[INFO] Window Closed ({now_str}). Done.")
                    self.state = "DONE"
                else:
                    # Display pre-market information every 30 seconds
                    if int(time.time()) % 30 == 0:
                        nifty_ltp = data_store.get_ltp(self.nifty_token)
                        
                        # If no Nifty price, try fetching
                        if nifty_ltp == 0:
                            print("[INFO] Fetching Nifty price...")
                            self.fetch_snapshot([self.nifty_token])
                            time.sleep(2)
                            nifty_ltp = data_store.get_ltp(self.nifty_token)
                        
                        # Fetch latest indicators for display
                        indicators_ok = self.fetch_indicators()
                        
                        # Calculate time remaining
                        now_dt = datetime.now()
                        start_dt = datetime.strptime(WINDOW_START, "%H:%M").replace(
                            year=now_dt.year, month=now_dt.month, day=now_dt.day
                        )
                        time_remaining = (start_dt - now_dt).total_seconds() / 60
                        
                        print(f"\n{'─'*70}")
                        print(f"⏰ WAITING FOR TRADING WINDOW @ {now_str}")
                        print(f"{'─'*70}")
                        print(f"📊 Market Data:")
                        if nifty_ltp > 0:
                            print(f"   Nifty 50:         {nifty_ltp:.2f}")
                        else:
                            print(f"   Nifty 50:         [Waiting for WebSocket data...]")
                        
                        print(f"\n📈 Indicators (Live):")
                        if indicators_ok and self.daily_atr > 0:
                            print(f"   ADX (5m):         {self.adx_5m:.1f} | Slope: {self.adx_slope:+.2f}")
                            print(f"   BB Width (5m):    {self.bb_width:.3f}")
                            print(f"   ATR 5m:           {self.atr_5m:.1f} | {int(ATR_PERCENTILE_THRESHOLD*100)}th %ile: {self.atr_5m_percentile_threshold:.1f}")
                            print(f"   ATR (Daily):      {self.daily_atr:.0f} pts")
                            print(f"   VIX Change:       {self.vix_pct_change:+.2f}%")
                        else:
                            print(f"   [Fetching from yfinance... Market data may be unavailable pre-9:15]")
                            if self.adx_5m > 0:
                                print(f"   ADX (5m):         {self.adx_5m:.1f} (from yesterday's data)")
                        
                        print(f"\n🕐 Schedule:")
                        print(f"   Window Opens:     {WINDOW_START} ({time_remaining:.0f} mins remaining)")
                        print(f"   Window Closes:    {WINDOW_END}")
                        print(f"   Hard Exit:        {HARD_EXIT_TIME}")
                        print(f"{'─'*70}\n")
            
            elif self.state == "REGIME_CHECK":
                # Fallback snapshot if no Nifty price
                if data_store.get_ltp(self.nifty_token) == 0:
                     self.fetch_snapshot([self.nifty_token])
                
                # Display current Nifty price
                nifty_price = data_store.get_ltp(self.nifty_token)
                print(f"\n[NIFTY] Current Price: {nifty_price:.2f}")
                     
                if self.fetch_indicators():
                    self.indicator_failures = 0  # Reset on success
                    # A. Trend Absence
                    cond_a = self.adx_5m < ADX_THRESHOLD and self.adx_slope <= 0
                    
                    # B. Volatility Compression (BB Width + ATR)
                    cond_b = False
                    if self.bb_width > 0 and self.atr_5m > 0:
                        # BB compression: bands are narrow
                        bb_compressed = self.bb_width < BB_WIDTH_THRESHOLD  # 2%
                        # ATR compression: current ATR is low
                        atr_compressed = self.atr_5m < self.atr_5m_percentile_threshold
                        
                        cond_b = bb_compressed and atr_compressed
                    
                    # C. VIX Spike Check
                    cond_c = self.vix_pct_change < 7.0
                    
                    # Display comprehensive regime analysis
                    print(f"\n{'─'*70}")
                    print(f"REGIME ANALYSIS @ {now_str}")
                    print(f"{'─'*70}")
                    print(f"📊 Indicators:")
                    print(f"   ADX (5m):        {self.adx_5m:.1f} (Threshold: <{ADX_THRESHOLD}) {'✓' if cond_a else '✗'}")
                    print(f"   ADX Slope:       {self.adx_slope:+.2f} (Must be ≤0) {'✓' if self.adx_slope <= 0 else '✗'}")
                    print(f"   BB Width:        {self.bb_width:.3f} (Threshold: <{BB_WIDTH_THRESHOLD}) {'✓' if self.bb_width < BB_WIDTH_THRESHOLD else '✗'}")
                    print(f"   ATR 5m:          {self.atr_5m:.1f} ({int(ATR_PERCENTILE_THRESHOLD*100)}th %ile: {self.atr_5m_percentile_threshold:.1f}) {'✓' if cond_b else '✗'}")
                    print(f"   ATR Daily:       {self.daily_atr:.0f} pts")
                    print(f"   VIX Change:      {self.vix_pct_change:+.2f}% (Threshold: <7%) {'✓' if cond_c else '✗'}")
                    print(f"\n🎯 Entry Decision: ", end="")
                    
                    if cond_a and cond_b and cond_c:
                        print(f"✅ ALL PASS - Entry Allowed\n{'─'*70}\n")
                        print(f"[REGIME] PASS. ADX:{self.adx_5m:.1f} BB_Width:{self.bb_width:.3f} "
                              f"ATR_5m:{self.atr_5m:.1f} ({int(ATR_PERCENTILE_THRESHOLD*100)}th%:{self.atr_5m_percentile_threshold:.1f}) "
                              f"VIX:{self.vix_pct_change:.2f}%")
                        print(f"[FSM] >> REGIME_CHECK -> READY_TO_ENTER")
                        self.state = "READY_TO_ENTER"
                    else:
                        print(f"[REGIME] Fail. ADX:{self.adx_5m:.1f} Slope:{self.adx_slope:.2f} "
                              f"BB_Width:{self.bb_width:.3f} ATR_5m:{self.atr_5m:.1f} "
                              f"({int(ATR_PERCENTILE_THRESHOLD*100)}th%:{self.atr_5m_percentile_threshold:.1f}) VIX:{self.vix_pct_change:.2f}%")
                        print(f"[FSM] >> REGIME_CHECK -> WAIT_FOR_WINDOW (Retry in 10s)")
                        self.state = "WAIT_FOR_WINDOW" 
                        time.sleep(10)
                else:
                    self.indicator_failures += 1
                    if self.indicator_failures >= 5:
                        print("[ERROR] Indicators failed 5 times. Stopping for today.")
                        self.state = "DONE"
                    else:
                        print(f"[WARN] Fetch Indicators Failed ({self.indicator_failures}/5). Retrying...")
                        time.sleep(5)
            
            elif self.state == "READY_TO_ENTER":
                # Check for Major News / Event? (Manual mostly)
                # If we are here, we are good to go
                if self.today_trade_taken and MAX_ROLLS == 0:
                     print("[FSM] Trade already taken today & Max Rolls = 0. Stopping.")
                     self.state = "DONE"
                else:
                     print(f"[FSM] >> READY_TO_ENTER -> ENTER_STRADDLE")
                     self.state = "ENTER_STRADDLE"
            
            elif self.state == "ENTER_STRADDLE":
                # 1. Identify ATM using Nifty Spot
                nifty_ltp = data_store.get_ltp(self.nifty_token)
                if nifty_ltp == 0:
                     print("[WARN] No Nifty Index Price. Waiting...")
                     time.sleep(2)
                     continue
                     
                atm = round(nifty_ltp / 50) * 50
                
                # 2. Get Tokens
                ce_tok, ce_sym = get_option_token(atm, "CE", self.expiry)
                pe_tok, pe_sym = get_option_token(atm, "PE", self.expiry)
                
                # 3. Subscribe Options
                if ce_tok and pe_tok:
                    self.client.subscribe(
                        instrument_tokens=[
                            {"instrument_token": str(ce_tok), "exchange_segment": "nse_fo"},
                            {"instrument_token": str(pe_tok), "exchange_segment": "nse_fo"}
                        ], isIndex=False, isDepth=False
                    )
                    print(f"[ENTRY] ATM: {atm} | Subscription sent.")
                    time.sleep(2) # Wait for ticks
                    
                    # Fallback for Weekend: Fetch Options Snapshots
                    if data_store.get_ltp(ce_tok) == 0:
                        self.fetch_snapshot([ce_tok, pe_tok])
                    
                    ce_ltp = data_store.get_ltp(ce_tok)
                    pe_ltp = data_store.get_ltp(pe_tok)
                    
                    if ce_ltp == 0 or pe_ltp == 0:
                        self.entry_retries += 1
                        if self.entry_retries > 10:
                            print("[ERROR] Could not get prices after 10 retries. Aborting.")
                            self.state = "WAIT_FOR_WINDOW"
                            self.entry_retries = 0
                        else:
                            print(f"[WARN] Incomplete prices: CE={ce_ltp} PE={pe_ltp}. Retry {self.entry_retries}/10...")
                            time.sleep(2)
                        continue
                    
                    self.entry_retries = 0  # Reset on success
                    entry_premium = ce_ltp + pe_ltp
                    qty = get_lot_size() * LOT_MULTIPLIER
                    
                    # Display entry confirmation
                    print(f"\n{'='*70}")
                    print(f"🔔 ENTERING SHORT STRADDLE")
                    print(f"{'='*70}")
                    print(f"Strike (ATM):     {atm}")
                    print(f"Nifty Price:      {nifty_ltp:.2f}")
                    print(f"CE Premium:       {ce_ltp:.2f} ({ce_sym})")
                    print(f"PE Premium:       {pe_ltp:.2f} ({pe_sym})")
                    print(f"Combined Premium: {entry_premium:.2f}")
                    print(f"Quantity:         {qty} lots")
                    print(f"Entry Time:       {datetime.now().strftime('%H:%M:%S')}")
                    print(f"{'='*70}\n")
                    
                    print(f"[EXEC] Selling Straddle {atm} | Combined: {entry_premium:.2f}")
                    if self.enter_trades(ce_sym, pe_sym, qty):
                         self.position = {'ce': ce_sym, 'pe': pe_sym, 'ce_tok': ce_tok, 'pe_tok': pe_tok, 'qty': qty, 'entry_time': time.time(), 'entry_nifty': nifty_ltp}
                         self.entry_combined_premium = entry_premium
                         self.best_combined_premium = entry_premium
                         self.initial_entry_premium = entry_premium # Baseline
                         self.campaign_start_time = time.time()     # Start Timer
                         
                         self.today_trade_taken = True
                         self.state = "IN_TRADE"
                         self.save_state()
                         
                         # Display risk parameters
                         print(f"\n{'─'*70}")
                         print(f"📋 ACTIVE RISK PARAMETERS")
                         print(f"{'─'*70}")
                         print(f"Directional SL:   {SL_RISK_EXIT_ATR}x ATR = {SL_RISK_EXIT_ATR * self.daily_atr:.1f} pts")
                         print(f"Premium Explosion: {SL_PREMIUM_EXPLOSION}x Entry = {entry_premium * SL_PREMIUM_EXPLOSION:.2f}")
                         print(f"Hard Stop Loss:   {MAX_CUMULATIVE_LOSS}x Initial = {entry_premium * MAX_CUMULATIVE_LOSS:.2f}")
                         print(f"Profit Lock:      {PROFIT_TRIGGER_DECAY*100:.0f}% decay → Lock {PROFIT_LOCK_PCT*100:.0f}%")
                         print(f"Max Campaign:     {MAX_CAMPAIGN_TIME} mins")
                         print(f"Time Exit:        {TIME_EXIT_MINS} mins (if profit < {TIME_EXIT_PROFIT_MIN*100:.0f}%)")
                         print(f"Max Rolls:        {MAX_ROLLS}")
                         print(f"{'─'*70}\n")
                    else:
                         print("[CRITICAL] Execution Failed.")
                         self.state = "DONE"

            elif self.state == "IN_TRADE":
                # === DATA VALIDATION ===
                # Verify we have valid position data
                if 'ce_tok' not in self.position or 'pe_tok' not in self.position:
                    print("[ERROR] Invalid position data. Exiting.")
                    self.state = "DONE"
                    continue
                
                # Atomically fetch position premium (prevents race conditions)
                ce_ltp, pe_ltp, current_premium, data_age = data_store.get_position_premium(
                    self.position['ce_tok'], 
                    self.position['pe_tok']
                )
                
                nifty_ltp = data_store.get_ltp(self.nifty_token)
                
                # Data staleness check
                if data_age > 10:  # No update for 10 seconds
                    print(f"[WARN] Stale data: {data_age:.1f}s old. Fetching snapshot...")
                    self.fetch_snapshot([self.position['ce_tok'], self.position['pe_tok'], self.nifty_token])
                
                # Validate non-zero data before processing
                if current_premium == 0 or nifty_ltp == 0:
                    print(f"[WARN] Zero prices detected (Premium:{current_premium} Nifty:{nifty_ltp}). Waiting...")
                    time.sleep(2)
                    continue
                
                # Update best premium tracker
                if current_premium < self.best_combined_premium:
                    self.best_combined_premium = current_premium
                    self.save_state()
                
                # === STATUS OUTPUT (Every 5 seconds for debugging) ===
                if int(time.time()) % 5 == 0:
                    current_pnl = self.entry_combined_premium - current_premium
                    total_pnl = self.cumulative_pnl + current_pnl
                    entry_time = self.position.get('entry_time', 0)
                    if entry_time == 0:
                        entry_time = time.time()  # Fallback if missing
                        self.position['entry_time'] = entry_time
                    mins_in = (time.time() - entry_time) / 60
                    
                    print(f"[STATUS] Premium:{current_premium:.1f} (Entry:{self.entry_combined_premium:.1f}) | "
                          f"PnL:{current_pnl:.1f} (Total:{total_pnl:.1f}) | Nifty:{nifty_ltp:.1f} | Time:{mins_in:.1f}m")

                # === 1. GLOBAL TIME EXIT ===
                campaign_mins = (time.time() - self.campaign_start_time) / 60
                if campaign_mins > MAX_CAMPAIGN_TIME:
                    print(f"[CAMPAIGN EXIT] Max strategy time reached ({campaign_mins:.1f}m > {MAX_CAMPAIGN_TIME}m)")
                    self.state = "EXIT"
                    continue
                
                # === 2. HARD STOP (Cumulative Loss) ===
                hit, msg = self.check_hard_stop(current_premium)
                if hit:
                    print(f"[HARD STOP] {msg}")
                    self.state = "EXIT"
                    continue

                # === 3. ROLLING LOGIC ===
                should_roll, roll_msg = self.check_roll_conditions(nifty_ltp, current_premium)
                if should_roll:
                    print(f"[ROLLING] {roll_msg}")
                    self.roll_position(nifty_ltp)
                    # After rolling, loop back to monitor new position
                    continue

                # === 4. DIRECTIONAL RISK ===
                hit, msg = self.check_directional_risk(nifty_ltp)
                if hit:
                    print(f"[RISK EXIT] {msg}")
                    self.state = "EXIT"
                    continue
                
                # === 5. PREMIUM EXPLOSION ===
                hit, msg = self.check_premium_explosion(current_premium)
                if hit:
                    print(f"[RISK EXIT] {msg}")
                    self.state = "EXIT"
                    continue

                # === 6. PROFIT PROTECTION ===
                # Update locked profit if threshold is met
                if self.entry_combined_premium > 0:
                    decay_pct = (self.entry_combined_premium - current_premium) / self.entry_combined_premium
                else:
                    decay_pct = 0
                if decay_pct >= PROFIT_TRIGGER_DECAY:  # 35% decay
                    lock_amt = self.entry_combined_premium * PROFIT_LOCK_PCT
                    if lock_amt > self.locked_profit:
                        self.locked_profit = lock_amt
                        print(f"[PROFIT LOCK] Locking {lock_amt:.2f} (Decay: {decay_pct:.1%})")
                        self.save_state()
                
                # Check if locked profit is violated
                hit, msg = self.check_profit_protection(current_premium)
                if hit:
                    print(f"[EXIT] {msg}")
                    self.state = "EXIT"
                    continue

                # === 7. TIME EXIT (Stagnation) ===
                hit, msg = self.check_time_exit()
                if hit:
                    current_improvement = (self.entry_combined_premium - current_premium) / self.entry_combined_premium
                    if current_improvement < TIME_EXIT_PROFIT_MIN:
                        print(f"[TIME EXIT] {msg} | Improvement: {current_improvement:.1%} < {TIME_EXIT_PROFIT_MIN:.1%}")
                        self.state = "EXIT"
                        continue

            elif self.state == "EXIT":
                print("[FSM] >> EXIT: Closing all positions...")
                self.exit_trades()
                self.state = "DONE"
                self.save_state()
                
            elif self.state == "DONE":
                print("[FSM] >> DONE: Strategy completed. Exiting loop.")
                self.running = False  # Exit the loop
                break

if __name__ == "__main__":
    strategy = ShortStraddleStrategy()
    strategy.run_fsm()
