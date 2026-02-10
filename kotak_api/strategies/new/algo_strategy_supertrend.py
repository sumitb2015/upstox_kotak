import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
import pandas as pd
import pandas_ta as ta
from neo_api_client import NeoAPI
import pyotp
from dotenv import load_dotenv

# Add lib to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)

from lib.historical_data import fetch_nifty_historical

# ================== CONFIGURATION ==================
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "algo_strategy_supertrend.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SupertrendPro")

load_dotenv()
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP")
MPIN = os.getenv("KOTAK_MPIN")
STATE_FILE = os.path.join(DATA_DIR, "supertrend_state.json")
# --- STRATEGY PARAMETERS ---
CAPITAL = 200000
MAX_TRADES_DAY = 15
DEPLOYMENT_PCT = 50.0     # Use only 50% of available funds for sizing
RISK_PER_TRADE_PCT = 1.0  # Risk 1% of DEPLOYED capital per trade
LOT_SIZE = 75            # Nifty current lot size
OTM_OFFSET = 100           # Offset in points (multiples of 50). E.g. 50 = 1 strike OTM.

# Percentage-based Risk (As % of Nifty Spot Price)
STOP_LOSS_PCT = 0.20    # Initial Hard Max SL (0.2% = ~50 pts)
# Percentage-based Risk (As % of OPTION PREMIUM)
STOP_LOSS_PCT = 0.18    # Hard Max SL (Options move faster, so 0.18% is tight)
TARGET_PCT = 0.35      # Hard Target (Realistic capture)
BE_ACTIVATION_PCT = 0.12 # Move to BE
TSL_ACTIVATION_PCT = 0.10 # Start TSL earlier
TSL_TRAIL_PCT = 0.10     # Wider initial leash
TSL_MIN_TRAIL_PCT = 0.04 # Tight choke at end

# Indicators Config
ST_PERIOD = 10
ST_MULTIPLIER = 3.0   
RSI_PERIOD = 14
TIMEFRAME = "1m"

# Safety Constants
PAPER_TRADE = True
TESTING_MODE = False   # Set True to bypass time checks

TIME_MARKET_OPEN = "09:20"
TIME_NO_ENTRY_AFTER = "15:10"
TIME_HARD_EXIT = "15:18"

# ================== GLOBALS ==================
client = None
master_df = None
data_store = None

class DataStore:
    """Thread-safe price cache."""
    def __init__(self):
        self.prices = {}
        self.lock = threading.Lock()
    def update(self, token, ltp):
        with self.lock:
            self.prices[str(token)] = ltp
    def get_ltp(self, token):
        with self.lock: return self.prices.get(str(token), 0)

data_store = DataStore()

# ================== UTILS ==================
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
    segments = ['nse_fo.csv', 'nse_cm.csv']
    dfs = []
    for filename in segments:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            try: dfs.append(pd.read_csv(path, low_memory=False))
            except: pass
    master_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    if not master_df.empty: master_df.columns = master_df.columns.str.strip()

def get_nifty_tokens():
    if master_df is None: return None
    try:
        spot = master_df[(master_df['pTrdSymbol'] == 'NIFTY') & (master_df['pExchSeg'] == 'nse_cm')]
        if not spot.empty: return int(spot.iloc[0]['pSymbol'])
    except: pass
    return None

def get_nearest_expiry():
    if master_df is None or master_df.empty: return None
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    expiry_dates = set()
    import re
    for sym in master_df[master_df['pTrdSymbol'].str.match(r'^NIFTY\d{2}[1-9OND]\d{2}', na=False)]['pTrdSymbol'].head(100):
         match = re.match(r'^NIFTY(\d{2})([1-9OND])(\d{2})', sym)
         if match:
             try:
                 yy, m_char, dd = int(match.group(1)), match.group(2), int(match.group(3))
                 m = int(m_char) if m_char.isdigit() else {'O':10,'N':11,'D':12}[m_char]
                 dt = datetime(2000+yy, m, dd)
                 if dt.date() >= today.date():
                     expiry_dates.add(dt)
             except: pass
    if expiry_dates:
        return sorted(list(expiry_dates))[0]
    return None

def get_option_token(strike, opt_type, expiry):
    if master_df is None or expiry is None: return None, None
    m_code = str(expiry.month) if expiry.month <= 9 else {10:'O', 11:'N', 12:'D'}[expiry.month]
    weekly_sym = f"NIFTY{expiry.strftime('%y')}{m_code}{expiry.strftime('%d')}{int(strike)}{opt_type}"
    res = master_df[(master_df['pTrdSymbol'] == weekly_sym) & (master_df['pExchSeg'] == 'nse_fo')]
    if not res.empty: return int(res.iloc[0]['pSymbol']), weekly_sym
    return None, None

# ================== MAIN STRATEGY ==================

class SupertrendStrategy:
    def __init__(self):
        self.running = True
        self.client = get_kotak_client()
        if not self.client: 
            self.running = False
            return
            
        load_master_data()
        self.spot_token = get_nifty_tokens()
        self.expiry = get_nearest_expiry()
        
        # State
        self.state = "INIT"
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.position = {'qty': 0, 'token': None, 'symbol': None, 'type': None, 'avg_price': 0.0}
        
        self.last_candle_time = None
        self.load_state()
        self.start_websocket()

    def start_websocket(self):
        try:
            self.client.on_message = self.on_message
            self.client.on_error = self.on_error
            self.client.on_close = self.on_close
            self.client.on_open = self.on_open
            
            tokens = [{"instrument_token": str(self.spot_token), "exchange_segment": "nse_cm"}]
            if self.position['token']:
                tokens.append({"instrument_token": str(self.position['token']), "exchange_segment": "nse_fo"})
            self.client.subscribe(instrument_tokens=tokens)
        except Exception as e: logger.error(f"WS Error: {e}")

    def on_open(self, message):
        logger.info("Websocket Connection Opened")

    def on_error(self, message):
        logger.error(f"Websocket Error: {message}")

    def on_close(self, message):
        logger.warning("Websocket Connection Closed")

    def on_message(self, message):
        try:
            if 'data' in message:
                for tick in message['data']:
                    tk = str(tick.get('tk', tick.get('instrument_token')))
                    ltp = float(tick.get('ltp', tick.get('last_price', 0)))
                    if tk and ltp > 0: data_store.update(tk, ltp)
        except: pass

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == datetime.now().strftime("%Y-%m-%d"):
                        self.state = data.get('state', 'INIT')
                        self.trades_today = data.get('trades_today', 0)
                        self.position = data.get('position', self.position)
                        self.daily_pnl = data.get('daily_pnl', 0.0)
                        logger.info("State Restored.")
            except: pass

    def save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump({
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'state': self.state, 'trades_today': self.trades_today,
                    'position': self.position, 'daily_pnl': self.daily_pnl
                }, f)
        except: pass

    def get_available_funds(self):
        """Fetch live available funds and scale by deployment percentage."""
        try:
            limits = self.client.limits()
            if limits and isinstance(limits, dict) and 'Net' in limits:
                total_funds = float(limits['Net'].replace(',', ''))
                tradeable_funds = total_funds * (DEPLOYMENT_PCT / 100.0)
                logger.info(f"🏦 Funds: Total ₹{total_funds:,.2f} | Deployed ({DEPLOYMENT_PCT}%) ₹{tradeable_funds:,.2f}")
                return tradeable_funds, total_funds
        except Exception as e:
            logger.error(f"Error fetching funds: {e}")
        
        logger.warning(f"Using default capital: ₹{CAPITAL:,.2f}")
        return float(CAPITAL) * (DEPLOYMENT_PCT / 100.0), float(CAPITAL)

    def check_margin_required(self, tok, qty, side):
        """Calculate exact margin needed from API."""
        try:
            resp = self.client.margin_required(
                exchange_segment="nse_fo", price="0", order_type="MKT", product="NRML",
                quantity=str(qty), instrument_token=str(tok), transaction_type="S"
            )
            if resp and 'data' in resp and 'total' in resp['data']:
                margin = float(resp['data']['total'])
                return margin
        except Exception as e:
            logger.error(f"Margin API Error: {e}")
        
        # Fallback estimation
        return (qty // 25) * 45000.0 # ~45k per lot estimate fallback

    def calculate_indicators(self, df):
        """Standard Supertrend + ADX + EMA."""
        try:
            if len(df) < max(ST_PERIOD, RSI_PERIOD) + 5: return None
            
            # Supertrend
            st_df = ta.supertrend(df['High'], df['Low'], df['Close'], length=ST_PERIOD, multiplier=ST_MULTIPLIER)
            # RSI (Faster than ADX for initiation)
            rsi_series = ta.rsi(df['Close'], length=RSI_PERIOD)
            
            return {
                'st': st_df.iloc[-1][f'SUPERT_{ST_PERIOD}_{ST_MULTIPLIER}'],
                'st_dir': st_df.iloc[-1][f'SUPERTd_{ST_PERIOD}_{ST_MULTIPLIER}'],
                'rsi': rsi_series.iloc[-1],
                'rsi_prev': rsi_series.iloc[-2],
                'candle_open': df['Open'].iloc[-1],
                'candle_close': df['Close'].iloc[-1]
            }
        except Exception as e:
            logger.error(f"Indication Error: {e}")
            return None

    def process(self):
        now = datetime.now()
        
        # Time Filters
        time_str = now.strftime("%H:%M")
        if not TESTING_MODE:
            if time_str < TIME_MARKET_OPEN: return
            if time_str >= TIME_HARD_EXIT:
                if self.state == "POSITION_OPEN": self.close_position("HARD_EXIT_TIME")
                return
        
        spot_ltp = data_store.get_ltp(self.spot_token)
        if spot_ltp == 0: return

        # Update Indicators every minute
        if self.last_candle_time is None or (now - self.last_candle_time).seconds >= 60:
            df = fetch_nifty_historical(period="1d", interval="1m")
            if df.empty: return
            
            inds = self.calculate_indicators(df)
            if not inds: return
            
            self.last_candle_time = now
            
            # 2. Real-Time SL/Target Check (Main Loop handles this now)
            if self.state == "POSITION_OPEN":
                # We still check ST flips on candle close
                self.check_exit_signals(spot_ltp, inds)
            elif self.state == "INIT" or self.state == "NO_POSITION":
                 self.check_entry(spot_ltp, inds, None)

    def manage_position(self):
        """Runs every second for Premium-Based PnL, TSL, and Targets."""
        if self.state != "POSITION_OPEN": return
        
        # We track Option Premium now
        opt_token = self.position['token']
        opt_ltp = data_store.get_ltp(opt_token)
        
        if opt_ltp == 0: return # Wait for first tick
        
        pos = self.position
        entry_prem = pos['entry_price'] # This is now Entry Premium
        
        # SHORT Position PnL: Profit if Price Falls
        # PnL Pts = Entry - Current
        pnl_pts = (entry_prem - opt_ltp)
        pnl_pct = (pnl_pts / entry_prem) * 100
        
        # 1. Hard Target Check (Premium %)
        if pnl_pct >= TARGET_PCT:
            self.close_position(f"TARGET_HIT_{TARGET_PCT}%")
            return

        # 2. Update Best Price (Lowest Premium Seen)
        if opt_ltp < pos['best_price']:
            self.position['best_price'] = opt_ltp

        # 3. Trailing Stop Loss (TSL) Activation (%)
        if not pos.get('is_tsl_active') and pnl_pct >= TSL_ACTIVATION_PCT:
            self.position['is_tsl_active'] = True
            logger.info(f"🔥 TSL Activated! Current Premium PnL: {pnl_pct:.2f}%")
        
        # 4. Apply Dynamic Trailing logic (%)
        if pos.get('is_tsl_active'):
            # Calculate Choke process
            total_range = (TARGET_PCT - TSL_ACTIVATION_PCT)
            if total_range > 0:
                progress = (pnl_pct - TSL_ACTIVATION_PCT) / total_range
                progress = max(0, min(1, progress))
            else:
                progress = 0
            
            # Linear Choke
            dynamic_trail_pct = TSL_TRAIL_PCT - (progress * (TSL_TRAIL_PCT - TSL_MIN_TRAIL_PCT))
            self.position['current_trail_pct'] = dynamic_trail_pct
            
            # Trail Distance in Points = Entry * pct
            trail_pts = (entry_prem * dynamic_trail_pct / 100)
            
            # For SHORT OPTIONS (Both CE & PE), we want Premium to FALL.
            # SL is ABOVE the price. TSL follows price DOWN.
            # New TSL = Lowest Price Seen + Trail Distance
            new_tsl = pos['best_price'] + trail_pts
            
            # Ratchet: Only move SL DOWN (Tighter)
            if new_tsl < pos['stop_loss']:
                self.position['stop_loss'] = new_tsl
                self.save_state()

        # 5. Break-Even Trigger Logic (%)
        elif not pos.get('is_be_active') and pnl_pct >= BE_ACTIVATION_PCT:
             self.position['stop_loss'] = entry_prem
             self.position['is_be_active'] = True
             logger.info(f"💥 Break-Even Activated! Premium dropped {pnl_pct:.2f}%")
             self.save_state()

        # 6. Real-Time Stop Loss Hit (Premium Check)
        # If Current Premium > Stop Premium -> Exit
        if opt_ltp >= pos['stop_loss']:
            self.close_position(f"STOP_LOSS_HIT [SL: {pos['stop_loss']:.2f}, LTP: {opt_ltp:.2f}]")

    def check_entry(self, spot_ltp, inds, current_candle):
        """
        Refined Entry (Option C - Color + 2-Candle Streak):
        1. Supertrend Direction (Trend Filter)
        2. RSI Slope (Momentum)
        3. Candle Color (Price Action Confirmation)
        """
        st_dir = inds['st_dir'] # 1 is Bullish, -1 is Bearish
        rsi = inds['rsi']
        rsi_prev = inds['rsi_prev']
        c_open = inds['candle_open']
        c_close = inds['candle_close']
        
        # SELL CE (Bearish) - Expecting Market Down
        # ST Red + RSI < 50 + Falling + Red Candle
        if st_dir == -1:
            if rsi < 50 and rsi < rsi_prev:
                if c_close < c_open: # Red Candle
                    logger.info(f"🚀 BEARISH Entry: ST Red, RSI Falling ({rsi:.1f} < {rsi_prev:.1f}), Red Candle. SELL CE")
                    self.execute_entry("CE_SHORT", spot_ltp, inds['st'])
            
        # SELL PE (Bullish) - Expecting Market Up
        # ST Green + RSI > 50 + Rising + Green Candle
        elif st_dir == 1:
            if rsi > 50 and rsi > rsi_prev:
                if c_close > c_open: # Green Candle
                    logger.info(f"🚀 BULLISH Entry: ST Green, RSI Rising ({rsi:.1f} > {rsi_prev:.1f}), Green Candle. SELL PE")
                    self.execute_entry("PE_SHORT", spot_ltp, inds['st'])

    def execute_entry(self, side, spot_ltp, st_val):
        # Calculate ATM Strike
        atm_strike = round(spot_ltp / 50) * 50
        
        # Apply OTM Offset
        # For Short CE: Higher strikes are OTM
        # For Short PE: Lower strikes are OTM
        if side == 'CE_SHORT':
            strike = atm_strike + abs(OTM_OFFSET)
        else:
            strike = atm_strike - abs(OTM_OFFSET)
            
        opt_type = 'CE' if side == 'CE_SHORT' else 'PE'
        
        tok, sym = get_option_token(strike, opt_type, self.expiry)
        if not tok: return
        
        # --- DYNAMIC POSITION SIZING (Real-Time Capital & Risk) ---
        tradeable_funds, total_funds = self.get_available_funds()
        
        sl_dist = abs(spot_ltp - st_val)
        # Safety: Cap SL distance at 0.05% of price (~12 pts)
        safe_sl_dist = max(sl_dist, spot_ltp * 0.0005) 
        
        # Risk is 1% of the DEPLOYED portion
        risk_rupees = (tradeable_funds * RISK_PER_TRADE_PCT / 100)
        
        # Quantity = Risk / Points 
        raw_qty = risk_rupees / safe_sl_dist
        qty = round(raw_qty / LOT_SIZE) * LOT_SIZE
        
        # --- REAL-TIME MARGIN CHECK ---
        margin_needed = self.check_margin_required(tok, qty, "S")
        
        # Check against TRADEABLE funds (to stay within 50% limit)
        if margin_needed > tradeable_funds:
            new_qty = (tradeable_funds // (margin_needed / qty)) // LOT_SIZE * LOT_SIZE
            logger.warning(f"⚠️ Margin exceeds Deployment Cap (Need: {margin_needed}, Cap: {tradeable_funds}). Scaling: {qty} -> {new_qty}")
            qty = new_qty
            
        if qty < LOT_SIZE:
             logger.error("❌ Not enough funds for even 1 lot.")
             return
        
        # Fetch Initial Option Premium for Reference
        entry_premium = 0.0
        try:
            q_resp = self.client.quotes(instrument_tokens=[{"instrument_token": str(tok), "exchange_segment": "nse_fo"}])
            if q_resp and 'message' in q_resp and len(q_resp['message']) > 0:
                entry_premium = float(q_resp['message'][0]['ltp'])
        except: pass
        
        if entry_premium == 0: 
            # Fallback if Quote fails: estimate from margin or wait for tick
            entry_premium = 100.0 
            
        # Initial Hard SL (Premium + %)
        hard_sl = entry_premium * (1 + (STOP_LOSS_PCT / 100))
        
        logger.info(f"💰 Sizing: Risk ₹{risk_rupees:.0f} | Funds (Total) ₹{total_funds:.0f} | Qty: {qty}")
        logger.info(f"ENTERING {side}: {sym} Qty: {qty} | Entry Premium: {entry_premium:.1f} | Hard SL Premium: {hard_sl:.1f}")

        if not PAPER_TRADE:
            # ... (order logic) ...
            pass

        self.state = "POSITION_OPEN"
        self.position = {
            'qty': qty, 'token': tok, 'symbol': sym, 'type': side,
            'entry_price': entry_premium, 'stop_loss': hard_sl,
            'best_price': entry_premium,
            'is_be_active': False,
            'is_tsl_active': False
        }
        self.trades_today += 1
        self.save_state()
        self.start_websocket() # Refresh sub

    def check_exit_signals(self, spot_ltp, inds):
        """Exit when Supertrend Direction Flips (Candle Close)"""
        st_dir = inds['st_dir']
        pos_type = self.position['type']
        
        if pos_type == "CE_SHORT" and st_dir == 1:
            self.close_position("ST_REVERSAL_BULLISH")
        elif pos_type == "PE_SHORT" and st_dir == -1:
            self.close_position("ST_REVERSAL_BEARISH")

    def close_position(self, reason):
        logger.info(f"CLOSING POSITION: {reason}")
        if not PAPER_TRADE:
            try:
                self.client.place_order(
                    exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                    quantity=str(self.position['qty']), validity="DAY", trading_symbol=self.position['symbol'],
                    transaction_type="B", amo="NO"
                )
            except: pass
            
        self.state = "NO_POSITION"
        self.position = {
            'qty': 0, 'token': None, 'symbol': None, 'type': None, 
            'entry_price': 0.0, 'stop_loss': 0.0, 'best_price': 0.0,
            'is_be_active': False, 'is_tsl_active': False
        }
        self.save_state()

    def run(self):
        logger.info("Supertrend Strategy Started...")
        self.last_status_print = 0
        while self.running:
            try:
                self.process()
                self.manage_position() # Real-time BE/SL handling
                
                # Heartbeat
                if time.time() - self.last_status_print > 5:
                    spot = data_store.get_ltp(self.spot_token)
                    state_clean = self.state.replace("_", " ")
                    msg = f"\r[{state_clean}] Nifty: {spot:.2f} | "
                    
                    if self.state == "POSITION_OPEN":
                        # PnL Check based on Option Premium
                        opt_ltp = data_store.get_ltp(self.position.get('token'))
                        if opt_ltp > 0:
                            entry_p = self.position['entry_price'] # Entry Premium
                            pnl_pts = (entry_p - opt_ltp) # Short: Entry - Current
                            pnl_pct = (pnl_pts / entry_p) * 100
                            
                            exit_mode = "RUNNING"
                            if self.position.get('is_tsl_active'):
                                cur_trail = self.position.get('current_trail_pct', TSL_TRAIL_PCT)
                                exit_mode = f"TSL {cur_trail:.2f}% [{self.position['stop_loss']:.1f}]"
                            elif self.position.get('is_be_active'):
                                exit_mode = "BE LOCKED"
                            else:
                                exit_mode = f"BE in {(BE_ACTIVATION_PCT - pnl_pct):.2f}%"
                            
                            msg += f"Prem: {opt_ltp:.1f} | PnL: {pnl_pct:+.2f}% ({pnl_pts:+.1f} pts) | {exit_mode}"
                    else:
                        msg += "Wait for Signal..."
                    
                    print(msg, end="", flush=True)
                    self.last_status_print = time.time()
                    
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("\nUser stopping...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(5)

    def shutdown(self):
        logger.info("Shutting down...")
        # Optionally close positions here if needed, or just disconnect
        self.running = False
        sys.exit(0)

if __name__ == "__main__":
    import sys
    try:
        strat = SupertrendStrategy()
        strat.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Critical Error: {e}")
    finally:
        try:
            if 'strat' in locals(): strat.shutdown()
        except: pass
        sys.exit(0)
