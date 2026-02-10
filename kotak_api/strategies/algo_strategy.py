"""
Algo Strategy: FSM-Based Value-Balanced NIFTY CE-PE Trading

Finite State Machine States:
  INIT → BALANCED → REBALANCE_REDUCE → REBALANCE_EXPAND → MONITOR → EXIT

Strategy:
1. Enter ATM NIFTY CE and PE positions
2. Monitor Total Trade Value (LTP × Qty) for each leg
3. If imbalance > 20%: REDUCE dominant leg
4. If min_lot reached: EXPAND weaker leg (once only)
5. MONITOR state allows one-time reversal rebalance
6. EXIT on persistent imbalance or risk breach

Features: DRY_RUN mode, guardrails, state persistence, detailed logging.
"""

import os
import json
import time
from datetime import datetime
import threading
from enum import Enum
import pandas as pd
from dotenv import load_dotenv
from neo_api_client import NeoAPI
import pyotp
import sys
import logging
import yfinance as yf

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("algo_strategy_base.log", encoding='utf-8')
        # Removed StreamHandler to prevent duplicate console output
    ]
)
logger = logging.getLogger("FSM_Algo")

load_dotenv()

# Credentials from environment
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
UCC = os.getenv("KOTAK_UCC")
TOTP = os.getenv("TOTP", "GC6A75CPAEY5WBWTQGMOGKQ2DE")
MPIN = os.getenv("KOTAK_MPIN")

# Strategy Parameters
NIFTY_STRIKE_INTERVAL = 50
STRANGLE_WIDTH = 200  # Points away from ATM
DRY_RUN = False              # Set to False for live trading

# FSM Guardrails
MIN_LOT_MULTIPLIER = 3      # Minimum 2 lots per leg (allows reduce by 1 lot)
MAX_LOT_MULTIPLIER = 5      # Maximum 5 lots per leg
MAX_TOTAL_TRADE_VALUE = 100000  # ₹1 lakh total exposure limit
MAX_REDUCE_ATTEMPTS = 5     # Max reduction attempts before escalating
COOLDOWN_SECONDS = 60       # 1 minute between adjustments
# MTM Limits (User Configurable)
TARGET_MTM_PROFIT = 5000.0  # Exit if profit reaches +5000
MAX_MTM_LOSS = 3000.0       # Exit if loss reaches -3000 (enter as positive value)

# Hybrid Threshold: Minimum absolute value difference to avoid over-trading on low prices
# Hybrid Threshold: Minimum absolute value difference to avoid over-trading on low prices
MIN_ABS_DIFF_THRESHOLD = 1500.0  # Equivalent to ~₹10/share with 2 lots (150 shares)

# Auto-Exit Time (User Configurable)
AUTO_EXIT_TIME_STR = "15:15"  # HH:MM format (24-hour)

# ======================== TRAILING STOP LOSS (User Configurable) ========================
# Level 1: Breakeven - When profit reaches TSL_TRIGGER_1, SL moves to TSL_SL_1
# Level 2: Lock Profit - When profit reaches TSL_TRIGGER_2, SL moves to TSL_SL_2
# Level 3: Trailing - Above TSL_TRIGGER_2, for every TSL_STEP_TRIGGER profit, SL moves by TSL_STEP_MOVE
TSL_TRIGGER_1 = 3000.0    # MTM threshold to activate Breakeven SL
TSL_SL_1 = 0.0            # Breakeven SL value (no loss)
TSL_TRIGGER_2 = 5000.0    # MTM threshold to lock profits
TSL_SL_2 = 3000.0         # Locked profit SL value
TSL_STEP_TRIGGER = 1000.0 # For every X profit above TSL_TRIGGER_2...
TSL_STEP_MOVE = 500.0     # ...move SL up by this amount
# ========================================================================================

# State-wise Thresholds (Dynamic)
STATE_THRESHOLDS = {
    "BALANCED": 30.0,              # Tight discipline
    "REBALANCE_REDUCE": 50.0,      # Wide tolerance for mechanical change
    "REBALANCE_EXPAND": 50.0,      # Wide tolerance for expansion
    "BALANCED_POST_EXPAND": 50.0,  # Stabilize after expansion
    "MONITOR": 30.0,               # Tight capital preservation
    "INIT": 30.0,
    "EXIT": 0.0
}


# FSM State and Exit Reason Enums
class FSMState(Enum):
    INIT = "INIT"
    BALANCED = "BALANCED"
    REBALANCE_REDUCE = "REBALANCE_REDUCE"
    REBALANCE_EXPAND = "REBALANCE_EXPAND"
    BALANCED_POST_EXPAND = "BALANCED_POST_EXPAND"  # New state to prevent churn
    MONITOR = "MONITOR"
    EXIT = "EXIT"


class ExitReason(Enum):
    POST_MONITOR_IMBALANCE = "POST_MONITOR_IMBALANCE"
    MAX_RISK_BREACH = "MAX_RISK_BREACH"
    TIME_EXIT = "TIME_EXIT"
    TREND_PERSISTENCE = "TREND_PERSISTENCE"
    MANUAL = "MANUAL"
    TARGET_HIT = "TARGET_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    NONE = "NONE"

# Global Data Store
class DataStore:
    def __init__(self):
        self.tick_data = {}  # {token: {'ltp': float, 'timestamp': float}}
        self.lock = threading.Lock()
        self.last_activity = time.time() # Track WS activity

    def update(self, token, ltp, pc=0.0, oi=0):
        with self.lock:
            self.tick_data[str(token)] = {'ltp': ltp, 'pc': pc, 'oi': oi, 'timestamp': time.time()}
            self.last_activity = time.time() # Refresh global activity

    def get_ltp(self, token):
        with self.lock:
            data = self.tick_data.get(str(token))
            return data['ltp'] if data else 0.0

    def get_change(self, token):
        with self.lock:
            data = self.tick_data.get(str(token))
            return data['pc'] if data else 0.0

    def get_oi(self, token):
        with self.lock:
            data = self.tick_data.get(str(token))
            return int(data['oi']) if data and 'oi' in data else 0

data_store = DataStore()


class FSMStrategy:
    """
    FSM-based Value-Balanced Options Strategy.
    
    States: INIT → BALANCED → REBALANCE_REDUCE → REBALANCE_EXPAND → MONITOR → EXIT
    
    Escalation: Reduction > Expansion (once) > Reversal (once) > Exit
    """
    
    def __init__(self, client, master_df, nifty_token, expiry, options_map):
        self.client = client
        self.master_df = master_df
        self.nifty_token = nifty_token
        self.expiry = expiry
        self.options_map = options_map  # {token: {'strike':..., 'type':..., 'symbol':...}}
        
        # Position State
        self.positions = {}  # {'CE': {'token':..., 'qty':..., 'strike':...}, 'PE': {...}}
        self.lock = threading.Lock()
        self.lot_size_cache = {}
        
        # FSM State
        self.state = FSMState.INIT
        self.exit_reason = ExitReason.NONE
        self.running = False
        
        # FSM Flags (Non-negotiable rules)
        self.allow_expand = True           # One-time expansion flag
        self.allow_reverse_rebalance = True  # One-time reversal flag
        self.reduce_count = 0              # Track reduction attempts
        self.previous_dominant = None      # Track for reversal detection
        
        # Timing
        self.last_adjustment_time = 0
        
        # MTM Caching (Rate Limit Protection)
        self.last_mtm_update = 0
        self.cached_mtm = 0.0
        
        # Logging
        self.state_log = []
        self.rebalance_log = []
        
        # TSL State
        self.max_mtm_high = -float('inf')  # High water mark for TSL
        
        # Nifty History Data
        self.nifty_data = self.fetch_nifty_data()
        self.last_yf_update = time.time() # Initialize last update time
        self.last_yf_update = time.time() # Initialize last update time
        self.last_oi_monitor = 0 # Track OI logging frequency
        
        # SL Confirmation
        self.sl_confirm_count = 0


    def fetch_nifty_data(self):
        """Fetch Nifty (^NSEI) data from yfinance."""
        print(f"\n📈 Fetching Nifty data from yfinance...")
        try:
            ticker = yf.Ticker("^NSEI")
            
            # 1. Fetch Daily Data (for Prev High/Low/Close)
            # Get last 5 days to ensure we get the last completed trading day
            daily_df = ticker.history(period="5d", interval="1d")
            
            if len(daily_df) < 2:
                print("  ⚠️ Insufficient daily data fetched.")
                return None
                
            # The last row is 'Today' (live/incomplete), so we take the second to last row for 'Yesterday'
            # Note: If run after market close, last row *might* be today. 
            # Ideally, we want the "Previous Completed Day". 
            # Logic: If today is a trading day and market is open, last row is today.
            # We explicitly target the last FULL candle.
            
            daily_df = daily_df.dropna()
            prev_day = daily_df.iloc[-2] # Second to last is definitely the previous completed day
            # (Assuming script runs during market hours of the current day)
            
            prev_date = prev_day.name.strftime('%Y-%m-%d')
            prev_high = prev_day['High']
            prev_low = prev_day['Low']
            prev_close = prev_day['Close']
            
            print(f"  📅 Previous Day ({prev_date}):")
            print(f"     High: {prev_high:.2f}")
            print(f"     Low:  {prev_low:.2f}")
            print(f"     Close: {prev_close:.2f}")
            
            # 2. Fetch 5-min Data (Recent)
            # Fetch 5 days of 5m data to capture yesterday's intraday
            intra_df = ticker.history(period="5d", interval="5m")
            
            if intra_df.empty:
                print("  ⚠️ No 5-min data fetched.")
            else:
                last_5min = intra_df.iloc[-1]
                print(f"  🕒 Last 5-min Candle ({last_5min.name}): Close {last_5min['Close']:.2f}")
            
            return {
                'prev_date': prev_date,
                'prev_high': prev_high,
                'prev_low': prev_low,
                'prev_close': prev_close,
                'intra_df': intra_df # Store full DF for advanced logic if needed
            }
            
        except Exception as e:
            print(f"  ❌ Error fetching yfinance data: {e}")
            return None

    # ==================== HELPER METHODS ====================
    
    def get_strike_token(self, strike, option_type):
        """Find token for a specific strike and type."""
        for token, details in self.options_map.items():
            if details['strike'] == strike and details['type'] == option_type:
                return token
        return None

    def get_cached_lot_size(self, symbol):
        """Get lot size with caching."""
        if symbol in self.lot_size_cache:
            return self.lot_size_cache[symbol]
        lot_size = get_lot_size(self.master_df, symbol)
        self.lot_size_cache[symbol] = lot_size
        return lot_size

    def get_position_values(self):
        """Get current CE and PE values and LTPs."""
        if 'CE' not in self.positions or 'PE' not in self.positions:
            return None
        
        ce_pos = self.positions['CE']
        pe_pos = self.positions['PE']
        
        ce_ltp = data_store.get_ltp(ce_pos['token'])
        pe_ltp = data_store.get_ltp(pe_pos['token'])
        
        if ce_ltp <= 0 or pe_ltp <= 0:
            return None
        
        ce_value = abs(ce_pos['qty']) * ce_ltp
        pe_value = abs(pe_pos['qty']) * pe_ltp
        
        return {
            'ce_value': ce_value, 'pe_value': pe_value,
            'ce_ltp': ce_ltp, 'pe_ltp': pe_ltp,
            'ce_qty': abs(ce_pos['qty']), 'pe_qty': abs(pe_pos['qty'])
        }

    def calculate_total_mtm(self, cache_duration=5):
        """Calculate total P&L manually using Kotak Neo formula (with 5s cache)."""
        # Check cache
        if time.time() - self.last_mtm_update < cache_duration:
            return self.cached_mtm

        try:
            positions_data = self.client.positions()
            if not positions_data or 'data' not in positions_data:
                return 0.0
                
            total_pnl = 0.0
            for pos in positions_data['data']:
                try:
                    # Parse Amounts (Strings in API response)
                    buy_amt = float(pos.get('buyAmt', 0) or 0)
                    cf_buy_amt = float(pos.get('cfBuyAmt', 0) or 0)
                    sell_amt = float(pos.get('sellAmt', 0) or 0)
                    cf_sell_amt = float(pos.get('cfSellAmt', 0) or 0)
                    
                    total_buy_amt = buy_amt + cf_buy_amt
                    total_sell_amt = sell_amt + cf_sell_amt
                    
                    # Parse Quantities
                    fl_buy_qty = int(pos.get('flBuyQty', 0) or 0)
                    cf_buy_qty = int(pos.get('cfBuyQty', 0) or 0)
                    fl_sell_qty = int(pos.get('flSellQty', 0) or 0)
                    cf_sell_qty = int(pos.get('cfSellQty', 0) or 0)
                    
                    total_buy_qty = fl_buy_qty + cf_buy_qty
                    total_sell_qty = fl_sell_qty + cf_sell_qty
                    
                    net_qty = total_buy_qty - total_sell_qty
                    
                    # Get Multiplier
                    multiplier = float(pos.get('multiplier', 1) or 1)
                    
                    # Get LTP from DataStore (WebSocket)
                    tok = str(pos.get('tok', pos.get('tk', '')))
                    ltp = data_store.get_ltp(tok)
                    
                    # If LTP is 0 in datastore, try getting closest from 'lp' if available or skip
                    if ltp == 0:
                        ltp = float(pos.get('lp', 0) or 0)
                        
                    # Calculate PnL: (SellAmt - BuyAmt) + (NetQty * LTP * Multiplier)
                    pnl = (total_sell_amt - total_buy_amt) + (net_qty * ltp * multiplier)
                    
                    # Debug logic for specific symbol if needed
                    # print(f"  DEBUG {pos.get('trdSym')}: NetQty={net_qty}, LTP={ltp}, PnL={pnl}")
                    
                    total_pnl += pnl
                    
                except Exception as ex:
                    continue
            
            # Update cache
            self.cached_mtm = total_pnl
            self.last_mtm_update = time.time()
            
            return total_pnl
        except Exception as e:
            # print(f"  ⚠️ MTM Calc Error: {e}")
            return 0.0

    def calculate_imbalance(self, ce_value, pe_value):
        """Calculate imbalance percentage using max-based formula."""
        max_val = max(ce_value, pe_value)
        if max_val == 0:
            return 0
        return abs(ce_value - pe_value) / max_val * 100

    def get_dominant_side(self, ce_value, pe_value):
        """Return 'CE' or 'PE' based on which has higher value."""
        return 'CE' if ce_value > pe_value else 'PE'

    def log_state_transition(self, from_state, to_state, trigger, details=None):
        """Log state transition with timestamp."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'from_state': from_state.value,
            'to_state': to_state.value,
            'trigger': trigger,
            'details': details or {}
        }
        self.state_log.append(entry)
        print(f"\n  🔄 STATE TRANSITION: {from_state.value} → {to_state.value}")
        print(f"     Trigger: {trigger}")
        if details:
            print(f"     Details: {json.dumps(details, indent=2)}")

    # ==================== ORDER METHODS ====================

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

    def place_order(self, token, qty, transaction_type, tag="FSM"):
        """Place an order. Respects DRY_RUN mode."""
        symbol = self.options_map.get(token, {}).get('symbol', str(token))
        try:
            action = "BUY" if transaction_type == "B" else "SELL"
            print(f"  📝 {'[DRY RUN] ' if DRY_RUN else ''}ORDER: {action} {qty} x {symbol} [{tag}]")
            
            if DRY_RUN:
                print(f"  🧪 DRY RUN: Order simulated - {action} {qty} x {symbol}")
                return True
            
            response = self.client.place_order(
                exchange_segment="nse_fo", product="MIS", price="0", order_type="MKT",
                quantity=str(qty), validity="DAY", trading_symbol=symbol,
                transaction_type=transaction_type, amo="NO"
            )
            
            if response and isinstance(response, dict) and 'nOrdNo' in response:
                order_id = response['nOrdNo']
                print(f"  ✅ Order Placed! ID: {order_id}")
                time.sleep(1)
                status = self.check_order_status(order_id)
                return status.lower() in ['complete', 'open', 'pending', 'filled']
            else:
                print(f"  ❌ Order API error: {response}")
            return False
        except Exception as e:
            print(f"  ❌ Order Exception: {e}")
            return False

    def find_value_balanced_strikes(self, atm_strike):
        """
        Find CE and PE strikes that have roughly equal premiums (to start balanced).
        Start at ATM +/- 200 (STRANGLE_WIDTH).
        If one side is significantly more expensive, move it further OTM until matched.
        """
        print(f"\n⚡ Balancing Strangle Premiums...")
        
        # Start with default width
        ce_strike = atm_strike + STRANGLE_WIDTH
        pe_strike = atm_strike - STRANGLE_WIDTH
        
        max_attempts = 10
        strike_step = 50  # Nifty strike interval
        
        for i in range(max_attempts):
            ce_token = self.get_strike_token(ce_strike, 'CE')
            pe_token = self.get_strike_token(pe_strike, 'PE')
            
            if not ce_token or not pe_token:
                print(f"  ⚠️ Could not find tokens for CE:{ce_strike} PE:{pe_strike}")
                break
                
            ce_ltp = data_store.get_ltp(ce_token)
            pe_ltp = data_store.get_ltp(pe_token)
            
            # If data missing, wait briefly
            if ce_ltp == 0 or pe_ltp == 0:
                print(f"  ⏳ Waiting for data... CE: {ce_ltp}, PE: {pe_ltp}")
                time.sleep(1)
                ce_ltp = data_store.get_ltp(ce_token)
                pe_ltp = data_store.get_ltp(pe_token)
            
            print(f"   Attempt {i+1}: CE {ce_strike} @ {ce_ltp} | PE {pe_strike} @ {pe_ltp}")
            
            if ce_ltp == 0 or pe_ltp == 0:
                print("  ❌ Data missing, using default offsets.")
                break
                
            # Check difference percentage
            diff_pct = abs(ce_ltp - pe_ltp) / max(ce_ltp, pe_ltp) * 100
            if diff_pct <= 10:  # Within 10% difference is good enough
                print(f"  ✅ Found balanced pair! Diff: {diff_pct:.1f}%")
                return ce_strike, pe_strike
            
            # Adjust the more expensive leg further OTM
            if ce_ltp > pe_ltp:
                ce_strike += strike_step
                print(f"  ⬇️ CE too expensive. Moving OTM to {ce_strike}")
            else:
                pe_strike -= strike_step
                print(f"  ⬇️ PE too expensive. Moving OTM to {pe_strike}")
            
            time.sleep(0.2)
            
        print(f"  ⚠️ Could not perfectly balance within {max_attempts} steps. Using best found.")
        return ce_strike, pe_strike

    # ==================== FSM STATE HANDLERS ====================

    def do_init(self, atm_strike):
        """INIT State: Enter initial positions."""
        print(f"\n{'='*60}")
        print(f"  📍 FSM STATE: {self.state.value}")
        print(f"{'='*60}")
        
        # Wait for WebSocket data BEFORE selecting strikes to ensure we have LTPs
        print(f"  ⏳ Waiting for WebSocket LTP data before strike selection...")
        max_wait = 30
        wait_start = time.time()
        while time.time() - wait_start < max_wait:
            # Check if we have ANY option data
            if any(v['ltp'] > 0 for k,v in data_store.tick_data.items() if k != str(self.nifty_token)):
                print(f"  ✅ WebSocket option data streaming...")
                break
            time.sleep(1)
        
        # Find balanced strikes
        ce_strike, pe_strike = self.find_value_balanced_strikes(atm_strike)
        
        ce_token = self.get_strike_token(ce_strike, 'CE')
        pe_token = self.get_strike_token(pe_strike, 'PE')
        
        if not ce_token or not pe_token:
            print(f"  ❌ Could not find tokens for {ce_strike} CE or {pe_strike} PE")
            self.transition_to(FSMState.EXIT, "TOKEN_NOT_FOUND")
            return
        
        print(f"\n  🚀 ENTERING STRANGLE: Short {ce_strike} CE & Short {pe_strike} PE")
        
        ce_symbol = self.options_map.get(ce_token, {}).get('symbol')
        pe_symbol = self.options_map.get(pe_token, {}).get('symbol')
        
        lot_size = self.get_cached_lot_size(ce_symbol)
        qty = lot_size * MIN_LOT_MULTIPLIER
        
        print(f"  ⚙️ FSM Guardrails: min_lot={MIN_LOT_MULTIPLIER}, max_lot={MAX_LOT_MULTIPLIER}, max_value=₹{MAX_TOTAL_TRADE_VALUE}")
        

        
        # Sell CE
        if self.place_order(ce_token, qty, "S", "INIT_CE"):
            self.positions['CE'] = {'token': ce_token, 'qty': -qty, 'strike': ce_strike, 'lots': MIN_LOT_MULTIPLIER}
        
        # Sell PE
        if self.place_order(pe_token, qty, "S", "INIT_PE"):
            self.positions['PE'] = {'token': pe_token, 'qty': -qty, 'strike': pe_strike, 'lots': MIN_LOT_MULTIPLIER}
        
        if 'CE' in self.positions and 'PE' in self.positions:
            self.transition_to(FSMState.BALANCED, "POSITIONS_ENTERED")
            self.running = True
        else:
            self.transition_to(FSMState.EXIT, "ENTRY_FAILED")

    def transition_to(self, new_state, trigger, details=None):
        """Transition FSM to a new state with logging."""
        old_state = self.state
        self.log_state_transition(old_state, new_state, trigger, details)
        self.state = new_state

    def do_balanced(self, values):
        """BALANCED State: Passive monitoring (Tight 30% Threshold)."""
        imbalance = self.calculate_imbalance(values['ce_value'], values['pe_value'])
        threshold = STATE_THRESHOLDS["BALANCED"]
        
        # Calculate MTM (Realized + Unrealized)
        mtm = self.calculate_total_mtm()
        mtm_str = f"₹{mtm:,.2f}"

        # Get Nifty Data
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        nifty_chg = data_store.get_change(self.nifty_token)
        
        # Get OI Stats
        atm_strike = round(nifty_ltp / 50) * 50
        oi_stats = self.monitor_open_interest(atm_strike)
        
        display_msg = f"  📊 [BALANCED] CE: ₹{values['ce_value']:.0f} | PE: ₹{values['pe_value']:.0f} | Imbalance: {imbalance:.1f}% | MTM: {mtm_str} | Nifty: {nifty_ltp:.2f} ({nifty_chg:+.2f}%) {oi_stats}"
        print(display_msg)
        logger.info(display_msg)
        
        # Calculate absolute difference
        abs_diff = abs(values['ce_value'] - values['pe_value'])
        
        # Hybrid Threshold: Must exceed BOTH percentage AND absolute threshold
        pct_exceeded = imbalance > threshold
        abs_exceeded = abs_diff > MIN_ABS_DIFF_THRESHOLD
        
        if pct_exceeded and abs_exceeded:
            # Check cooldown
            if time.time() - self.last_adjustment_time < COOLDOWN_SECONDS:
                remaining = COOLDOWN_SECONDS - (time.time() - self.last_adjustment_time)
                print(f"  ⏳ Cooldown: {remaining:.0f}s remaining")
                return
            
            self.transition_to(FSMState.REBALANCE_REDUCE, f"IMBALANCE_{imbalance:.1f}%_DIFF_{abs_diff:.0f}", {
                'ce_value': values['ce_value'], 'pe_value': values['pe_value']
            })
            self.do_rebalance_reduce(values)
        elif pct_exceeded and not abs_exceeded:
            print(f"  ⚠️ Imbalance {imbalance:.1f}% exceeds threshold but abs diff ₹{abs_diff:.0f} < ₹{MIN_ABS_DIFF_THRESHOLD:.0f} - Skipping")

    def do_rebalance_reduce(self, values):
        """REBALANCE_REDUCE State: Reduce dominant leg."""
        print(f"\n  📍 FSM STATE: {self.state.value}")
        
        dominant = self.get_dominant_side(values['ce_value'], values['pe_value'])
        weaker = 'PE' if dominant == 'CE' else 'CE'
        
        dominant_pos = self.positions[dominant]
        lot_size = self.get_cached_lot_size(self.options_map[dominant_pos['token']]['symbol'])
        current_lots = dominant_pos.get('lots', abs(dominant_pos['qty']) // lot_size)
        
        print(f"  ⚖️ Dominant: {dominant} ({current_lots} lots) | Weaker: {weaker}")
        
        # Check if we can reduce (need at least 2 lots to reduce by 1)
        if current_lots <= 1:
            print(f"  ⚠️ Dominant leg at minimum (1 lot). Escalating to EXPAND...")
            self.previous_dominant = dominant  # Track this as the driving force
            
            if self.allow_expand:
                self.transition_to(FSMState.REBALANCE_EXPAND, "CANNOT_REDUCE_FURTHER")
                self.do_rebalance_expand(values)
            else:
                self.transition_to(FSMState.MONITOR, "EXPAND_EXHAUSTED")
            return
        
        # Calculate reduction
        reduction_lots = 1  # Reduce by 1 lot at a time (incremental)
        reduction_qty = reduction_lots * lot_size
        
        print(f"  📉 REDUCING: BUY {reduction_qty} x {self.options_map[dominant_pos['token']]['symbol']}")
        
        success = self.place_order(dominant_pos['token'], reduction_qty, "B", "REDUCE")
        
        if success:
            with self.lock:
                self.positions[dominant]['qty'] += reduction_qty  # Adding to negative = reducing
                self.positions[dominant]['lots'] = current_lots - reduction_lots
            
            self.reduce_count += 1
            self.last_adjustment_time = time.time()
            self.previous_dominant = dominant
            
            self.log_rebalance("REDUCE", dominant, reduction_qty, values)
            
            # Fetch updated values for check
            new_values = self.get_position_values()
            
            # Check if balanced now
            if new_values:
                new_imbalance = self.calculate_imbalance(new_values['ce_value'], new_values['pe_value'])
                # Use REDUCE state threshold (50%) for immediate check
                threshold = STATE_THRESHOLDS["REBALANCE_REDUCE"]
                print(f"  ✅ Post-reduce imbalance: {new_imbalance:.1f}% (Limit: {threshold}%)")
                
                if new_imbalance <= threshold:
                    self.transition_to(FSMState.BALANCED, "BALANCE_RESTORED")
                else:
                    # Still imbalanced - stay in REDUCE state for next cycle
                    print(f"  ⚠️ Still imbalanced > {threshold}%. Will re-evaluate.")
                    self.transition_to(FSMState.BALANCED, "PARTIAL_REBALANCE")
        else:
            print(f"  ❌ Reduce order failed!")
            self.transition_to(FSMState.BALANCED, "ORDER_FAILED")

    def do_rebalance_expand(self, values):
        """REBALANCE_EXPAND State: Expand weaker leg (ONE TIME ONLY)."""
        print(f"\n  📍 FSM STATE: {self.state.value}")
        
        if not self.allow_expand:
            print(f"  ❌ Expansion already used! Moving to MONITOR.")
            self.transition_to(FSMState.MONITOR, "EXPAND_ALREADY_USED")
            return
        
        dominant = self.get_dominant_side(values['ce_value'], values['pe_value'])
        weaker = 'PE' if dominant == 'CE' else 'CE'
        
        weaker_pos = self.positions[weaker]
        lot_size = self.get_cached_lot_size(self.options_map[weaker_pos['token']]['symbol'])
        current_lots = weaker_pos.get('lots', abs(weaker_pos['qty']) // lot_size)
        
        # Check guardrails
        if current_lots >= MAX_LOT_MULTIPLIER:
            print(f"  ⚠️ Weaker leg at MAX_LOT ({MAX_LOT_MULTIPLIER}). Cannot expand.")
            self.allow_expand = False
            self.transition_to(FSMState.MONITOR, "MAX_LOT_REACHED")
            return
        
        # Check total value limit
        total_value = values['ce_value'] + values['pe_value']
        weaker_ltp = values['ce_ltp'] if weaker == 'CE' else values['pe_ltp']
        expansion_value = lot_size * weaker_ltp
        
        if total_value + expansion_value > MAX_TOTAL_TRADE_VALUE:
            print(f"  ⚠️ Expansion would breach MAX_TOTAL_TRADE_VALUE. Cannot expand.")
            self.allow_expand = False
            self.transition_to(FSMState.MONITOR, "MAX_VALUE_BREACH")
            return
        
        # Expand weaker leg
        expansion_lots = 1
        expansion_qty = expansion_lots * lot_size
        
        print(f"  📈 EXPANDING: SELL {expansion_qty} x {self.options_map[weaker_pos['token']]['symbol']}")
        
        success = self.place_order(weaker_pos['token'], expansion_qty, "S", "EXPAND")
        
        if success:
            with self.lock:
                self.positions[weaker]['qty'] -= expansion_qty  # Subtracting from negative = increasing short
                self.positions[weaker]['lots'] = current_lots + expansion_lots
            
            self.allow_expand = False  # ONE TIME ONLY
            self.last_adjustment_time = time.time()
            
            self.log_rebalance("EXPAND", weaker, expansion_qty, values)
            
            # Check if balanced
            # Check if balanced
            new_values = self.get_position_values()
            if new_values:
                new_imbalance = self.calculate_imbalance(new_values['ce_value'], new_values['pe_value'])
                # Use EXPAND state threshold (50%)
                threshold = STATE_THRESHOLDS["REBALANCE_EXPAND"]
                print(f"  ✅ Post-expand imbalance: {new_imbalance:.1f}% (Limit: {threshold}%)")
                
                # TRANSITION TO POST_EXPAND STATE (Prevent immediate churn)
                self.transition_to(FSMState.BALANCED_POST_EXPAND, "EXPANSION_COMPLETE")

        else:
            print(f"  ❌ Expand order failed! Moving to MONITOR.")
            self.allow_expand = False
            self.transition_to(FSMState.MONITOR, "EXPAND_FAILED")

    def do_balanced_post_expand(self, values):
        """BALANCED_POST_EXPAND: Stabilize with wider tolerance (50%)."""
        imbalance = self.calculate_imbalance(values['ce_value'], values['pe_value'])
        threshold = STATE_THRESHOLDS["BALANCED_POST_EXPAND"]
        
        print(f"  🛡️ [POST_EXPAND] CE: ₹{values['ce_value']:.0f} | PE: ₹{values['pe_value']:.0f} | Imbalance: {imbalance:.1f}% (Limit: {threshold}%)")
        
        if imbalance > threshold:
            print(f"  ⚠️ Imbalance > {threshold}% in POST_EXPAND. Escalating to MONITOR.")
            self.transition_to(FSMState.MONITOR, "POST_EXPAND_RISK_BREACH")
        elif imbalance <= STATE_THRESHOLDS["BALANCED"]:
            # If we are back within strict limits, return to normal operation
            print(f"  ✅ Stabilized within {STATE_THRESHOLDS['BALANCED']}%. Returning to BALANCED.")
            self.transition_to(FSMState.BALANCED, "STABILIZED")

    def do_monitor(self, values):
        """MONITOR State: Strict observation (Tight 30%)."""
        imbalance = self.calculate_imbalance(values['ce_value'], values['pe_value'])
        current_dominant = self.get_dominant_side(values['ce_value'], values['pe_value'])
        threshold = STATE_THRESHOLDS["MONITOR"]
        
        print(f"  👁️ [MONITOR] CE: ₹{values['ce_value']:.0f} | PE: ₹{values['pe_value']:.0f} | Imbalance: {imbalance:.1f}% (Limit: {threshold}%)")
        print(f"     Flags: allow_expand={self.allow_expand}, allow_reverse={self.allow_reverse_rebalance}")
        print(f"     Previous dominant: {self.previous_dominant}, Current dominant: {current_dominant}")
        
        if imbalance <= threshold:
            print(f"  ✅ Balanced (within {threshold}%) in MONITOR state.")
            return
        
        # Check for reversal
        if self.previous_dominant and current_dominant != self.previous_dominant:
            print(f"  🔄 REVERSAL DETECTED: {self.previous_dominant} → {current_dominant}")
            
            if self.allow_reverse_rebalance:
                # Check cooldown
                if time.time() - self.last_adjustment_time < COOLDOWN_SECONDS:
                    remaining = COOLDOWN_SECONDS - (time.time() - self.last_adjustment_time)
                    print(f"  ⏳ Cooldown: {remaining:.0f}s remaining")
                    return
                
                self.do_reversal_rebalance(values, current_dominant)
                return
        
        # Imbalance persists with no reversal allowed
        if imbalance > threshold and not self.allow_reverse_rebalance:
            print(f"  ⚠️ Persistent imbalance after reversal. Triggering EXIT.")
            self.transition_to(FSMState.EXIT, "POST_REVERSAL_IMBALANCE")
            self.exit_reason = ExitReason.POST_MONITOR_IMBALANCE
            self.do_exit()

    def do_reversal_rebalance(self, values, new_dominant):
        """One-time reversal rebalance in MONITOR state."""
        print(f"\n  🔄 REVERSAL REBALANCE (ONE TIME)")
        
        # The new weaker leg (previously dominant, now losing) should be expanded
        weaker = 'PE' if new_dominant == 'CE' else 'CE'
        
        weaker_pos = self.positions[weaker]
        lot_size = self.get_cached_lot_size(self.options_map[weaker_pos['token']]['symbol'])
        current_lots = weaker_pos.get('lots', abs(weaker_pos['qty']) // lot_size)
        
        # Check guardrails
        if current_lots >= MAX_LOT_MULTIPLIER:
            print(f"  ⚠️ Cannot expand {weaker} - at MAX_LOT")
            self.allow_reverse_rebalance = False
            return
        
        # Expand weaker (previously dominant) leg
        expansion_qty = lot_size
        
        print(f"  📈 REVERSAL EXPAND: SELL {expansion_qty} x {self.options_map[weaker_pos['token']]['symbol']}")
        
        success = self.place_order(weaker_pos['token'], expansion_qty, "S", "REVERSAL")
        
        if success:
            with self.lock:
                self.positions[weaker]['qty'] -= expansion_qty
                self.positions[weaker]['lots'] = current_lots + 1
            
            self.allow_reverse_rebalance = False  # ONE TIME ONLY
            self.last_adjustment_time = time.time()
            self.previous_dominant = new_dominant
            
            self.log_rebalance("REVERSAL", weaker, expansion_qty, values)
            print(f"  ✅ Reversal rebalance complete. No further rebalancing allowed.")
        else:
            print(f"  ❌ Reversal order failed!")
            self.allow_reverse_rebalance = False

    def do_exit(self):
        """EXIT State: Square off all positions."""
        print(f"\n{'='*60}")
        print(f"  🛑 FSM STATE: {self.state.value}")
        print(f"  Exit Reason: {self.exit_reason.value}")
        print(f"{'='*60}")
        
        self.running = False
        
        # Square off CE
        if 'CE' in self.positions:
            ce_pos = self.positions['CE']
            if ce_pos['qty'] < 0:  # Short position
                self.place_order(ce_pos['token'], abs(ce_pos['qty']), "B", "EXIT_CE")
        
        # Square off PE
        if 'PE' in self.positions:
            pe_pos = self.positions['PE']
            if pe_pos['qty'] < 0:  # Short position
                self.place_order(pe_pos['token'], abs(pe_pos['qty']), "B", "EXIT_PE")
        
        print(f"\n  📋 FSM LOG SUMMARY:")
        print(f"     State transitions: {len(self.state_log)}")
        print(f"     Rebalance actions: {len(self.rebalance_log)}")
        pass

    def monitor_open_interest(self, atm_strike):
        """
        Analyze Open Interest for ATM +/- 6 strikes.
        Returns formatted OI stats string.
        """
        try:
            start_strike = atm_strike - (6 * 50)
            end_strike = atm_strike + (6 * 50)
            
            ce_oi_sum = 0
            pe_oi_sum = 0
            
            for token, info in self.options_map.items():
                s = info['strike']
                if start_strike <= s <= end_strike:
                    oi = data_store.get_oi(token)
                    if info['type'] == 'CE':
                        ce_oi_sum += oi
                    elif info['type'] == 'PE':
                        pe_oi_sum += oi
            
            diff = pe_oi_sum - ce_oi_sum
            
            # Return formatted string instead of printing
            return f"| OI CE: {ce_oi_sum:,} | PE: {pe_oi_sum:,} | Diff: {diff:+,}"
            
        except Exception as e:
            return f"| OI Error: {e}"

    def log_rebalance(self, action_type, side, qty, values):
        """Log a rebalance action."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action_type,
            'side': side,
            'qty': qty,
            'ce_value': round(values['ce_value'], 2),
            'pe_value': round(values['pe_value'], 2),
            'imbalance': round(self.calculate_imbalance(values['ce_value'], values['pe_value']), 2)
        }
        self.rebalance_log.append(entry)
        print(f"  📝 LOG: {json.dumps(entry)}")

    # ==================== MAIN LOOP ====================

    def run(self):
        """Main FSM monitoring loop."""
        print(f"\n  👀 FSM Monitoring Started...")
        print(f"  ⚙️ Guardrails: thresholds={STATE_THRESHOLDS}, cooldown={COOLDOWN_SECONDS}s, DRY_RUN={DRY_RUN}")
        
        while self.running and self.state != FSMState.EXIT:
            time.sleep(2)
            
            try:
                values = self.get_position_values()
                if not values:
                    # Show heartbeat so user knows loop is running
                    ce_token = self.positions.get('CE', {}).get('token', 'N/A')
                    pe_token = self.positions.get('PE', {}).get('token', 'N/A')
                    ce_ltp = data_store.get_ltp(ce_token) if ce_token != 'N/A' else 0
                    pe_ltp = data_store.get_ltp(pe_token) if pe_token != 'N/A' else 0
                    print(f"  ⏳ Waiting for LTP... CE({ce_token}): {ce_ltp} | PE({pe_token}): {pe_ltp}")
                    print(f"  ⏳ Waiting for LTP... CE({ce_token}): {ce_ltp} | PE({pe_token}): {pe_ltp}")
                    continue
                
                # --- TIME EXIT CHECK ---
                try:
                    current_time = datetime.now().time()
                    exit_time = datetime.strptime(AUTO_EXIT_TIME_STR, "%H:%M").time()
                    
                    if current_time >= exit_time:
                        print(f"  ⏰ TIME EXIT TRIGGERED: Current time {current_time.strftime('%H:%M:%S')} >= {AUTO_EXIT_TIME_STR}")
                        self.transition_to(FSMState.EXIT, "TIME_EXIT")
                        self.exit_reason = ExitReason.TIME_EXIT
                        self.do_exit()
                        break
                except Exception as e:
                    print(f"  ⚠️ Time Check Error: {e}")
                # -----------------------

                # --- WS TIMEOUT CHECK ---
                time_since_last_packet = time.time() - data_store.last_activity
                if time_since_last_packet > 15:
                    print(f"  🚨 CRITICAL: No WebSocket data for {int(time_since_last_packet)}s (>15s). Force Exit!")
                    self.transition_to(FSMState.EXIT, "WS_TIMEOUT_DISCONNECT")
                    self.exit_reason = ExitReason.MANUAL # Treat as risk exit
                    self.do_exit()
                    break
                # ------------------------
                
                # --- Deleted OI Monitoring from here (Moving to end) ---
                
                # --- GLOBAL MTM CHECK & TSL ---
                mtm = self.calculate_total_mtm()
                
                # Update High Watermark
                if mtm > self.max_mtm_high:
                    self.max_mtm_high = mtm
                
                # Calculate Dynamic SL
                current_sl_limit = -abs(MAX_MTM_LOSS)  # Default static SL
                tsl_status = ""
                
                if self.max_mtm_high >= TSL_TRIGGER_2:
                    # Level 2 + Trailing: Base 3000 + (steps * 500)
                    steps = int((self.max_mtm_high - TSL_TRIGGER_2) // TSL_STEP_TRIGGER)
                    current_sl_limit = TSL_SL_2 + (steps * TSL_STEP_MOVE)
                    tsl_status = f"(🔒 TSL Level 2+ | Max: {self.max_mtm_high:.0f})"
                elif self.max_mtm_high >= TSL_TRIGGER_1:
                    # Level 1: Breakeven
                    current_sl_limit = TSL_SL_1
                    tsl_status = f"(🛡️ TSL Level 1 | Max: {self.max_mtm_high:.0f})"

                if mtm >= TARGET_MTM_PROFIT:
                    print(f"  🎯 TARGET HIT: MTM ₹{mtm:.2f} >= ₹{TARGET_MTM_PROFIT}")
                    self.transition_to(FSMState.EXIT, "MTM_TARGET_HIT")
                    self.exit_reason = ExitReason.TARGET_HIT
                    self.do_exit()
                    break
                elif mtm <= current_sl_limit:
                    self.sl_confirm_count += 1
                    print(f"  ⚠️ SL BREACH DETECTED: MTM ₹{mtm:.2f} <= ₹{current_sl_limit:.0f}. Confirming {self.sl_confirm_count}/3...")
                    
                    if self.sl_confirm_count >= 3:
                        print(f"  🛑 SL HIT CONFIRMED: MTM ₹{mtm:.2f} <= ₹{current_sl_limit:.0f} {tsl_status}")
                        self.transition_to(FSMState.EXIT, "STOP_LOSS_HIT")
                        self.exit_reason = ExitReason.STOP_LOSS_HIT
                        self.do_exit()
                        break
                else:
                    # Reset counter if MTM recovers
                    if self.sl_confirm_count > 0:
                        print(f"  ✅ SL Breach Recovered. Counter reset.")
                    self.sl_confirm_count = 0
                # ------------------------
                
                # Execute logic based on current state
                state = self.state
                
                if state == FSMState.BALANCED:
                    self.do_balanced(values)
                elif state == FSMState.REBALANCE_REDUCE:
                    self.do_rebalance_reduce(values)
                elif state == FSMState.REBALANCE_EXPAND:
                    self.do_rebalance_expand(values)
                elif state == FSMState.BALANCED_POST_EXPAND:
                    self.do_balanced_post_expand(values)
                elif state == FSMState.MONITOR:
                    self.do_monitor(values)
                elif state == FSMState.EXIT:
                    break
                    
            except Exception as e:
                print(f"  ❌ FSM Loop Error: {e}")
                time.sleep(5)
                import traceback
                traceback.print_exc()
        
        if self.state != FSMState.EXIT:
            self.exit_reason = ExitReason.MANUAL
            self.transition_to(FSMState.EXIT, "LOOP_ENDED")
            self.do_exit()










































# --- Helper Functions ---

def authenticate():
    print("🔐 Authenticating with Kotak Neo API...")
    client = NeoAPI(environment='prod', consumer_key=CONSUMER_KEY)
    client.totp_login(mobile_number=MOBILE_NUMBER, ucc=UCC, totp=pyotp.TOTP(TOTP).now())
    client.totp_validate(mpin=MPIN)
    print("✅ Authentication successful!")
    return client

def download_fresh_master(client):
    try:
        print("  Downloading fresh nse_fo.csv...")
        client.scrip_master(exchange_segment="nse_fo")
        print("  Downloading fresh nse_cm.csv...")
        client.scrip_master(exchange_segment="nse_cm")
    except Exception as e: print(f"  Error downloading: {e}")

def load_master_data(client):
    segments = ['nse_fo.csv', 'nse_cm.csv']
    if not all(os.path.exists(f) for f in segments):
        download_fresh_master(client)
    
    dfs = []
    for path in segments:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, low_memory=False)
                df = df.rename(columns=lambda x: x.strip())
                dfs.append(df)
            except: pass
    return pd.concat(dfs, ignore_index=True) if dfs else None

def get_lot_size(master_df, full_symbol):
    """Get lot size for the given symbol from master data."""
    try:
        df = master_df
        # Use strip() to handle potential whitespace
        df = df[df['pTrdSymbol'].astype(str).str.strip().str.upper() == full_symbol.strip().upper()]
        if len(df) >= 1:
            # Check for various possible column names for Lot Size, prioritizing lLotSize
            possible_cols = ['lLotSize', 'lLotsize', 'pLotSize', 'pLotSize;']
            for col in possible_cols:
                if col in df.columns:
                    return int(df[col].iloc[0])
            print(f"  Lot size column not found for {full_symbol}")
            return 75 # Default fallback
        return 75 
    except Exception as e:
        print(f"  Error getting lot size: {e}")
        return 75

def get_nifty_spot_token(master_df):
    try:
        df = master_df[master_df['pExchSeg'].str.lower() == 'nse_cm']
        df = df[df['pTrdSymbol'].str.upper() == 'NIFTY']
        if len(df) > 0:
            token = int(df['pSymbol'].iloc[0])
            print(f"  DEBUG: Found Nifty token: {token}")
            return token
        else:
            print(f"  DEBUG: No NIFTY found in nse_cm segment")
            # Try alternative: look for 'Nifty 50' or similar
            df2 = master_df[master_df['pExchSeg'].str.lower() == 'nse_cm']
            nifty_rows = df2[df2['pTrdSymbol'].str.contains('NIFTY', case=False, na=False)]
            if len(nifty_rows) > 0:
                print(f"  DEBUG: Found alternative Nifty rows: {nifty_rows['pTrdSymbol'].head().tolist()}")
            return None
    except Exception as e:
        print(f"  DEBUG: get_nifty_spot_token error: {e}")
        return None

def get_nifty_spot_price(client, nifty_token):
    if not nifty_token:
        print(f"  DEBUG: nifty_token is None")
        return None
    try:
        print(f"  DEBUG: Calling quotes API for token {nifty_token}...")
        resp = client.quotes(instrument_tokens=[{"instrument_token": str(nifty_token), "exchange_segment": "nse_cm"}], quote_type="ltp")
        print(f"  DEBUG: Quotes response: {resp}")
        if isinstance(resp, dict):
            data = resp.get('data', resp.get('message', resp))
            if isinstance(data, list) and len(data):
                ltp = float(data[0].get('ltp', 0))
                print(f"  DEBUG: Extracted LTP: {ltp}")
                return ltp if ltp > 0 else None
    except Exception as e:
        print(f"  DEBUG: get_nifty_spot_price error: {e}")
    return None

def parse_expiry_from_symbol(trading_symbol):
    import re
    sym = trading_symbol.upper()
    # Weekly: NIFTY<YY><M><DD><STRIKE><Type>
    m = re.match(r'NIFTY(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)', sym)
    if m:
        try:
            y, m_char, d = int(m.group(1)), m.group(2), int(m.group(3))
            months = {'1':1,'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'O':10,'N':11,'D':12}
            return datetime(2000+y, months[m_char], d)
        except: pass
    # Monthly
    m = re.match(r'NIFTY(\d{2})([A-Z]{3})(\d+)(CE|PE)', sym)
    if m:
        try:
            d, m_str = int(m.group(1)), m.group(2)
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            now = datetime.now()
            dt = datetime(now.year, months[m_str], d)
            if dt < now: dt = datetime(now.year+1, months[m_str], d)
            return dt
        except: pass
    return None

def get_nearest_expiry(master_df):
    df = master_df[(master_df['pExchSeg'] == 'nse_fo') & (master_df['pSymbolName'] == 'NIFTY')]
    df = df[df['pOptionType'].isin(['CE', 'PE'])].copy()
    df['expiry_dt'] = df['pTrdSymbol'].apply(parse_expiry_from_symbol)
    df = df[df['expiry_dt'] >= datetime.now()]
    return df['expiry_dt'].min() if len(df) else None

def get_all_option_tokens(master_df, expiry_dt):
    """Get ALL option tokens for the expiry (to allow flexible rolling)."""
    df = master_df[(master_df['pExchSeg'] == 'nse_fo') & (master_df['pSymbolName'] == 'NIFTY')]
    df = df.copy()
    df['expiry_dt'] = df['pTrdSymbol'].apply(parse_expiry_from_symbol)
    df = df[df['expiry_dt'].dt.date == expiry_dt.date()]
    
    tokens = []
    # Build map
    options_map = {}
    
    for _, row in df.iterrows():
        try:
            strike = float(row['dStrikePrice;']) / 100.0
            token = int(row['pSymbol'])
            opt_type = row['pOptionType']
            sym = row['pTrdSymbol']
            
            item = {'token': token, 'strike': strike, 'type': opt_type, 'symbol': sym}
            tokens.append(item)
            options_map[token] = item
        except: pass
        
    return tokens, options_map

# --- WebSocket ---

def on_message(message):
    try:
        if isinstance(message, str): message = json.loads(message)
        ticks = message.get('data', []) if isinstance(message, dict) else message
        
        for tick in ticks:
            token = str(tick.get('instrument_token', tick.get('tk', '')))
            ltp = float(tick.get('ltp', 0) or 0)
            
            # Try to get percentage change 'nc' (Net Change %)
            pc = float(tick.get('nc', 0) or 0)
            
            # Extract Open Interest (Only if present in tick - preserve existing otherwise)
            if 'oi' in tick:
                oi = int(tick.get('oi', 0) or 0)
            else:
                # Preserve existing OI from data_store to avoid overwrite
                existing = data_store.tick_data.get(token, {})
                oi = existing.get('oi', 0)
            
            # Fallback: if nc missing, try calculating from close 'c'
            if pc == 0 and float(tick.get('c', 0) or 0) > 0:
                 close_p = float(tick.get('c', 0))
                 pc = ((ltp - close_p) / close_p) * 100
                 
            if token and ltp > 0:
                data_store.update(token, ltp, pc, oi)
    except: pass

# --- WebSocket Handler with Auto-Reconnect ---

subscription_list = [] # Store tokens globally for resubscription
last_nifty_token = None
reconnect_thread = None

def subscribe_tokens(client, tokens, nifty_token):
    """Subscribe to tokens (Nifty + Options)."""
    global subscription_list, last_nifty_token
    # Update global list for reconnections
    if tokens: subscription_list = tokens
    if nifty_token: last_nifty_token = nifty_token
    
    # Subscribe to Nifty index first
    print(f"  Subscribing to Nifty (token: {nifty_token})...")
    try:
        client.subscribe(
            instrument_tokens=[{"instrument_token": str(nifty_token), "exchange_segment": "nse_cm"}], 
            isIndex=False, 
            isDepth=False
        )
    except Exception as e:
        print(f"  ⚠️ Nifty subscription error: {e}")
    
    time.sleep(0.5)
    
    # Subscribe to options in batches
    batch_size = 25
    option_tokens = [t for t in subscription_list if isinstance(t, int)]
    
    for i in range(0, len(option_tokens), batch_size):
        batch = option_tokens[i:i+batch_size]
        subs = [{"instrument_token": str(t), "exchange_segment": "nse_fo"} for t in batch]
        try:
            client.subscribe(instrument_tokens=subs, isIndex=False, isDepth=False)
            print(f"  Subscribed batch {i//batch_size + 1}: {len(subs)} tokens")
        except Exception as e:
            print(f"  ⚠️ Subscription error: {e}")
        time.sleep(0.3)
    
    print(f"  ✅ Total {len(option_tokens)} option tokens subscribed")

def attempt_reconnect(client):
    """Reconnection Loop."""
    global reconnect_thread
    print("  🔄 Attempting to reconnect WebSocket in 5s...")
    time.sleep(5)
    
    try:
        # Re-subscribe using global tokens
        if last_nifty_token and subscription_list:
            print("  ⚡ Re-subscribing to feeds...")
            subscribe_tokens(client, subscription_list, last_nifty_token)
        else:
            print("  ⚠️ No tokens to resubscribe.")
    except Exception as e:
        print(f"  ❌ Reconnect failed: {e}")
        # Retry again
        reconnect_thread = threading.Thread(target=attempt_reconnect, args=(client,), daemon=True)
        reconnect_thread.start()

# Callbacks
def on_error(e): 
    print(f"❌ WS Error: {e}")
    # Trigger reconnect on error if not already running
    # (Checking reconnect_thread logic can be complex, for now simple trigger)

def on_close(m): 
    print(f"🔌 WS Closed: {m}")
    # Trigger reconnect
    global reconnect_thread, client_instance
    if client_instance:
         reconnect_thread = threading.Thread(target=attempt_reconnect, args=(client_instance,), daemon=True)
         reconnect_thread.start()

def on_open(m): print(f"🟢 WS Connected")

client_instance = None # Global reference for callbacks

def start_websocket(client, tokens, nifty_token):
    """Initialize WebSocket with proper callback setup and subscription."""
    global client_instance
    client_instance = client
    
    # Set callbacks
    client.on_message = on_message
    client.on_error = on_error
    client.on_close = on_close
    client.on_open = on_open
    
    # Start subscription in background thread
    threading.Thread(target=subscribe_tokens, args=(client, tokens, nifty_token), daemon=True).start()

# --- Main ---

def main():
    print("="*60 + "\n   FSM ALGO STRATEGY - Value-Balanced CE/PE\n" + "="*60 + "\n")
    
    client = authenticate()
    print("\n📂 Loading master data...")
    master_df = load_master_data(client)
    if master_df is None: return

    # Get Nifty token from master data
    print("\n🔍 Getting Nifty Token...")
    nifty_token = get_nifty_spot_token(master_df)
    if not nifty_token:
        print("  ❌ Could not find Nifty token in master data")
        return
    print(f"  ✅ Nifty token: {nifty_token}")
    
    # Get expiry first (doesn't need spot price)
    print("\n📅 Finding Expiry...")
    expiry = get_nearest_expiry(master_df)
    print(f"  Expiry: {expiry.date()}")
    
    # Load option chain (need this before subscribing)
    print("\n🔗 Loading Option Chain...")
    all_tokens_list, options_map = get_all_option_tokens(master_df, expiry)
    print(f"  Loaded {len(all_tokens_list)} contracts")
    
    # Collect all tokens to subscribe (Nifty + all options around a wide range)
    # Since we don't know ATM yet, subscribe to a wide range
    sub_tokens = [nifty_token]
    for t in all_tokens_list:
        sub_tokens.append(t['token'])
    
    # Start WebSocket FIRST and subscribe to Nifty
    print(f"\n🔌 Starting WebSocket...")
    start_websocket(client, sub_tokens, nifty_token)
    
    # Wait for Nifty spot price from WebSocket
    print(f"\n⏳ Waiting for Nifty spot price from WebSocket...")
    max_wait = 30
    wait_start = time.time()
    spot_price = None
    
    while time.time() - wait_start < max_wait:
        ltp = data_store.get_ltp(nifty_token)
        if ltp > 0:
            spot_price = ltp
            print(f"  ✅ Nifty Spot via WebSocket: {spot_price}")
            break
        print(f"  ⏳ Waiting... Nifty LTP: {ltp}")
        time.sleep(2)
    
    if not spot_price:
        print(f"  ❌ Could not get Nifty spot price from WebSocket within {max_wait}s")
        print(f"  💡 Check WebSocket connection and try again")
        return
    
    # Calculate ATM strike
    atm_strike = round(spot_price / NIFTY_STRIKE_INTERVAL) * NIFTY_STRIKE_INTERVAL
    print(f"  ATM Strike: {atm_strike}")
    
    # Initialize FSM Strategy
    strategy = FSMStrategy(client, master_df, nifty_token, expiry, options_map)
    
    # Wait a bit more for option LTPs to arrive
    print("\n⏳ Waiting for option LTPs...")
    time.sleep(3)
    
    # Enter positions via FSM
    strategy.do_init(atm_strike)
    
    # Start FSM monitoring loop
    threading.Thread(target=strategy.run, daemon=True).start()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: print("\n👋 Exiting...")

if __name__ == "__main__":
    main()

