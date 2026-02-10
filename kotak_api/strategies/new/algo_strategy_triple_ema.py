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
        logging.FileHandler(os.path.join(LOG_DIR, "algo_strategy_triple_ema.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TripleEMA")

load_dotenv()
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP")
MPIN = os.getenv("KOTAK_MPIN")
STATE_FILE = os.path.join(DATA_DIR, "triple_ema_state.json")

# --- STRATEGY PARAMETERS ---
MAX_TRADES_DAY = 15
DEPLOYMENT_PCT = 50.0     
RISK_PER_TRADE_PCT = 1.0  
OTM_OFFSET = 100           

# Percentage-based Risk (As % of OPTION PREMIUM)
STOP_LOSS_PCT = 18.0    
TARGET_PCT = 35.0      
BE_ACTIVATION_PCT = 12.0 
TSL_ACTIVATION_PCT = 10.0 
TSL_TRAIL_PCT = 15.0     
TSL_MIN_TRAIL_PCT = 2.0  

# Pyramiding Config
PYRAMID_ENABLE = True
PYRAMID_TRIGGER_PCT = 15.0  # Add when PnL reaches 15%
PYRAMID_MAX_COUNT = 1       # Max 1 addition
PYRAMID_QTY_PCT = 50.0      # Add 50% of initial qty 

# Indicators Config
EMA_FAST = 5
EMA_MED = 8
EMA_SLOW = 13
TIMEFRAME = "5m"

# Safety Constants
PAPER_TRADE = True
TESTING_MODE = False   

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

def get_lot_size():
    if master_df is None or master_df.empty: return None
    try:
        # Look for NIFTY in FO segment
        nifty_fo = master_df[(master_df['pSymbolName'] == 'NIFTY') & (master_df['pExchSeg'] == 'nse_fo')]
        if nifty_fo.empty:
            nifty_fo = master_df[master_df['pTrdSymbol'] == 'NIFTY']
            
        if not nifty_fo.empty:
            for col in ['lLotSize', 'iLotSize', 'pLotSize']:
                if col in nifty_fo.columns:
                    val = nifty_fo.iloc[0][col]
                    if pd.notnull(val): return int(val)
    except Exception as e:
        logger.error(f"Error finding lot size: {e}")
    return None

# ================== MAIN STRATEGY ==================

# ================== MAIN STRATEGY ==================

class TripleEMAStrategy:
    def __init__(self):
        self.running = True
        self.client = get_kotak_client()
        if not self.client: 
            self.running = False
            return
            
        load_master_data()
        self.spot_token = get_nifty_tokens()
        self.expiry = get_nearest_expiry()
        self.lot_size = get_lot_size()
        
        if self.lot_size is None:
            logger.error("❌ CRITICAL: Could not find Nifty Lot Size in Master Data. Shutting down.")
            self.running = False
            return
            
        logger.info(f"Initialized Strategy: Nifty Lot Size = {self.lot_size}")
        
        # State
        self.state = "INIT"
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.position = {'qty': 0, 'token': None, 'symbol': None, 'type': None, 'avg_price': 0.0}
        
        self.last_candle_time = None
        self.last_signal_time = None
        self.latest_inds = None
        self.load_state()
        self.start_websocket()


    def start_websocket(self):
        try:
            self.client.on_message = self.on_message
            self.client.on_error = self.on_error
            self.client.on_close = self.on_close
            self.client.on_open = self.on_open
            
            self.refresh_subscriptions()
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

    def refresh_subscriptions(self):
        try:
            tokens = [{"instrument_token": str(self.spot_token), "exchange_segment": "nse_cm"}]
            if self.position['token']:
                tokens.append({"instrument_token": str(self.position['token']), "exchange_segment": "nse_fo"})
            self.client.subscribe(instrument_tokens=tokens)
        except Exception as e: logger.error(f"Sub Error: {e}")


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
                        self.last_signal_time = data.get('last_signal_time')
                        logger.info("State Restored.")
            except: pass

    def save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump({
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'state': self.state, 'trades_today': self.trades_today,
                    'position': self.position, 'daily_pnl': self.daily_pnl,
                    'last_signal_time': self.last_signal_time
                }, f)
        except: pass

    def get_available_funds(self):
        try:
            limits = self.client.limits()
            if limits and isinstance(limits, dict) and 'Net' in limits:
                total_funds = float(limits['Net'].replace(',', ''))
                tradeable_funds = total_funds * (DEPLOYMENT_PCT / 100.0)
                return tradeable_funds, total_funds
        except Exception as e:
            logger.error(f"Error fetching funds: {e}")
        
        return 0.0, 0.0

    def check_margin_required(self, tok, qty, side):
        try:
            resp = self.client.margin_required(
                exchange_segment="nse_fo", price="0", order_type="MKT", product="NRML",
                quantity=str(qty), instrument_token=str(tok), transaction_type="S"
            )
            if resp and 'data' in resp and 'total' in resp['data']:
                return float(resp['data']['total'])
        except Exception as e:
            logger.error(f"Margin API Error: {e}")
        return (qty // 25) * 45000.0 

    def calculate_indicators(self, df):
        try:
            if len(df) < EMA_SLOW + 5: return None
            
            # Triple EMA
            ema_fast = ta.ema(df['Close'], length=EMA_FAST)
            ema_med = ta.ema(df['Close'], length=EMA_MED)
            ema_slow = ta.ema(df['Close'], length=EMA_SLOW)
            
            return {
                'ema_fast': ema_fast.iloc[-2],
                'ema_med': ema_med.iloc[-2],
                'ema_slow': ema_slow.iloc[-2],
                'candle_close': df['Close'].iloc[-2],
                'timestamp': df.index[-2] # Lock to completed candle
            }
        except Exception as e:
            logger.error(f"Indication Error: {e}")
            return None

    def process(self):
        now = datetime.now()
        
        time_str = now.strftime("%H:%M")
        if not TESTING_MODE:
            if time_str < TIME_MARKET_OPEN: return
            if time_str >= TIME_HARD_EXIT:
                if self.state == "POSITION_OPEN": self.close_position("HARD_EXIT_TIME")
                return
        
        spot_ltp = data_store.get_ltp(self.spot_token)
        if spot_ltp == 0: return

        if self.last_candle_time is None or (now - self.last_candle_time).seconds >= 60:
            df = fetch_nifty_historical(period="1d", interval=TIMEFRAME)
            if df.empty: return
            
            inds = self.calculate_indicators(df)
            if not inds: return
            
            self.latest_inds = inds # Store for management logic
            self.last_candle_time = now
            
            if self.state == "POSITION_OPEN":
                pass
            elif self.state == "INIT" or self.state == "NO_POSITION":
                 # Prevent multiple entries on the same signal candle
                 if inds['timestamp'] != self.last_signal_time:
                    self.check_entry(spot_ltp, inds)
                    self.last_signal_time = inds['timestamp']


    def manage_position(self):
        if self.state != "POSITION_OPEN": return
        
        opt_token = self.position['token']
        opt_ltp = data_store.get_ltp(opt_token)
        
        if opt_ltp == 0: return 
        
        pos = self.position
        entry_prem = pos.get('avg_price', 0)
        
        if entry_prem == 0: return # Handle invalid state
        
        pnl_pts = (entry_prem - opt_ltp)
        pnl_pct = (pnl_pts / entry_prem) * 100
        
        # --- PYRAMIDING LOGIC ---
        if PYRAMID_ENABLE and pnl_pct >= PYRAMID_TRIGGER_PCT:
            current_count = pos.get('pyramid_count', 0)
            if current_count < PYRAMID_MAX_COUNT:
                self.execute_pyramid(opt_ltp)
                return # Return to allow state update to reflect
        
        # 1. Target
        if pnl_pct >= TARGET_PCT:
            self.close_position(f"TARGET_HIT_{TARGET_PCT}%")
            return

        # 2. Best Price Update
        if opt_ltp < pos['best_price']:
            self.position['best_price'] = opt_ltp

        # 3. TSL Activation
        if not pos.get('is_tsl_active') and pnl_pct >= TSL_ACTIVATION_PCT:
            self.position['is_tsl_active'] = True
            logger.info(f"🔥 TSL Activated! Current PnL: {pnl_pct:.2f}%")
        
        # 4. TSL Logic
        if pos.get('is_tsl_active'):
            total_range = (TARGET_PCT - TSL_ACTIVATION_PCT)
            if total_range > 0:
                progress = (pnl_pct - TSL_ACTIVATION_PCT) / total_range
                progress = max(0, min(1, progress))
            else:
                progress = 0
            
            dynamic_trail_pct = TSL_TRAIL_PCT - (progress * (TSL_TRAIL_PCT - TSL_MIN_TRAIL_PCT))
            self.position['current_trail_pct'] = dynamic_trail_pct
            
            trail_pts = (entry_prem * dynamic_trail_pct / 100)
            new_tsl = pos['best_price'] + trail_pts
            
            if new_tsl < pos['stop_loss']:
                self.position['stop_loss'] = new_tsl
                self.save_state()

        # 5. BE Logic
        elif not pos.get('is_be_active') and pnl_pct >= BE_ACTIVATION_PCT:
             self.position['stop_loss'] = entry_prem
             self.position['is_be_active'] = True
             logger.info(f"💥 Break-Even Activated! PnL: {pnl_pct:.2f}%")
             self.save_state()

             self.save_state()
             
        # 6. Trend Reversal Exit (EMA Cross)
        if self.latest_inds:
            spot_ltp = data_store.get_ltp(self.spot_token)
            e5 = self.latest_inds['ema_fast']
            e8 = self.latest_inds['ema_med']
            e13 = self.latest_inds['ema_slow']
            
            if spot_ltp > 0:
                # BEARISH TRADE Exit: Price > All EMAs
                if pos['type'] == 'CE_SHORT':
                    if spot_ltp > e5 and spot_ltp > e8 and spot_ltp > e13:
                        self.close_position(f"EMA_REVERSAL_EXIT [Spot ({spot_ltp}) > All EMAs]")
                        return

                # BULLISH TRADE Exit: Price < All EMAs
                elif pos['type'] == 'PE_SHORT':
                    if spot_ltp < e5 and spot_ltp < e8 and spot_ltp < e13:
                        self.close_position(f"EMA_REVERSAL_EXIT [Spot ({spot_ltp}) < All EMAs]")
                        return

        # 7. SL Hit
        if opt_ltp >= pos['stop_loss']:
            self.close_position(f"STOP_LOSS_HIT [SL: {pos['stop_loss']:.2f}, LTP: {opt_ltp:.2f}]")

    def execute_pyramid(self, current_ltp):
        pos = self.position
        initial_qty = pos['qty']
        add_qty = round((initial_qty * (PYRAMID_QTY_PCT / 100.0)) / self.lot_size) * self.lot_size
        if add_qty < self.lot_size: add_qty = self.lot_size
        
        # Margin Check
        funds, _ = self.get_available_funds()
        margin = self.check_margin_required(pos['token'], add_qty, "S")
        if margin > funds:
            logger.warning("⚠️ Insufficient funds for Pyramiding. Skipping.")
            # Mark max count reached to avoid retry loop
            self.position['pyramid_count'] = PYRAMID_MAX_COUNT
            return

        logger.info(f"🚀 PYRAMIDING: Adding {add_qty} Qty at {current_ltp:.2f}")
        
        if not PAPER_TRADE:
             try:
                # Place Sell Order
                self.client.place_order(
                    exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                    quantity=str(add_qty), validity="DAY", trading_symbol=pos['symbol'],
                    transaction_type="S", amo="NO"
                )
             except Exception as e: logger.error(f"Pyramid Order Error: {e}")

        # Update Weighted Average Price
        # New Price = ((OldQty * OldAvg) + (NewQty * NewPrice)) / TotalQty
        old_val = pos['qty'] * pos['avg_price']
        new_val = add_qty * current_ltp
        total_qty = pos['qty'] + add_qty
        new_avg = (old_val + new_val) / total_qty
        
        self.position['qty'] = total_qty
        self.position['avg_price'] = new_avg
        self.position['entry_price'] = new_avg # Shift 'entry' to new avg for PnL calcs
        self.position['pyramid_count'] = pos.get('pyramid_count', 0) + 1
        
        # Reset Logic: Move SL to Break Even (New Avg)
        self.position['stop_loss'] = new_avg 
        self.position['is_be_active'] = True # Consider BE done
        
        logger.info(f"✅ Pyramid Done. New Qty: {total_qty}, New Avg: {new_avg:.2f}, SL moved to Avg.")
        self.save_state()

    def check_entry(self, spot_ltp, inds):
        """
        Trend Following: Triple EMA Alignment (Price < 5 < 8 < 13)
        """
        e5 = inds['ema_fast']
        e8 = inds['ema_med']
        e13 = inds['ema_slow']
        close = inds['candle_close']
        
        # SELL CE (Bearish)
        # Price < EMA 5 < EMA 8 < EMA 13
        if close < e5 and e5 < e8 and e8 < e13:
            logger.info(f"🚀 BEARISH: Price({close:.1f}) < E5({e5:.1f}) < E8({e8:.1f}) < E13({e13:.1f}). SELL CE")
            # Use EMA 13 (Slowest) as the pivot/resistance point for SL calculation
            self.execute_entry("CE_SHORT", spot_ltp, e13) 

        # SELL PE (Bullish)
        # Price > EMA 5 > EMA 8 > EMA 13
        elif close > e5 and e5 > e8 and e8 > e13:
            logger.info(f"🚀 BULLISH: Price({close:.1f}) > E5({e5:.1f}) > E8({e8:.1f}) > E13({e13:.1f}). SELL PE")
            self.execute_entry("PE_SHORT", spot_ltp, e13)

    def execute_entry(self, side, spot_ltp, pivot_val):
        if self.trades_today >= MAX_TRADES_DAY:
            logger.warning(f"⚠️ Max Trades ({MAX_TRADES_DAY}) Reached. Skipping Entry.")
            return

        atm_strike = round(spot_ltp / 50) * 50
        
        if side == 'CE_SHORT':
            strike = atm_strike + abs(OTM_OFFSET)
        else:
            strike = atm_strike - abs(OTM_OFFSET)
            
        opt_type = 'CE' if side == 'CE_SHORT' else 'PE'
        
        tok, sym = get_option_token(strike, opt_type, self.expiry)
        if not tok: return
        
        tradeable_funds, total_funds = self.get_available_funds()
        if tradeable_funds <= 0:
            logger.error("❌ CRITICAL: Could not verify live funds. Skipping Entry.")
            return
        
        # Sizing Logic
        sl_dist = abs(spot_ltp - pivot_val)
        safe_sl_dist = max(sl_dist, spot_ltp * 0.0005) 
        
        risk_rupees = (tradeable_funds * RISK_PER_TRADE_PCT / 100)
        raw_qty = risk_rupees / safe_sl_dist
        qty = round(raw_qty / self.lot_size) * self.lot_size
        # --- REAL-TIME MARGIN CHECK ---
        margin_needed = self.check_margin_required(tok, qty, "S")
        
        # Check against TRADEABLE funds limit
        if margin_needed > tradeable_funds:
            # Calculate cost per unit: margin_needed / current_qty
            # new_qty = Available Funds / Cost_Per_Unit
            # Then floor division to finding nearest lot multiple
            cost_per_qty = margin_needed / qty
            max_qty_possible = tradeable_funds / cost_per_qty
            new_qty = int(max_qty_possible // self.lot_size) * self.lot_size
            
            logger.warning(f"⚠️ Margin exceeds Deployment Cap (Need: {margin_needed}, Cap: {tradeable_funds}). Scaling: {qty} -> {new_qty}")
            qty = new_qty
            
        if qty < self.lot_size:
             logger.error("❌ Not enough funds.")
             return
        
        entry_premium = 0.0
        try:
            q_resp = self.client.quotes(instrument_tokens=[{"instrument_token": str(tok), "exchange_segment": "nse_fo"}])
            if q_resp and 'message' in q_resp and len(q_resp['message']) > 0:
                entry_premium = float(q_resp['message'][0]['ltp'])
        except: pass
        if entry_premium == 0: entry_premium = 100.0 
            
        hard_sl = entry_premium * (1 + (STOP_LOSS_PCT / 100))
        
        logger.info(f"ENTERING {side}: {sym} Qty: {qty} | Entry: {entry_premium:.1f} | SL: {hard_sl:.1f}")

        if not PAPER_TRADE:
             try:
                self.client.place_order(
                    exchange_segment="nse_fo", product="NRML", price="0", order_type="MKT",
                    quantity=str(qty), validity="DAY", trading_symbol=sym,
                    transaction_type="S", amo="NO"
                )
             except Exception as e:
                logger.error(f"❌ LIVETRADE ENTRY ERROR: {e}")
                return # Block state update on failure

        self.state = "POSITION_OPEN"
        self.position = {
            'qty': qty, 'token': tok, 'symbol': sym, 'type': side,
            'entry_price': entry_premium, 'avg_price': entry_premium, # Init avg_price
            'stop_loss': hard_sl,
            'best_price': entry_premium,
            'is_be_active': False,
            'is_tsl_active': False,
            'pyramid_count': 0
        }
        self.trades_today += 1
        self.save_state()
        self.start_websocket()

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
        logger.info("Triple EMA Strategy Started...")
        self.last_status_print = 0
        self.last_ws_check = 0
        
        while self.running:
            try:
                self.process()
                self.manage_position()
                
                # --- WS HEARTBEAT CHECK ---
                if time.time() - self.last_ws_check > 30:
                    # Request quotes as a heartbeat; if it fails/times out, we re-sub
                    try:
                        self.refresh_subscriptions()
                        self.last_ws_check = time.time()
                    except: pass
                
                if time.time() - self.last_status_print > 5:
                    spot = data_store.get_ltp(self.spot_token)
                    state_clean = self.state.replace("_", " ")
                    msg = f"\r[{state_clean}] Nifty: {spot:.2f} | "
                    
                    if self.state == "POSITION_OPEN":
                        opt_ltp = data_store.get_ltp(self.position.get('token'))
                        if opt_ltp > 0:
                            entry_p = self.position['avg_price'] 
                            pnl_pts = (entry_p - opt_ltp)
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
                        msg += "Wait for Trend Setup..."
                    
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
        self.running = False
        os._exit(0)

if __name__ == "__main__":
    try:
        strat = TripleEMAStrategy()
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
