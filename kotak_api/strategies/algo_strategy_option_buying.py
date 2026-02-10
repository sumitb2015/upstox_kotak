import os
import sys
import re
import time
import threading
import logging
import json
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import pandas_ta as ta
from dotenv import load_dotenv
from neo_api_client import NeoAPI
import pyotp

# Terminal encoding
if sys.stdout.encoding != 'UTF-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# ================== CONFIGURATION ==================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "algo_strategy_option_buying.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Option_Buying_FSM")

load_dotenv()
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP")
MPIN = os.getenv("KOTAK_MPIN")
STATE_FILE = os.path.join(DATA_DIR, "option_buying_state.json")

# --- STRATEGY PARAMETERS ---
CAPITAL = 100000
RISK_PER_TRADE_PCT = 0.01   # 1%
MAX_DAILY_LOSS_PCT = 0.02   # 2%
MAX_CONSECUTIVE_LOSSES = 3
MAX_TRADES_DAY = 5          # Scalping: Increased from 3 to 5
PYRAMID_MAX_ADDS = 2
HEARTBEAT_SCAN_SEC = 1
HEARTBEAT_MONITOR_SEC = 1
MAX_POSITION_DURATION_MINS = 60     # Scalping: 1 Hour max (was 3 hours)
LOG_FILE_THROTTLE_SEC = 30          # Throttle file logging to avoid bloat

# Risk Management Logic Constants
SL_PCT = 0.20               # 20% Initial SL for Options
PYRAMID_LEVELS = [1.0, 2.0] # R-Milestones to add lots
LOCKED_PROFIT_OFFSET = 0.5  # Lock (CurrentR - 0.5) bits of profit
VOL_COLLAPSE_THRESHOLD = 0.8 # Exit if ATR drops below 80% of peak
EMA_BUFFER_PCT = 0.0005     # 0.05% buffer below EMA9 for trend exit (~12pts)
MAX_CAPITAL_USAGE_PCT = 0.5  # Max 50% of capital in one option trade
INDICATOR_STALE_SEC = 90    # Block trading if no data for 90s

# Scalping Parameters (v7: Aggressive Intraday)
QUICK_EXIT_TARGET_R = 0.5   # Take partial profit at 0.5R
QUICK_EXIT_TIMEOUT_MINS = 30 # Exit if no profit after 30 mins
PARTIAL_EXIT_PCT = 0.5      # Exit 50% of position at quick target
LOSS_COOLDOWN_MINS = 3      # Wait 3 mins after loss before next entry

# Entry Filter Constants (Audit v6: Quality Improvements)
MIN_SPREAD_POINTS = 7       # Scalping: Lowered from 10 to 7 for faster entries
MAX_EXTENSION_PCT = 0.003   # Max 0.3% price extension from EMA9 (~70pts)

# Safety Flags
PAPER_TRADE = True          # If True, no real orders are sent
TESTING_MODE = True         # If True, overrides time filters for testing

if TESTING_MODE:
    TIME_MARKET_OPEN = "00:00"
    TIME_NO_ENTRY_AFTER = "23:55"
    TIME_HARD_EXIT = "23:59"
    TIME_MIN_ENTRY = "00:01" 
else:
    TIME_MARKET_OPEN = "09:30"
    TIME_NO_ENTRY_AFTER = "15:00"
    TIME_HARD_EXIT = "15:20"
    TIME_MIN_ENTRY = "09:45"

# ================== GLOBALS & UTILS ==================
client = None
master_df = None
data_store = None

class DataStore:
    """Thread-safe price cache."""
    def __init__(self):
        self.prices = {}
        self.last_tick_time = 0
        self.lock = threading.Lock()
    def update_full(self, token, ltp, oi=0, vol=0):
        with self.lock:
            s_tok = str(token)
            if s_tok not in self.prices: self.prices[s_tok] = {'ltp': 0, 'oi': 0}
            if ltp > 0: self.prices[s_tok]['ltp'] = ltp
            if oi > 0: self.prices[s_tok]['oi'] = oi
            self.last_tick_time = time.time()
    def get_ltp(self, token):
        with self.lock: return self.prices.get(str(token), {}).get('ltp', 0)
    def get_oi(self, token):
        with self.lock: return self.prices.get(str(token), {}).get('oi', 0)

def get_kotak_client():
    global client
    if client: return client
    try:
        client = NeoAPI(consumer_key=CONSUMER_KEY, environment='prod')
        client.totp_login(mobile_number=MOBILE_NUMBER, ucc=UCC, totp=pyotp.TOTP(TOTP).now())
        client.totp_validate(mpin=MPIN)
        logger.info("[SUCCESS] Kotak Neo API Logged In!")
        return client
    except Exception as e:
        logger.error(f"Login Failed: {e}")
        return None

def load_master_data():
    global master_df
    segments = ['nse_fo.csv', 'nse_cm.csv'] # Need CM for Spot Index
    dfs = []
    for filename in segments:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try: dfs.append(pd.read_csv(path, low_memory=False))
            except: pass
    master_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    if not master_df.empty: master_df.columns = master_df.columns.str.strip()

def get_lot_size():
    if master_df is None or master_df.empty: return 25
    try:
        df = master_df[(master_df['pTrdSymbol'].str.startswith('NIFTY', na=False)) & 
                       (master_df['pExchSeg'].str.lower() == 'nse_fo')]
        if not df.empty:
            for col in ['lLotSize', 'lLotsize', 'pLotSize']:
                if col in df.columns: return int(df.iloc[0][col])
    except: pass
    return 65 # Standard Nifty Lot Size Default

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
    if not expiry_dates: return None
    sorted_exp = sorted(list(expiry_dates))
    return sorted_exp[0]

def get_nifty_tokens():
    """Get Spot Index Token."""
    spot_tok = None
    if master_df is None: return None
    
    # 1. Spot (Nifty 50 Index)
    try:
        # Based on Debug Dump: pTrdSymbol='NIFTY', pExchSeg='nse_cm', pInstType=NaN
        spot = master_df[
            (master_df['pTrdSymbol'] == 'NIFTY') & 
            (master_df['pExchSeg'] == 'nse_cm')
        ]
        
        if not spot.empty: 
            spot_tok = int(spot.iloc[0]['pSymbol'])
            logger.info(f"Spot Token: {spot_tok} (Nifty 50)")
        else:
            # Fallback for some master files where it might be 'Nifty 50'
             spot = master_df[(master_df['pTrdSymbol'] == 'Nifty 50') & (master_df['pExchSeg'] == 'nse_cm')]
             if not spot.empty:
                 spot_tok = int(spot.iloc[0]['pSymbol'])
                 logger.info(f"Spot Token: {spot_tok} (Nifty 50 Fallback)")

    except Exception as e: logger.error(f"Spot Token Error: {e}")

    return spot_tok

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

# ================== EMA MOMENTUM STRATEGY (FSM) ==================
class OptionBuyingStrategy:
    def __init__(self):
        # 1. Setup Infrastructure
        self.client = get_kotak_client()
        if not self.client: return
        load_master_data()
        global data_store
        data_store = DataStore()
        
        self.running = True
        
        # 2. State Variables
        self.expiry = get_nearest_expiry()
        
        # Get Token (Spot Only)
        self.spot_token = get_nifty_tokens()
        
        if not self.spot_token:
             logger.error("Failed to find Nifty Spot Token. Exiting.")
             self.running = False
             return
        
        self.state = "MARKET_OPEN"
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        
        # Position Data Template (Canonical)
        self.default_position = {
            'qty': 0, 'avg_price': 0.0, 'stop_loss': 0.0, 
            'token': None, 'symbol': None,
            'pyramid_count': 0, 'initial_risk_pts': 0.0,
            'peak_ATR': 0.0, 'entry_time': None,
            'locked_profit_pts': 0.0, 'base_qty': 0,
            'entry_price': 0.0,  # Fixed anchor for Locked SL (Audit Fix v3)
            'initial_oi': 0,     # Snapshot for trend analysis
            'trade_dir': None,   # 'CE' or 'PE'
            'partial_exited': False,  # Scalping: Track if 0.5R taken
            'remaining_qty': 0   # Scalping: Qty after partial exit
        }
        self.position = self.default_position.copy()
        
        # Indicators
        self.ema9 = 0
        self.ema20 = 0
        self.adx = 0
        self.atr = 0
        self.atr_sma = 0
        self.spread_slope_positive = False
        self.ema_spread = 0
        
        # Initialize heartbeat to past to ensure immediate first print
        self.last_heartbeat = datetime.now() - timedelta(seconds=HEARTBEAT_SCAN_SEC)
        self.last_yf_download = 0
        self.last_full_download = 0
        self.hist_df = pd.DataFrame()
        self.last_log_time = 0  # Throttle file logging
        self.exit_retry_count = 0  # Track exit order failures
        self.last_exit_time = None  # Loss-only cooldown tracking
        self.last_status_time = 0   # For output display

        self.load_state()
        self.start_websocket()
        
        # --- STRATEGY LOGIC DOCUMENTATION ---
        # 1. ENTRY/TREND: Derived from NIFTY SPOT INDEX (yfinance).
        # 2. EXIT SL/PNL: Derived from OPTION PREMIUM (WebSocket).
        # 3. VOLATILITY EXIT: Derived from NIFTY SPOT ATR (yfinance).
        # This separation is intentional: Spot provides the structural trend, 
        # while Option prices provide the real-world execution risk.
        
        logger.info("STRATEGY INITIALIZED: Option Buying (Long CE/PE)")

    def save_state(self):
        try:
            # Serialize datetime objects
            serializable_pos = self.position.copy()
            if isinstance(serializable_pos.get('entry_time'), datetime):
                serializable_pos['entry_time'] = serializable_pos['entry_time'].isoformat()
            
            data = {
                'state': self.state,
                'trades_today': self.trades_today,
                'daily_pnl': self.daily_pnl,
                'consecutive_losses': self.consecutive_losses,
                'position': serializable_pos,
                'date_str': datetime.now().strftime("%Y-%m-%d") # Save Date for Reset
            }
            with open(STATE_FILE, 'w') as f: json.dump(data, f, indent=4)
        except: pass

    def load_state(self):
        """Restore strategy state and position from disk after a crash/restart."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.state = data.get('state', "MARKET_OPEN")
                    self.trades_today = data.get('trades_today', 0)
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.consecutive_losses = data.get('consecutive_losses', 0)
                    self.consecutive_losses = data.get('consecutive_losses', 0)
                    
                    # Daily Reset Logic
                    saved_date = data.get('date_str', "")
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    
                    if saved_date != today_str or TESTING_MODE:
                         print(f"[RESET] New Day (or Test Mode). Resetting Daily Stats. (Saved: {saved_date}, Today: {today_str})")
                         self.trades_today = 0
                         self.daily_pnl = 0.0
                         self.consecutive_losses = 0
                         self.state = "MARKET_OPEN"
                         self.position = self.default_position.copy()
                         self.save_state()
                         return # Start fresh
                    
                    # Restore Position
                    pos_data = data.get('position', {})
                    if pos_data and pos_data.get('qty', 0) > 0:
                        # Expiry Validation
                        pos_sym = pos_data.get('symbol', '')
                        nearest_exp = self.expiry.strftime('%y%b').upper() if self.expiry else ""
                        if nearest_exp in pos_sym:
                            self.position = pos_data
                            # Deserialize entry_time
                            if isinstance(self.position.get('entry_time'), str):
                                try:
                                    self.position['entry_time'] = datetime.fromisoformat(self.position['entry_time'])
                                except:
                                    self.position['entry_time'] = None

                            # Ensure peak_ATR exists in restored data
                            if 'peak_ATR' not in self.position: self.position['peak_ATR'] = self.atr
                            logger.info(f"[RECOVERY] Restored Position: {self.position.get('symbol')} x{self.position.get('qty')}")
                        else:
                            logger.warning(f"[RECOVERY] Position {pos_sym} appears mismatched. Clearing.")
                            self.position = self.default_position.copy()
            except Exception as e:
                logger.error(f"State restoration failed: {e}")

    def place_order_safe(self, **kwargs):
        """Wrapper for strategy-wide paper/live execution control."""
        if PAPER_TRADE:
            paper_id = f"PAPER_{int(time.time()*100)}"
            logger.warning(f"[PAPER] Simulating {kwargs.get('transaction_type')} order for {kwargs.get('trading_symbol')} Qty:{kwargs.get('quantity')}")
            return {'nOrdNo': paper_id, 'status': 'complete'}
        else:
            try:
                return self.client.place_order(**kwargs)
            except Exception as e:
                logger.error(f"API place_order failure: {e}")
                return None

    # --- WEBSOCKET ---
    # --- WEBSOCKET ---
    def on_message(self, message):
        # Debug: Print raw message
        # print(f"[WS DEBUG] {message}")
        try:
            # Handle nested data structure (Standard Neo API Format)
            if isinstance(message, dict):
                ticks = message.get('data', [])
                if not isinstance(ticks, list): 
                    ticks = [ticks]
            elif isinstance(message, list):
                ticks = message
            else:
                return

            for tick in ticks:
                if not isinstance(tick, dict): continue
                
                tk = str(tick.get('tk', tick.get('instrument_token', '')))
                
                try:
                    ltp_raw = tick.get('ltp', tick.get('last_price', 0))
                    ltp = float(ltp_raw) if ltp_raw else 0.0
                    oi = int(tick.get('oi', 0))
                except:
                    continue
                    
                if tk and ltp > 0: 
                    data_store.update_full(tk, ltp, oi=oi)
        except Exception as e:
            pass # Silently ignore malformed messages to keep connection alive

    def on_error(self, message):
        logger.error(f"WS Error: {message}")

    def on_close(self, message):
        logger.warning(f"WS Connection Closed: {message}. Attempting reconnection...")
        if self.running:
            for attempt in range(3):
                try:
                    # Exponential backoff: 5s, 10s, 15s
                    wait_time = 5 * (attempt + 1)
                    logger.info(f"Reconnection attempt {attempt + 1}/3 in {wait_time}s...")
                    time.sleep(wait_time)
                    
                    if self.start_websocket():
                        logger.info("[SUCCESS] WS Reconnected and Verified.")
                        return
                    else:
                        logger.error(f"Reconnect attempt {attempt + 1} failed verification.")
                except Exception as e:
                    logger.error(f"Reconnect attempt {attempt + 1} error: {e}")
            
            # If we reach here, reconnection failed
            logger.critical("WS Reconnection FAILED after maximum attempts. Forcing exit for safety.")
            if self.position.get('qty', 0) > 0:
                print("\n[CRITICAL] Connection Lost with Open Position. Triggering Emergency Exit.")
                self.state = "POSITION_EXIT"
            else:
                self.state = "MARKET_CLOSE"
                self.running = False

    def start_websocket(self):
        """Starts WS and verifies data flow before returning."""
        try:
            self.client.on_message = self.on_message
            self.client.on_error = self.on_error
            self.client.on_close = self.on_close
            self.client.on_open = lambda m: logger.info("WS Opened")
            
            # 1. Subscribe to Spot (Always)
            tokens = [
                {"instrument_token": str(self.spot_token), "exchange_segment": "nse_cm"}
            ]
            
            # 2. Re-subscribe to active position if exists
            pos_tok = self.position.get('token')
            if pos_tok:
                tokens.append({"instrument_token": str(pos_tok), "exchange_segment": "nse_fo"})
                logger.info(f"Re-subscribing to position token: {pos_tok}")

            self.client.subscribe(instrument_tokens=tokens, isIndex=False, isDepth=False)
            
            # 3. VERIFICATION: Wait 3s and check if prices are flowing
            time.sleep(3)
            test_price = data_store.get_ltp(self.spot_token)
            if test_price > 0:
                logger.info(f"WS Verified: Spot Index Price = {test_price}")
                return True
            else:
                logger.error("WS Verification Failed: No data received for Spot Index.")
                return False
        except Exception as e:
            logger.error(f"start_websocket failure: {e}")
            return False

    def verify_order_fill(self, order_id):
        """Polls order report to confirm fill. Returns (filled_bool, avg_price, fill_qty)."""
        if not order_id: return False, 0.0, 0
        
        for _ in range(10): # Wait up to 5 sec
            try:
                resp = self.client.order_report()
                orders = resp.get('data', []) if isinstance(resp, dict) else resp
                if orders is None: orders = []
                
                for o in orders:
                    if str(o.get('nOrdNo', '')) == str(order_id):
                        st = o.get('ordSt', '').lower()
                        f_qty = int(o.get('flQty', 0))
                        
                        if st in ['complete', 'traded']:
                            avg = float(o.get('avgPrc', 0.0))
                            if avg == 0: avg = float(o.get('avg_price', 0.0))
                            return True, avg, f_qty
                        elif st in ['rejected', 'cancelled']:
                             print(f"[ERR] Order {order_id} Result: {st} - {o.get('rejRsn', '')}")
                             return (f_qty > 0), float(o.get('avgPrc', 0.0)), f_qty
            except: pass
            time.sleep(0.5)
            
        print(f"[WARN] Order {order_id} Verification Timeout.")
        return False, 0.0, 0

    # --- INDICATORS (ON FUTURES) ---
    def update_indicators(self):
        """Fetch historical data for NIFTY SPOT (1m) with 30s throttle and calc indicators."""
        now = time.time()
        
        # 30-second throttle for any update
        if now - self.last_yf_download < 30:
            return True

        try:
            # UNIFIED FETCH: Always fetch 1d (min valid period for 1m data)
            df = yf.download("^NSEI", period="1d", interval="1m", progress=False)
            
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
                
                # Update Cache
                self.hist_df = df
                self.last_yf_download = now
            else:
                # Download failed
                if self.hist_df.empty:
                    logger.error("[CRITICAL] YFinance download failed. No data available.")
                    return False
                else:
                    logger.warning("[FETCH] Update failed. Using cached data.")
                    # Don't update last_yf_download so it retries soon if needed, 
                    # but maybe throttle failure logging? Let's just keep old data.
            
            if self.hist_df.empty: return False
            
            # Robust Deduplication (Index-based) & Validation
            # Ensure Index is Datetime
            if not isinstance(self.hist_df.index, pd.DatetimeIndex):
                self.hist_df.index = pd.to_datetime(self.hist_df.index)
            
            # Remove duplicate timestamps (keep last updated)
            self.hist_df = self.hist_df[~self.hist_df.index.duplicated(keep='last')]
            
            # Use cached or fresh data
            df = self.hist_df.copy()
            
            # Validation: Ensure 'Close' exists
            if 'Close' not in df.columns:
                logger.error(f"[ERR] 'Close' column missing in data. Columns: {df.columns}. Clearing Cache.")
                self.hist_df = pd.DataFrame()
                return False
            df['EMA9'] = ta.ema(df['Close'], length=9)
            df['EMA20'] = ta.ema(df['Close'], length=20)
            df['ADX'] = ta.adx(df['High'], df['Low'], df['Close'], length=14)['ADX_14']
            df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            
            # Spread & ATR SMA
            df['Spread'] = df['EMA9'] - df['EMA20']
            df['Spread_Prev'] = df['Spread'].shift(1)
            df['ATR_SMA'] = ta.sma(df['ATR'], length=5)
            
            # Latest (Use previous value if NaN to avoid signal flicker)
            row = df.iloc[-1]
            if not pd.isna(row['EMA9']): self.ema9 = float(row['EMA9'])
            if not pd.isna(row['EMA20']): self.ema20 = float(row['EMA20'])
            if not pd.isna(row['ADX']): self.adx = float(row['ADX'])
            if not pd.isna(row['ATR']): self.atr = float(row['ATR'])
            if not pd.isna(row['ATR_SMA']): self.atr_sma = float(row['ATR_SMA'])
            if not pd.isna(row['Spread']): self.ema_spread = float(row['Spread'])
            
            # Check Slope (Current vs Prev valid)
            spread_curr = float(row['Spread'])
            spread_prev = float(row['Spread_Prev']) if not pd.isna(row['Spread_Prev']) else spread_curr
            self.spread_slope_positive = (spread_curr > spread_prev)
            
            return True
            
        except Exception as e:
            logger.error(f"Update Indicators Failed: {e}")
            return False
    
    def print_status_update(self, spot_ltp):
        """Print independent periodic status."""
        if time.time() - self.last_status_time < 5:  # Print every 5 seconds
            return

        trend_str = "BULLISH" if (self.ema9 > self.ema20) else "BEARISH"
        is_stale = (time.time() - self.last_yf_download) > INDICATOR_STALE_SEC
        stale_tag = " [STALE]" if is_stale else ""
            
        status_msg = (f"[MONITORING{stale_tag}] Nifty: {spot_ltp:.2f} | "
                      f"Trend: {trend_str} (Diff: {self.ema_spread:.1f}) | "
                      f"EMA9: {self.ema9:.1f} EMA20: {self.ema20:.1f} | "
                      f"ADX: {self.adx:.1f} | ATR: {self.atr:.1f}")
            
        print(status_msg)
        
        if time.time() - self.last_log_time > LOG_FILE_THROTTLE_SEC:
            logger.info(status_msg)
            self.last_log_time = time.time()
            
        self.last_status_time = time.time()

    # --- FSM LOGIC ---
    def run(self):
        print(f"\n[FSM] STARTING STRATEGY LOOP | State: {self.state}")
        while self.running:
            try:
                self.process_state()
            except Exception as e:
                logger.error(f"FSM Error: {e}")
            time.sleep(1) # 1-second tick for live updates

    def process_state(self):
        now = datetime.now()
        cur_time = now.strftime("%H:%M")
        
        # 1. MARKET_OPEN
        if self.state == "MARKET_OPEN":
            if cur_time >= "09:00" and not getattr(self, 'master_data_loaded', False):
                load_master_data() # Refresh master data daily
                self.master_data_loaded = True
                print("[FSM] Master Data Refreshed for the day.")
            if cur_time >= TIME_MARKET_OPEN:
                print(f"[FSM] >> MARKET_OPEN -> NO_POSITION")
                self.state = "NO_POSITION"
                self.save_state()
        
        # Data Flow Watchdog
        if self.state in ["NO_POSITION", "MONITORING"]:
            if data_store.last_tick_time > 0 and (time.time() - data_store.last_tick_time) > 60:
                logger.critical("DATA WATCHDOG: No ticks received for 60s! Connection might be stale.")
                if self.position.get('qty', 0) > 0:
                    self.state = "POSITION_EXIT"
                else:
                    self.start_websocket() # Attempt soft reset
                return
        
        # 2. NO_POSITION (Scan)
        elif self.state == "NO_POSITION":
            if cur_time > TIME_NO_ENTRY_AFTER:
                self.state = "MARKET_CLOSE"
                return

            if self.trades_today >= MAX_TRADES_DAY:
                print("[FSM] Max trades reached. Done for day.")
                self.state = "MARKET_CLOSE"
                return
            
            # Daily Loss Protection
            max_loss_amt = CAPITAL * MAX_DAILY_LOSS_PCT
            if self.daily_pnl <= -max_loss_amt:
                print(f"[FSM] Daily Loss Limit Reached ({self.daily_pnl:.2f}). Stopping for the day.")
                self.state = "MARKET_CLOSE"
                return

            # Consecutive Loss Protection
            if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                print(f"[FSM] {MAX_CONSECUTIVE_LOSSES} Consecutive Losses. Stopping for the day.")
                self.state = "MARKET_CLOSE"
                return

            # Fetch Spot Immediately for Display
            spot_ltp = data_store.get_ltp(self.spot_token)

            # --- LOSS COOLDOWN CHECK (v8: Prevent Revenge Trading) ---
            if self.last_exit_time:
                mins_since_loss = (datetime.now() - self.last_exit_time).total_seconds() / 60
                if mins_since_loss < LOSS_COOLDOWN_MINS:
                    cooldown_remaining = LOSS_COOLDOWN_MINS - mins_since_loss
                    if int(time.time()) % 10 == 0:  # Print every 10 seconds
                        print(f"[COOLDOWN] Waiting {cooldown_remaining:.1f} mins after loss before next entry...")
                    return  # Skip scanning during cooldown

            # --- HEARTBEAT & STATUS MONITORING ---
            self.print_status_update(spot_ltp)
            
            # Update heartbeat timestamp
            self.last_heartbeat = datetime.now()

            # Check time filter (status was already printed above)
            if cur_time < TIME_MIN_ENTRY: 
                return

            # Check data availability (status was already printed above)
            if spot_ltp <= 0:
                return

            self.update_indicators()


            
            # ===== ENTRY LOGIC (Audit v6: Improved Filters) =====
            
            # Condition 1: Trend Direction
            is_bullish = (self.ema9 > self.ema20)
            is_bearish = (self.ema9 < self.ema20)
            
            # Condition 2: Price Strength (Simplified - redundant check removed)
            bull_strength = (spot_ltp > self.ema9)  # If EMA9>EMA20 and Spot>EMA9, then Spot>EMA20 is implied
            bear_strength = (spot_ltp < self.ema9)
            
            # Condition 3: Momentum Acceleration with Magnitude Filter
            # Bullish: Spread must be positive AND expanding AND meaningful (>10pts)
            # Bearish: Spread must be negative AND contracting AND meaningful (<-10pts)
            cond_accel_bull = (self.ema_spread > MIN_SPREAD_POINTS) and self.spread_slope_positive
            cond_accel_bear = (self.ema_spread < -MIN_SPREAD_POINTS) and (not self.spread_slope_positive)
            
            # Condition 4: Trend Strength (Lowered from 25 to 20 for more entries)
            # ADX > 20 = Moderate to strong trend (tradeable)
            # ADX > 25 = Strong trend (previous, too restrictive)
            cond_trend_strength = (self.adx > 20)
            
            # Condition 5: Price Extension Guard (NEW - prevent late entries)
            # Don't enter if price has already moved >0.3% from EMA9 (~70pts at 23,500)
            price_extension_bull = ((spot_ltp - self.ema9) / self.ema9) if self.ema9 > 0 else 0
            price_extension_bear = ((self.ema9 - spot_ltp) / self.ema9) if self.ema9 > 0 else 0
            
            not_overextended_bull = (price_extension_bull < MAX_EXTENSION_PCT)
            not_overextended_bear = (price_extension_bear < MAX_EXTENSION_PCT)
            
            # SIGNAL GENERATION (Removed ATR volatility filter - let ADX handle trend quality)
            if is_bullish and bull_strength and cond_accel_bull and cond_trend_strength and not_overextended_bull:
                print(f"\n[SIGNAL] BULLISH ENTRY! Spread:{self.ema_spread:.1f}pts | ADX:{self.adx:.1f} | Ext:{price_extension_bull*100:.2f}%")
                self.position['trade_dir'] = 'CE'
                self.state = "POSITION_OPEN"
                
            elif is_bearish and bear_strength and cond_accel_bear and cond_trend_strength and not_overextended_bear:
                print(f"\n[SIGNAL] BEARISH ENTRY! Spread:{self.ema_spread:.1f}pts | ADX:{self.adx:.1f} | Ext:{price_extension_bear*100:.2f}%")
                self.position['trade_dir'] = 'PE'
                self.state = "POSITION_OPEN"
                
            else:
                 pass
        
        # 3. POSITION_OPEN (Execute)
        elif self.state == "POSITION_OPEN":
            # Select Strike from SPOT
            spot_ltp = data_store.get_ltp(self.spot_token)
            if spot_ltp == 0: return # Wait for tick
            
            # Strike Selection: ATM (Round Spot to nearest 50)
            atm_strike = round(spot_ltp / 50) * 50
            
            trade_dir = self.position.get('trade_dir', 'CE') # Default CE for safety
            if not trade_dir: trade_dir = 'CE'
            
            # Buying CE or PE
            opt_tok, opt_sym = get_option_token(atm_strike, trade_dir, self.expiry)
            
            if not opt_tok:
                logger.error(f"[SIGNAL] Option contract not found for {atm_strike} {trade_dir}. Skipping entry.")
                self.state = "NO_POSITION"
                return
            
            # Calc Size
            # SL = 1.5 * ATR (Futures ATR projected to Option approx delta 0.5) implies ~0.75 ATR on Option
            # Or simply 20% of Premium. 
            # Let's get Option LTP first.
            try:
                self.client.subscribe(instrument_tokens=[{"instrument_token": str(opt_tok), "exchange_segment": "nse_fo"}])
            except Exception as e:
                logger.error(f"[ERR] WebSocket subscription failed for {opt_sym}: {e}")
                self.state = "NO_POSITION"
                return
            
            # Polling for data
            opt_ltp = 0
            for _ in range(10): # Wait up to 5 sec
                time.sleep(0.5)
                opt_ltp = data_store.get_ltp(opt_tok)
                if opt_ltp > 0: break
            
            if opt_ltp == 0:
                print("[ERR] Option Price 0")
                self.state = "NO_POSITION"
                return

            sl_pts = opt_ltp * 0.20 # 20% SL
            risk_amt = CAPITAL * RISK_PER_TRADE_PCT # 1000
            qty = int(risk_amt / sl_pts)
            
            # Capital Usage Guard
            max_qty_by_cap = int((CAPITAL * MAX_CAPITAL_USAGE_PCT) / opt_ltp)
            qty = min(qty, max_qty_by_cap)
            
            # Lot Rounding
            lot = get_lot_size()
            # Audit Fix v4: Risk Safety Guard
            if qty < lot:
                logger.warning(f"[SIGNAL] Calculated Qty {qty} is less than minimum lot {lot}. Risk too small. Skipping trade.")
                self.state = "NO_POSITION"
                return
            qty = (qty // lot) * lot
            if qty <= 0: return # Final check
            
            print(f"[EXEC] Buying {opt_sym} | Qty:{qty} @ {opt_ltp} | SL: {opt_ltp - sl_pts:.1f}")
            
            # REAL ORDER PLACEMENT
            try:
                resp = self.place_order_safe( # Changed to place_order_safe
                    exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                    quantity=str(qty), validity="DAY", trading_symbol=opt_sym,
                    transaction_type="B", amo="NO"
                )
                
                if not resp or not isinstance(resp, dict):
                    print(f"[ERR] Order Placement Failed (Invalid Response): {resp}")
                    self.state = "NO_POSITION"
                    return

                ord_id = resp.get('nOrdNo')
                if not ord_id:
                    print(f"[ERR] Order Placement Failed (No ID): {resp}")
                    self.state = "NO_POSITION"
                    return

                print(f"[ORDER] ID: {ord_id}")
                
                # VERIFY FILL
                filled, fill_price, fill_qty = self.verify_order_fill(ord_id)
                
                if filled or fill_qty > 0:
                    # Use Actual Fill Price
                    if fill_price > 0: opt_ltp = fill_price
                    
                    self.position['token'] = opt_tok
                    self.position['symbol'] = opt_sym
                    self.position['qty'] = fill_qty 
                    self.position['base_qty'] = fill_qty 
                    self.position['avg_price'] = opt_ltp
                    self.position['entry_price'] = opt_ltp # Anchor for SL (Audit v3)
                    self.position['stop_loss'] = opt_ltp - sl_pts
                    self.position['initial_oi'] = data_store.get_oi(opt_tok)
                    
                    # Fixed Risk Baseline (Audit Fix)
                    self.position['initial_risk_pts'] = sl_pts 
                    self.position['pyramid_count'] = 0
                    
                    self.position['peak_ATR'] = self.atr
                    self.position['entry_time'] = datetime.now()
                    
                    print(f"[SUCCESS] Position Opened x{fill_qty} @ {opt_ltp}")
                    self.state = "MONITORING" 
                    self.save_state()
                else:
                    print("[FAIL] Order not filled. Resetting.")
                    self.state = "NO_POSITION"
                    return

            except Exception as e:
                logger.error(f"Order Failed: {e}")
                self.state = "NO_POSITION"
                return

        # 4. MONITORING (Unified)
        elif self.state == "MONITORING":
            # Check Time Exit
            if cur_time >= TIME_HARD_EXIT:
                print("\n[EXIT] Time Stop.")
                self.state = "POSITION_EXIT"
                return

            # Update indicators during monitoring to catch trend reversals
            self.update_indicators()

            term_ltp = data_store.get_ltp(self.position['token'])
            spot_ltp = data_store.get_ltp(self.spot_token)
            if term_ltp == 0 or spot_ltp == 0: 
                return  # Wait for ticks

            # Update Peak ATR
            if 'peak_ATR' not in self.position: 
                self.position['peak_ATR'] = self.atr
            else: 
                self.position['peak_ATR'] = max(self.position['peak_ATR'], self.atr)

            # PnL Calc
            pnl_pts = term_ltp - self.position['avg_price']
            
            risk_val = self.position.get('initial_risk_pts', 0)
            if risk_val <= 0: 
                logger.error(f"[CRITICAL] initial_risk_pts is {risk_val}. Forcing exit for safety.")
                self.state = "POSITION_EXIT"
                return
            current_R = pnl_pts / risk_val

            # --- HEARTBEAT (IMPROVED) ---
            elapsed_seconds = (datetime.now() - self.last_heartbeat).total_seconds()
            if elapsed_seconds >= HEARTBEAT_MONITOR_SEC:
                pnl_val = pnl_pts * self.position['qty']
                
                # Calc Duration info
                entry_time = self.position.get('entry_time')
                dur_str = ""
                if entry_time:
                    dur_mins = int((datetime.now() - entry_time).total_seconds() / 60)
                    dur_str = f" | Dur:{dur_mins}m"
                
                # Calc OI Trend
                curr_oi = data_store.get_oi(self.position['token'])
                oi_delta_pct = 0.0
                if self.position.get('initial_oi', 0) > 0:
                    oi_delta_pct = ((curr_oi - self.position['initial_oi']) / self.position['initial_oi']) * 100

                status_msg = (f"[LIVE] {self.position['symbol']} | "
                              f"Qty:{self.position['qty']} @ {self.position['avg_price']:.1f} | "
                              f"LTP:{term_ltp:.1f} | PnL:{pnl_val:+.0f} ({current_R:+.2f}R) | "
                              f"SL:{self.position['stop_loss']:.1f} | "
                              f"OI:{curr_oi:,} ({oi_delta_pct:+.1f}%) | "
                              f"Spot:{spot_ltp:.0f} | "
                              f"Trend:{'BULL' if spot_ltp > self.ema9 else 'BEAR' if spot_ltp < self.ema9 else 'NEUTRAL'}")

                if int(time.time()) % 10 == 0:
                     print(f"\n{status_msg}")
                else:
                     print(f"\r{status_msg}   ", end="", flush=True)

                if time.time() - self.last_log_time > LOG_FILE_THROTTLE_SEC:
                    logger.info(status_msg)
                    self.last_log_time = time.time()

                self.last_heartbeat = datetime.now()

            # --- SCALPING EXIT LOGIC (v7: Quick Profit Taking) ---
            
            # Scalping Rule 1: Partial Exit at 0.5R (Take quick profit)
            if current_R >= QUICK_EXIT_TARGET_R and not self.position.get('partial_exited', False):
                # Retry limit: prevent spam if order keeps failing
                if not hasattr(self, 'partial_exit_attempts'):
                    self.partial_exit_attempts = 0
                    
                if self.partial_exit_attempts >= 3:
                    logger.warning("[SCALPING] Partial exit failed 3 times. Skipping further attempts.")
                    self.position['partial_exited'] = True  # Don't retry
                    self.save_state()
                else:
                    # Calculate partial exit quantity (50% of current position)
                    partial_qty = int(self.position['qty'] * PARTIAL_EXIT_PCT)
                    lot = get_lot_size()
                    partial_qty = (partial_qty // lot) * lot  # Round to lot size
                    
                    if partial_qty > 0:
                        self.partial_exit_attempts += 1
                        print(f"\n[SCALPING] 0.5R Target Hit! Taking Partial Profit ({PARTIAL_EXIT_PCT*100}% = {partial_qty} qty)...")
                        
                        try:
                            resp = self.place_order_safe(
                                exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                                quantity=str(partial_qty), validity="DAY", trading_symbol=self.position['symbol'],
                                transaction_type="S", amo="NO"
                            )
                            
                            if resp and isinstance(resp, dict):
                                ord_id = resp.get('nOrdNo')
                                if ord_id:
                                    # Verify partial exit
                                    filled_partial, f_partial_price, f_partial_qty = self.verify_order_fill(ord_id)
                                    
                                    if filled_partial and f_partial_qty > 0:
                                        partial_pnl = (f_partial_price - self.position['avg_price']) * f_partial_qty
                                        
                                        # CRITICAL FIX #1: Track partial profit in daily PnL
                                        self.daily_pnl += partial_pnl
                                        
                                        # Update position
                                        self.position['qty'] -= f_partial_qty
                                        self.position['partial_exited'] = True
                                        self.position['remaining_qty'] = self.position['qty']
                                        
                                        # CRITICAL FIX #2: Update base_qty for correct pyramid sizing
                                        self.position['base_qty'] = self.position['qty']
                                        
                                        # CRITICAL FIX #3: Safety check for zero qty
                                        if self.position['qty'] <= 0:
                                            logger.error("[CRITICAL] Position qty became 0 after partial exit. Forcing full exit.")
                                            self.state = "POSITION_EXIT"
                                            return
                                        
                                        print(f"[SCALPING SUCCESS] Partial Exit {f_partial_qty} @ {f_partial_price:.1f} | Profit: +{partial_pnl:.0f} | Remaining: {self.position['qty']} | Daily PnL: {self.daily_pnl:+.0f}")
                                        logger.info(f"Partial exit: {f_partial_qty} qty @ {f_partial_price}, PnL: +{partial_pnl:.0f}, Daily PnL: {self.daily_pnl:.0f}")
                                        
                                        # Reset retry counter on success
                                        self.partial_exit_attempts = 0
                                        
                                        # Let runner continue with pyramiding logic
                                        self.save_state()
                        except Exception as e:
                            logger.error(f"Partial exit order failed (attempt {self.partial_exit_attempts}/3): {e}")
            
            # Scalping Rule 2: Quick Timeout Exit (No profit after 30 mins)
            if self.position.get('entry_time'):
                mins_held = (datetime.now() - self.position['entry_time']).total_seconds() / 60
                
                # If held for 30+ mins and still not profitable, exit
                if mins_held >= QUICK_EXIT_TIMEOUT_MINS and current_R < 0.3:
                    print(f"\n[SCALPING TIMEOUT] No profit after {mins_held:.0f} mins (at {current_R:.2f}R). Quick exit.")
                    self.state = "POSITION_EXIT"
                    return

            # --- EXIT RULES ---
            
            # 1. Hard Stop Loss
            if term_ltp <= self.position['stop_loss']:
                print(f"\n[EXIT] Hard SL Hit. LTP:{term_ltp:.1f} <= SL:{self.position['stop_loss']:.1f}")
                self.state = "POSITION_EXIT"
                return

            # 2. Trend Reversal (Price Crosses EMA9)
            is_ce = (self.position.get('trade_dir', 'CE') == 'CE')
            
            if is_ce:
                # Bullish Exit: Spot drops below EMA9
                exit_trigger = self.ema9 * (1 - EMA_BUFFER_PCT)
                if spot_ltp < exit_trigger:
                    print(f"\n[EXIT] Trend Broken (Spot {spot_ltp:.0f} < EMA9 {self.ema9:.0f})")
                    self.state = "POSITION_EXIT"
                    return
            else:
                # Bearish Exit: Spot rises above EMA9
                exit_trigger = self.ema9 * (1 + EMA_BUFFER_PCT)
                if spot_ltp > exit_trigger:
                    print(f"\n[EXIT] Trend Broken (Spot {spot_ltp:.0f} > EMA9 {self.ema9:.0f})")
                    self.state = "POSITION_EXIT"
                    return

            # 3. Volatility Collapse (Exit when volatility dries up, regardless of PnL)
            peak_atr = self.position.get('peak_ATR', 0)
            if peak_atr > 0 and self.atr < (peak_atr * VOL_COLLAPSE_THRESHOLD): 
                print(f"\n[EXIT] Volatility Collapse (ATR -{int((1-VOL_COLLAPSE_THRESHOLD)*100)}%). Current:{self.atr:.2f} < Peak:{peak_atr:.2f}")
                self.state = "POSITION_EXIT"
                return

            # 4. Maximum Position Duration (Time Stop)
            if self.position.get('entry_time'):
                mins_held = (datetime.now() - self.position['entry_time']).total_seconds() / 60
                if mins_held > MAX_POSITION_DURATION_MINS:
                    print(f"\n[EXIT] Max Duration Reached: {mins_held:.0f}m > {MAX_POSITION_DURATION_MINS}m")
                    self.state = "POSITION_EXIT"
                    return

            # --- MANAGEMENT (Audit Hardened: Milestone Tiers & Locked Profit) ---
            
            # 1. Locked Profit System (Audit Fix v3: Anchor to Entry Price)
            if current_R >= 1.0:
                # Lock floor = (CurrentR - 0.5) * initial_risk_pts
                new_locked_pts = (current_R - LOCKED_PROFIT_OFFSET) * self.position['initial_risk_pts']
                self.position['locked_profit_pts'] = max(self.position.get('locked_profit_pts', 0.0), new_locked_pts)
                
                # SL ancored to ENTRY_PRICE, not shifting avg_price
                locked_sl = self.position['entry_price'] + self.position['locked_profit_pts']
                if locked_sl > self.position['stop_loss']:
                    self.position['stop_loss'] = locked_sl
                    self.save_state()

            # 2. Milestone Pyramiding (1 lot added per tier)
            next_tier_index = self.position.get('pyramid_count', 0)
            if next_tier_index < len(PYRAMID_LEVELS):
                target_R = PYRAMID_LEVELS[next_tier_index]
                
                if current_R >= target_R:
                    try:
                        # Asymmetric Sizing: Always 50% of initial base qty
                        py_qty = int(self.position['base_qty'] * 0.5)
                        lot = get_lot_size()
                        py_qty = max(lot, (py_qty // lot) * lot)
                        
                        # Capital Usage Check
                        # Audit Fix v4: Use avg_price for accounting consistency
                        current_cost = self.position['qty'] * self.position['avg_price'] 
                        new_cost = py_qty * term_ltp # Use current market price for new buying cost
                        if (current_cost + new_cost) > (CAPITAL * MAX_CAPITAL_USAGE_PCT):
                            # logger.warning(f"[MGMT] Pyramid Tier {target_R}R Skipped: Capital Limit ({MAX_CAPITAL_USAGE_PCT*100}%).")
                            # Increment count anyway to avoid looping on a blocked level
                            self.position['pyramid_count'] += 1
                            return

                        print(f"\n[MGMT] Tier {target_R}R Reached! Pyramiding {py_qty} Qty...")
                        
                        resp = self.place_order_safe(
                            exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                            quantity=str(py_qty), validity="DAY", trading_symbol=self.position['symbol'],
                            transaction_type="B", amo="NO"
                        )
                        
                        if not resp or not isinstance(resp, dict):
                            print(f"[FAIL] Pyramid Order Placement Failed: {resp}")
                            return

                        ord_id = resp.get('nOrdNo')
                        if not ord_id:
                            print(f"[FAIL] Pyramid Order No ID: {resp}")
                            return
                        
                        # VERIFY FILL
                        filled_py, f_price, f_qty = self.verify_order_fill(ord_id)
                        
                        # Consolidate paper and live logic (Audit Fix v5)
                        if filled_py or (PAPER_TRADE and f_qty > 0):
                            # Use actual fill price, fallback to market price if unavailable
                            fill_price = f_price if f_price > 0 else term_ltp
                            
                            # Update Avg with filled qty (works for both live and paper)
                            total_val = (self.position['qty'] * self.position['avg_price']) + (f_qty * fill_price)
                            new_total_qty = self.position['qty'] + f_qty
                            self.position['qty'] = new_total_qty
                            self.position['avg_price'] = total_val / new_total_qty
                            self.position['pyramid_count'] += 1
                            
                            status_tag = "PAPER" if PAPER_TRADE else "SUCCESS"
                            print(f"[{status_tag}] Pyramid Added x{f_qty}. New Avg: {self.position['avg_price']:.2f}")
                            self.save_state()
                        else:
                            print(f"[FAIL] Pyramid order not filled. Status: {resp}")
                    except Exception as e:
                        logger.error(f"Pyramid Order Logic Error: {e}")

        # 6. POSITION_EXIT
        elif self.state == "POSITION_EXIT":
            term_ltp = data_store.get_ltp(self.position['token'])
            
            # Audit Fix v4: Stale Tick Watchdog for Exit Logging
            if (time.time() - data_store.last_tick_time) > 5:
                logger.warning(f"[EXIT] Stale WebSocket data detected during exit! Last tick was {int(time.time() - data_store.last_tick_time)}s ago.")
            
            print(f"[EXIT EXEC] Closing {self.position['qty']} @ LTP:{term_ltp}. Triggered Exit.")
            
            try:
                resp = self.place_order_safe(
                    exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                    quantity=str(self.position['qty']), validity="DAY", trading_symbol=self.position['symbol'],
                    transaction_type="S", amo="NO"
                )
                
                if resp and isinstance(resp, dict):
                    ord_id = resp.get('nOrdNo')
                    if ord_id:
                        print(f"[EXIT ORDER] ID: {ord_id}")
                        # Audit Fix v3: Use actual fill price for final PnL
                        filled_ex, f_ex_price, f_ex_qty = self.verify_order_fill(ord_id)
                        
                        if filled_ex:
                            exit_price = f_ex_price if f_ex_price > 0 else term_ltp
                            actual_pnl = (exit_price - self.position['avg_price']) * self.position['qty']
                            
                            # Only finalize if order was FILLED
                            self.trades_today += 1
                            self.daily_pnl += actual_pnl
                            
                            # Loss-Only Cooldown (v8): Set cooldown timer only for losses
                            if actual_pnl < 0:
                                self.consecutive_losses += 1
                                self.last_exit_time = datetime.now()  # Start cooldown
                                print(f"[EXIT SUCCESS] Fill Price: {exit_price} | Final PnL: {actual_pnl:.2f} | Cooldown: {LOSS_COOLDOWN_MINS} mins")
                            else:
                                self.consecutive_losses = 0
                                self.last_exit_time = None  # No cooldown on winners
                                print(f"[EXIT SUCCESS] Fill Price: {exit_price} | Final PnL: {actual_pnl:.2f} | Ready for next trade")
                            
                            # Reset position and retry counter
                            self.position = self.default_position.copy()
                            self.exit_retry_count = 0
                            self.state = "NO_POSITION"
                            self.save_state()
                        else:
                            # Audit Fix v5: Implement retry mechanism with forced reset
                            self.exit_retry_count += 1
                            logger.error(f"[EXIT FAILURE] Order {ord_id} not filled/rejected. Retry {self.exit_retry_count}/5")
                            
                            if self.exit_retry_count >= 5:
                                logger.critical("[EMERGENCY] Exit failed 5 times. Forcing position reset for safety.")
                                print("\n[CRITICAL] Manual intervention may be required - check broker terminal!")
                                self.position = self.default_position.copy()
                                self.exit_retry_count = 0
                                self.state = "NO_POSITION"
                                self.save_state()
                            return
                    else:
                        self.exit_retry_count += 1
                        logger.error(f"Exit order failed - no order ID: {resp}. Retry {self.exit_retry_count}/5")
                        
                        if self.exit_retry_count >= 5:
                            logger.critical("[EMERGENCY] Exit failed 5 times (no order ID). Forcing position reset.")
                            self.position = self.default_position.copy()
                            self.exit_retry_count = 0
                            self.state = "NO_POSITION"
                            self.save_state()
                        return
                else:
                    self.exit_retry_count += 1
                    logger.error(f"Exit order failed - invalid response: {resp}. Retry {self.exit_retry_count}/5")
                    
                    if self.exit_retry_count >= 5:
                        logger.critical("[EMERGENCY] Exit failed 5 times (invalid response). Forcing position reset.")
                        self.position = self.default_position.copy()
                        self.exit_retry_count = 0
                        self.state = "NO_POSITION"
                        self.save_state()
                    return
            except Exception as e:
                self.exit_retry_count += 1
                logger.error(f"Exit order exception: {e}. Retry {self.exit_retry_count}/5")
                
                if self.exit_retry_count >= 5:
                    logger.critical("[EMERGENCY] Exit failed 5 times (exception). Forcing position reset.")
                    self.position = self.default_position.copy()
                    self.exit_retry_count = 0
                    self.state = "NO_POSITION"
                    self.save_state()
                return

        # 6. MARKET_CLOSE
        elif self.state == "MARKET_CLOSE":
            print("Market Closed. Strategy Done.")
            self.running = False

    def shutdown(self):
        self.running = False


if __name__ == "__main__":
    strategy = OptionBuyingStrategy()
    if strategy and getattr(strategy, 'running', False): 
        strategy.run()
    else:
        print("[CRITICAL] Strategy failed to initialize (Tokens not found?).")
