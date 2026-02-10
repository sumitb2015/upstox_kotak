"""
Algo Strategy: Aggressive Directional Option Selling

Logic:
1. Track 5-minute NIFTY spot candles with EMA(9) and EMA(20)
2. SHORT CE (bearish bias) or SHORT PE (bullish bias) based on tight entry rules
3. Intrabar entry on retracement to EMA9
4. Tight spot-based SL (swing high/low + 10 points)
5. Re-entry mechanism with quantity reduction
6. Comprehensive risk controls (daily loss limit, time restrictions)

Purpose: Aggressive premium selling with tight NIFTY tracking
"""

import os
import sys
import time
from datetime import datetime, timedelta
from enum import Enum
import logging
from collections import deque

# Add parent directory to path for library imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib.broker import BrokerClient
from lib.data_store import DataStore
from lib.websocket_client import WebSocketClient
from lib.order_manager import OrderManager
from lib.utils import get_lot_size, round_to_strike_interval, setup_strategy_logger
from lib.trading_utils import (
    get_instrument_token,
    get_nearest_expiry,
    get_strike_token,
    calculate_ema,
    get_atm_strike,
    get_otm_strike,
    find_swing_high,
    find_swing_low
)
from lib.time_utils import should_auto_exit, is_trading_time

# Configure Logging using library helper
logger = setup_strategy_logger("Aggressive_Directional", "algo_strategy_aggressive.log")

# Note: BrokerClient loads credentials from .env automatically

# Strategy Parameters
LOT_MULTIPLIER = 1              # Base lot multiplier
EMA_FAST = 9                    # Fast EMA period
EMA_SLOW = 20                   # Slow EMA period
SWING_LOOKBACK = 10             # Candles to look back for swing points
SPOT_SL_BUFFER = 10             # Points beyond swing high/low for SL
PREMIUM_SL_PCT = 0.30           # 30% loss on option premium
PROFIT_DECAY_PCT = 0.20         # 20% premium decay target (lowered from 25%)
TRAILING_SL_TRIGGER_PCT = 0.15  # Start trailing at 15% profit
EMA_SEPARATION_THRESHOLD = 8    # Min points validation (Reduced to 8)
REENTRY_QTY_REDUCTION = 0.30    # 30% quantity reduction on re-entry
MAX_REENTRIES = 2               # Maximum re-entries per side

# Risk Management (Fixed Amounts - Independent of Other Strategies)
MAX_LOSS_PER_TRADE = 2500       # Increased from 500 (~33 pts on 1 lot)
MAX_DAILY_LOSS = 5000           # Increased from 1250

# Time Controls
TRADING_START_TIME = "09:20"    # Start trading after market stabilizes
TRADING_END_TIME = "15:15"      # No new trades in last 15 min
AUTO_EXIT_TIME = "15:00"        # Exit all positions by 3 PM
DRY_RUN = False                 # Set to True for simulation

# Global State (using library components)
broker = None
data_store = None
ws_client = None
order_mgr = None


class State(Enum):
    """FSM States for strategy"""
    WAIT = "WAIT"
    DIRECTION_CONFIRMED = "DIRECTION_CONFIRMED"
    SHORT_OPTION = "SHORT_OPTION"
    POSITION_EXIT = "POSITION_EXIT"


# Reusable functions now imported from lib.trading_utils


class AggressiveDirectionalStrategy:
    """Aggressive directional option selling strategy."""
    
    def __init__(self):
        global broker, data_store, ws_client, order_mgr
        
        # Initialize library components
        broker = BrokerClient()
        broker.authenticate()
        broker.load_master_data()
        
        data_store = DataStore()
        ws_client = WebSocketClient(broker.client, data_store)
        order_mgr = OrderManager(broker.client, dry_run=DRY_RUN)
        
        self.broker = broker
        self.data_store = data_store
        self.ws_client = ws_client
        self.order_mgr = order_mgr
        
        self.nifty_token = get_instrument_token(broker, "Nifty 50", "nse_cm")
        self.expiry = get_nearest_expiry()
        
        # State management
        self.state = State.WAIT
        self.position = None  # {'type': 'CE'/'PE', 'token': ..., 'entry_spot': ..., 'qty': ..., 'entry_premium': ..., 'strike': ...}
        self.running = True
        
        # 1-min candle tracking
        self.candles = deque(maxlen=60)  # Store last 60 candles (1 hour)
        self.current_candle = None
        self.candle_start_time = None
        
        # EMA tracking
        self.ema9 = None
        self.ema20 = None
        
        # Swing points
        self.swing_high = None
        self.swing_low = None
        
        # Re-entry tracking
        self.reentry_count = 0
        self.last_position_type = None
        self.candles_since_exit = 0
        self.standdown_side = None  # 'CE' or 'PE' after 2 stops
        self.last_exit_reason = None
        self.last_status_time = 0  # For periodic status updates
        
        # Risk management - Isolated P&L tracking for this strategy only
        self.strategy_pnl = 0  # Tracks only this strategy's realized P&L
        self.max_daily_loss = MAX_DAILY_LOSS
        self.max_loss_per_trade = MAX_LOSS_PER_TRADE
        self.trailing_sl_price = None  # To track trailing SL level
        self.last_indicator_update = 0 # Track last yfinance update
        
        # Initialize Candles with Historical Data
        self.initialize_candles()
        
    def initialize_candles(self):
        """Fetch historical data to warm up indicators."""
        try:
            import pandas as pd
            print("  Fetching historical data (5d 1m) to warm up EMAs...")
            # Import yfinance if not globally imported
            import yfinance as yf
            df = yf.download("^NSEI", period="5d", interval="1m", progress=False)
            
            if df.empty:
                print("⚠️ No historical data found. Indicators will warm up live.")
                return

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Populate candles
            count = 0
            for idx, row in df.iterrows():
                try:
                    c = {
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
                    }
                    self.candles.append(c)
                    count += 1
                except: continue
                
            print(f"✅ Loaded {count} historical candles. EMAs ready.")
            
            # Explicitly Calculate Indicators (finalize_candle expects current_candle which is None)
            if len(self.candles) >= EMA_SLOW:
                closes = [c['close'] for c in self.candles]
                self.ema9 = calculate_ema(closes, EMA_FAST)
                self.ema20 = calculate_ema(closes, EMA_SLOW)
                
            self.update_swing_points()
            
        except Exception as e:
            print(f"⚠️ Historical data fetch failed: {e}")
    
    def check_ema_separation(self):
        """Ensure EMAs are separated enough to indicate trend (avoid chop)."""
        if self.ema9 is None or self.ema20 is None:
            return False
        return abs(self.ema9 - self.ema20) > EMA_SEPARATION_THRESHOLD
        
        if not self.nifty_token:
            print("❌ Cannot run strategy without Nifty token")
            self.running = False
    
    def on_message(self, message):
        """WebSocket message handler - delegated to ws_client."""
        self.ws_client.on_message(message)
    
    def on_error(self, error_message):
        logger.error(f"WS error: {error_message}")
    
    def on_close(self, message=None):
        print(f"WebSocket closed: {message}")
    
    def on_open(self, message=None):
        print("WebSocket opened")
    
    def start_websocket(self):
        """Start WebSocket in background thread."""
        self.broker.client.on_message = self.on_message
        self.broker.client.on_error = self.on_error
        self.broker.client.on_close = self.on_close
        self.broker.client.on_open = self.on_open
        
        # Subscribe to Nifty using ws_client
        print(f"  Subscribing to Nifty (token: {self.nifty_token})...")
        self.ws_client.subscribe([self.nifty_token], is_index=False, is_depth=False)
        
        time.sleep(2)
        print("✅ WebSocket started")
    
    def update_indicators(self):
        """Fetch latest data from yfinance and update indicators."""
        try:
            import pandas as pd
            # print("  Fetching latest data from yfinance...")
            import yfinance as yf
            # Fetch 5 days to ensure we have enough history even at market open
            df = yf.download("^NSEI", period="5d", interval="1m", progress=False)
            
            if df.empty:
                print("⚠️ YFinance returned empty data. Skipping update.")
                return

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Convert to list of dicts for compatibility
            # We only need the latest closes for EMA
            closes = df['Close'].tolist()
            
            # Check length (Safeguard)
            if len(closes) < EMA_SLOW:
                print(f"⚠️ Insufficient data points ({len(closes)}) from YFinance. Need {EMA_SLOW}.")
                return
                
            # Update EMAs
            self.ema9 = calculate_ema(closes, EMA_FAST)
            self.ema20 = calculate_ema(closes, EMA_SLOW)
            
            # Update Swing Points (High/Low of last 10 candles)
            if len(df) >= 10:
                last_10 = df.iloc[-10:]
                self.swing_high = float(last_10['High'].max())
                self.swing_low = float(last_10['Low'].min())
            
            # Store candles for logic (convert last 60 to dicts)
            # Only overwrite if we have valid data
            temp_candles = []
            for idx, row in df.iloc[-60:].iterrows(): # Keep last 60
                 try:
                    c = {
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'timestamp': idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
                    }
                    temp_candles.append(c)
                 except: continue
            
            if temp_candles:
                self.candles.clear()
                self.candles.extend(temp_candles)

        except Exception as e:
            print(f"⚠️ Indicator update failed: {e}")
    
    def update_swing_points(self):
        """Update swing high and swing low using proper local peaks/troughs."""
        if len(self.candles) < 5:  # Need at least 5 candles for proper swing detection
            return
        
        # Find swing high (local peak - higher than 2 candles before and after)
        swing_high_found = None
        for i in range(len(self.candles) - 3, 1, -1):  # Start from recent, go backwards
            candle = self.candles[i]
            # Check if this is a local peak
            if (candle['high'] > self.candles[i-1]['high'] and
                candle['high'] > self.candles[i-2]['high'] and
                candle['high'] > self.candles[i+1]['high'] and
                candle['high'] > self.candles[i+2]['high']):
                swing_high_found = candle['high']
                break
        
        # Find swing low (local trough - lower than 2 candles before and after)
        swing_low_found = None
        for i in range(len(self.candles) - 3, 1, -1):  # Start from recent, go backwards
            candle = self.candles[i]
            # Check if this is a local trough
            if (candle['low'] < self.candles[i-1]['low'] and
                candle['low'] < self.candles[i-2]['low'] and
                candle['low'] < self.candles[i+1]['low'] and
                candle['low'] < self.candles[i+2]['low']):
                swing_low_found = candle['low']
                break
        
        # Update swing points (keep previous if no new swing found)
        if swing_high_found is not None:
            self.swing_high = swing_high_found
        elif self.swing_high is None:
            # Fallback: use highest high if no swing detected yet
            self.swing_high = max(c['high'] for c in self.candles[-SWING_LOOKBACK:])
        
        if swing_low_found is not None:
            self.swing_low = swing_low_found
        elif self.swing_low is None:
            # Fallback: use lowest low if no swing detected yet
            self.swing_low = min(c['low'] for c in self.candles[-SWING_LOOKBACK:])
    
    def check_short_ce_entry(self):
        """Check if SHORT CE entry conditions are met (bearish bias)."""
        if self.ema9 is None or self.ema20 is None:
            return False
        
        # 1. EMA9 < EMA20 (bearish structure)
        if self.ema9 >= self.ema20:
            return False
        
        # 2. Check EMA Separation (avoid chop)
        if not self.check_ema_separation():
            return False
        
        return True
    
    def check_short_pe_entry(self):
        """Check if SHORT PE entry conditions are met (bullish bias)."""
        if self.ema9 is None or self.ema20 is None:
            return False
        
        # 1. EMA9 > EMA20 (bullish structure)
        if self.ema9 <= self.ema20:
            return False
        
        # 2. Check EMA Separation (avoid chop)
        if not self.check_ema_separation():
            return False
        
        return True
    
    def check_candle_break_trigger(self, direction):
        """Check if price breaks previous candle high/low (momentum trigger)."""
        if len(self.candles) < 1:
            return False
            
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        prev_candle = self.candles[-1]
        
        if direction == 'CE': # Short CE (Bearish)
            # Entry if Price breaks below previous candle LOW
            return nifty_ltp < prev_candle['low']
        else: # Short PE (Bullish)
            # Entry if Price breaks above previous candle HIGH
            return nifty_ltp > prev_candle['high']
    
    def calculate_trend_strength(self):
        """Calculate trend strength for strike selection."""
        if self.ema9 is None or self.ema20 is None:
            return 0
        
        return abs(self.ema9 - self.ema20) / self.ema20
    
    def select_strike(self, direction):
        """Select strike with dynamic OTM offset based on premium availability."""
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        atm_strike = round(nifty_ltp / 50) * 50
        
        MIN_PREMIUM = 15  # Minimum acceptable premium
        OFFSETS = [200, 150, 100, 50]  # Try progressively closer strikes
        
        for offset in OFFSETS:
            if direction == "CE":
                test_strike = atm_strike + offset
            else:  # PE
                test_strike = atm_strike - offset
            
            # Get token and check premium
            token, symbol = get_strike_token(test_strike, direction, self.expiry)
            if not token:
                continue
            
            # Subscribe to get LTP
            instrument_list = [{"instrument_token": str(token), "exchange_segment": "nse_fo"}]
            self.client.subscribe(instrument_tokens=instrument_list, isIndex=False, isDepth=False)
            time.sleep(1)  # Wait for data
            
            premium = data_store.get_ltp(token)
            
            if premium >= MIN_PREMIUM:
                print(f"  ✓ Selected {direction} {test_strike} (Offset: {offset}) | Premium: ₹{premium:.2f}")
                return test_strike
            else:
                print(f"  ✗ Skipped {direction} {test_strike} (Offset: {offset}) | Premium: ₹{premium:.2f} < ₹{MIN_PREMIUM}")
        
        # Fallback: If all fail, use ATM±50 as fallback
        print(f"  ⚠️ All offsets failed premium check. Using ATM±50 as fallback.")
        return get_otm_strike(nifty_ltp, direction, 50)
    
    def enter_position(self, direction, is_reentry=False):
        """SHORT CE or PE option."""
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        strike = self.select_strike(direction)
        
        token, trading_symbol = get_strike_token(strike, direction, self.expiry)
        if not token:
            print(f"❌ Could not find {direction} token for strike {strike}")
            return False
        
        # Subscribe to option token
        instrument_list = [{"instrument_token": str(token), "exchange_segment": "nse_fo"}]
        self.client.subscribe(instrument_tokens=instrument_list, isIndex=False, isDepth=False)
        
        # Wait for LTP (Polling)
        premium = 0
        for _ in range(10):  # Check 10 times (5 seconds total)
            time.sleep(0.5)
            premium = data_store.get_ltp(token)
            if premium > 0:
                break
        
        if premium <= 0:
            print(f"❌ No LTP for {direction} option (Token: {token}) after 5s wait")
            return False
        
        # Calculate quantity (reduce by whole lots if re-entry)
        lot_size = get_lot_size(trading_symbol)
        
        if is_reentry:
            # Reduce by 1 lot (or keep minimum 1 lot)
            lots = max(1, LOT_MULTIPLIER - 1)  # If 2 lots, reduce to 1; if 1 lot, stay at 1
            qty = lot_size * lots
        else:
            qty = lot_size * LOT_MULTIPLIER
        
        print(f"\n🚀 {'RE-' if is_reentry else ''}ENTERING SHORT POSITION:")
        print(f"   Direction: SHORT {direction}")
        print(f"   Strike: {strike} ({trading_symbol})")
        print(f"   Premium: ₹{premium:.2f}")
        print(f"   Qty: {qty}")
        print(f"   Entry Spot: {nifty_ltp:.2f}")
        print(f"   EMA9: {self.ema9:.2f} | EMA20: {self.ema20:.2f}")
        print(f"   Swing High: {self.swing_high:.2f} | Swing Low: {self.swing_low:.2f}")
        
        if not DRY_RUN:
            try:
                order = self.client.place_order(
                    exchange_segment="nse_fo",
                    product="NRML",
                    price="0",
                    order_type="MKT",
                    quantity=str(qty),
                    validity="DAY",
                    trading_symbol=trading_symbol,  # Use confirmed symbol
                    transaction_type="S"  # SELL to short
                )
                print(f"✅ Short order placed: {order}")
                
                # Check for API rejection
                if isinstance(order, dict) and order.get('stat') != 'Ok':
                     print(f"❌ Order Rejected: {order.get('errMsg', 'Unknown Error')}")
                     return False
                     
            except Exception as e:
                print(f"❌ Order failed: {e}")
                return False
        else:
            print("   [DRY RUN - No real order]")
        
        # Track position
        self.position = {
            'type': direction,
            'token': token,
            'symbol': trading_symbol,
            'strike': strike,
            'entry_spot': nifty_ltp,
            'entry_premium': premium,
            'qty': qty
        }
        
        self.lowest_premium = premium # Track lowest premium for trailing SL
        
        if is_reentry:
            self.reentry_count += 1
        
        self.state = State.SHORT_OPTION
        self.trailing_sl_price = None  # Reset trailing SL
        return True
    
    def check_spot_sl(self):
        """Check spot-based stop loss."""
        if not self.position:
            return False
        
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        
        if self.position['type'] == 'CE':
            # Short CE SL = Recent Swing High + 10 points
            sl_level = self.swing_high + SPOT_SL_BUFFER
            if nifty_ltp >= sl_level:
                print(f"  🛑 SPOT SL HIT: {nifty_ltp:.2f} >= {sl_level:.2f}")
                return True
        else:  # PE
            # Short PE SL = Recent Swing Low - 10 points
            sl_level = self.swing_low - SPOT_SL_BUFFER
            if nifty_ltp <= sl_level:
                print(f"  🛑 SPOT SL HIT: {nifty_ltp:.2f} <= {sl_level:.2f}")
                return True
        
        return False
    
    def check_premium_sl(self):
        """Check emergency option premium stop loss."""
        if not self.position:
            return False
        
        current_premium = data_store.get_ltp(self.position['token'])
        if current_premium <= 0:
            return False
        
        entry_premium = self.position['entry_premium']
        
        # For short positions, loss occurs when premium increases
        loss_pct = (current_premium - entry_premium) / entry_premium
        
        if loss_pct >= PREMIUM_SL_PCT:
            print(f"  🛑 PREMIUM SL HIT: {loss_pct*100:.1f}% loss")
            return True
        
        return False
    
    def check_profit_exit(self):
        """Check profit exit conditions."""
        if not self.position:
            return None
        
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        current_premium = data_store.get_ltp(self.position['token'])
        
        if current_premium <= 0:
            return None
        
        entry_premium = self.position['entry_premium']
        
        # 1. Spot touches EMA20 (Structural Break)
        if self.ema20 and abs(nifty_ltp - self.ema20) < 5:
            return "EMA20_TOUCH"
        
        # 2. Dynamic Premium Decay Target (based on entry premium)
        decay_pct = (entry_premium - current_premium) / entry_premium
        current_pnl = (entry_premium - current_premium) * self.position['qty']
        
        # Determine target based on entry premium tier
        if entry_premium < 20:
            # Low premium: 50% decay OR ₹500 min profit
            target_decay_pct = 0.50
            min_profit = 500
            if decay_pct >= target_decay_pct or current_pnl >= min_profit:
                print(f"  💰 Low Premium Exit: Decay {decay_pct*100:.1f}% (Target 50%) | Profit ₹{current_pnl:.2f} (Min ₹500)")
                return "PREMIUM_DECAY"
        elif entry_premium < 50:
            # Medium premium: 30% decay
            target_decay_pct = 0.30
            if decay_pct >= target_decay_pct:
                print(f"  💰 Medium Premium Exit: Decay {decay_pct*100:.1f}% (Target 30%)")
                return "PREMIUM_DECAY"
        else:
            # High premium: 20% decay
            target_decay_pct = 0.20
            if decay_pct >= target_decay_pct:
                print(f"  💰 High Premium Exit: Decay {decay_pct*100:.1f}% (Target 20%)")
                return "PREMIUM_DECAY"
            
        # 3. High-Water-Mark Trailing Stop Loss
        # Track lowest premium seen
        if self.lowest_premium is None:
             self.lowest_premium = entry_premium
        
        if current_premium < self.lowest_premium:
             self.lowest_premium = current_premium
             
        # Calculate max profit reached so far
        max_profit_pct = (entry_premium - self.lowest_premium) / entry_premium
        
        # Trigger TSL if max profit > 15% (more forgiving for option selling)
        if max_profit_pct >= 0.15:
             # Trail 10% above the lowest price (wider buffer for volatility)
             # Example: Entry 100. Lowest 80 (20% profit). SL = 80 * 1.10 = 88.
             new_sl = self.lowest_premium * 1.10
             
             # Also ensure SL is at least Breakeven if profit > 20%
             if max_profit_pct >= 0.20:
                 new_sl = min(new_sl, entry_premium)
                 
             # Update TSL if it's tighter (lower) than current
             if self.trailing_sl_price is None or new_sl < self.trailing_sl_price:
                 self.trailing_sl_price = new_sl
                 print(f"  ⛓️ Trailing SL Updated: {self.trailing_sl_price:.2f} (Lowest: {self.lowest_premium:.2f})")

        if self.trailing_sl_price:
             if current_premium >= self.trailing_sl_price:
                 return "TRAILING_SL_HIT"

        # 4. Counter Candle (REMOVED strict close > EMA9 to avoid conflict)
        # Replaced with stricter check: Close > EMA20 is covered by EMA20 touch check generally
        # We can add a severe reversal check: Close > EMA20
        if len(self.candles) > 0:
            last_candle = self.candles[-1]
            if self.position['type'] == 'CE' and last_candle['close'] > self.ema20:
                return "TREND_REVERSAL_CLOSE"
            if self.position['type'] == 'PE' and last_candle['close'] < self.ema20:
                return "TREND_REVERSAL_CLOSE"
        
        return None
    
    def check_max_loss_per_trade(self):
        """Check if max loss per trade is breached."""
        if not self.position:
            return False
        
        current_premium = data_store.get_ltp(self.position['token'])
        if current_premium <= 0:
            return False
        
        # For short: PnL = (entry_premium - current_premium) * qty
        pnl = (self.position['entry_premium'] - current_premium) * self.position['qty']
        
        if pnl <= -self.max_loss_per_trade:
            print(f"  🚨 MAX LOSS PER TRADE BREACHED: ₹{pnl:.2f}")
            return True
        
        return False
    
    def monitor_position(self):
        """Monitor position and check exit conditions."""
        if not self.position:
            return
        
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        option_ltp = data_store.get_ltp(self.position['token'])
        
        if option_ltp <= 0:
            return
        
        # Calculate PnL (for short: profit when premium decreases)
        current_pnl = (self.position['entry_premium'] - option_ltp) * self.position['qty']
        
        # Calculate dynamic Spot SL level for display
        spot_sl_level = 0
        if self.position['type'] == 'CE':
            spot_sl_level = self.swing_high + SPOT_SL_BUFFER
        else:
            spot_sl_level = self.swing_low - SPOT_SL_BUFFER

        # Display status including SL levels
        sl_status = f"Spot SL: {spot_sl_level:.2f}"
        if self.trailing_sl_price:
             sl_status += f" | TSL: {self.trailing_sl_price:.2f}"
        
        print(f"  📊 [SHORT {self.position['type']}] Spot: {nifty_ltp:.2f} | Prem: ₹{option_ltp:.2f} | P&L: ₹{current_pnl:.2f} | {sl_status}")
        
        # Check exit conditions (priority order)
        
        # 1. Max loss per trade
        if self.check_max_loss_per_trade():
            self.exit_position("MAX_LOSS_BREACH")
            return
        
        # 2. Spot-based SL
        if self.check_spot_sl():
            self.exit_position("STOP_LOSS")
            return
        
        # 3. Premium SL
        if self.check_premium_sl():
            self.exit_position("PREMIUM_SL")
            return
        
        # 4. Profit exits
        profit_reason = self.check_profit_exit()
        if profit_reason:
            self.exit_position(profit_reason)
            return
    
    def exit_position(self, reason):
        """Square off position."""
        if not self.position:
            return
        
        option_ltp = data_store.get_ltp(self.position['token'])
        pnl = (self.position['entry_premium'] - option_ltp) * self.position['qty']
        
        print(f"\n🛑 EXITING POSITION: {reason}")
        print(f"   Final P&L: ₹{pnl:.2f}")
        
        if not DRY_RUN:
            try:
                order = self.client.place_order(
                    exchange_segment="nse_fo",
                    product="NRML",
                    price="0",
                    order_type="MKT",
                    quantity=str(self.position['qty']),
                    validity="DAY",
                    trading_symbol=self.position['symbol'], # Use stored valid symbol
                    transaction_type="B"  # BUY to cover short
                )
                print(f"✅ Cover order placed: {order}")
            except Exception as e:
                print(f"❌ Exit order failed: {e}")
        else:
            print("   [DRY RUN - No real order]")
        
        # Update strategy P&L (isolated from other strategies)
        self.strategy_pnl += pnl
        print(f"   Strategy P&L (Today): ₹{self.strategy_pnl:.2f}")
        
        # Check daily loss limit for this strategy
        if self.strategy_pnl <= -self.max_daily_loss:
            print(f"🚨 STRATEGY LOSS LIMIT BREACHED: ₹{self.strategy_pnl:.2f} (Max: -₹{self.max_daily_loss:.2f})")
            self.running = False
        
        # Track for re-entry logic
        self.last_position_type = self.position['type']
        self.last_exit_reason = reason
        self.candles_since_exit = 0
        
        # Check if we should stand down (2 stops on same side)
        if reason in ["STOP_LOSS", "PREMIUM_SL", "MAX_LOSS_BREACH"]:
            if self.reentry_count >= MAX_REENTRIES:
                print(f"⛔ Max re-entries reached on {self.last_position_type}. Standing down on this side.")
                self.standdown_side = self.last_position_type
                self.reentry_count = 0  # Reset for other side
        else:
            # Profitable exit - reset re-entry counter
            self.reentry_count = 0
        
        self.position = None
        self.state = State.WAIT
    
    def check_reentry_allowed(self):
        """Check if re-entry is allowed after stop loss."""
        if self.last_exit_reason not in ["STOP_LOSS", "PREMIUM_SL"]:
            return False
        
        if self.reentry_count >= MAX_REENTRIES:
            return False
        
        if self.standdown_side == self.last_position_type:
            return False
        
        # Check if structure still intact
        if self.ema9 is None or self.ema20 is None:
            return False
        
        if self.last_position_type == 'CE':
            # For bearish bias, EMA9 should still be < EMA20
            if self.ema9 >= self.ema20:
                return False
        else:  # PE
            if self.ema9 <= self.ema20:
                return False
        
        # Check if NIFTY failed to continue beyond SL zone (wait 2 candles for stability)
        if self.candles_since_exit >= 2:
            nifty_ltp = data_store.get_ltp(self.nifty_token)
            
            if self.last_position_type == 'CE':
                # Price should have come back below swing high
                if nifty_ltp < self.swing_high:
                    return True
            else:  # PE
                if nifty_ltp > self.swing_low:
                    return True
        
        return False
    
    def is_trading_allowed(self):
        """Check if trading is allowed based on time."""
        current_time = datetime.now().time()
        
        # No trades first 10 minutes (before 9:25)
        start_time = datetime.strptime(TRADING_START_TIME, "%H:%M").time()
        if current_time < start_time:
            return False
        
        # No trades last 15 minutes (after 15:15)
        end_time = datetime.strptime(TRADING_END_TIME, "%H:%M").time()
        if current_time >= end_time:
            return False
        
        return True
    
    def print_status_update(self, status_msg="WAITING"):
        """Print periodic status update."""
        if time.time() - self.last_status_time < 10:  # Print every 10 seconds for better feedback
            return
            
        nifty_ltp = data_store.get_ltp(self.nifty_token)
        
        # Calculate EMA Diff
        ema_diff_str = ""
        if self.ema9 and self.ema20:
             diff_val = abs(self.ema9 - self.ema20)
             ema_diff_str = f" (Diff: {diff_val:.1f}/{EMA_SEPARATION_THRESHOLD})"
             
        ema_str = f"EMA9: {self.ema9:.2f} EMA20: {self.ema20:.2f}{ema_diff_str}" if self.ema9 else "EMAs: WARMING UP"
        swing_str = f"H: {self.swing_high:.2f} L: {self.swing_low:.2f}" if self.swing_high else "Swing: N/A"
        
        current_time_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time_str}] ⏳ {status_msg} | Spot: {nifty_ltp:.2f} | {ema_str} | {swing_str}")
        self.last_status_time = time.time()

    def run(self):
        """Main strategy loop."""
        print("\n" + "="*70)
        print("  AGGRESSIVE DIRECTIONAL OPTION SELLING STRATEGY")
        print("="*70)
        print(f"  EMA: {EMA_FAST}/{EMA_SLOW}")
        print(f"  Trading Hours: {TRADING_START_TIME} - {TRADING_END_TIME}")
        print(f"  Auto Exit: {AUTO_EXIT_TIME}")
        print(f"  Max Strategy Loss (Today): ₹{self.max_daily_loss:.2f}")
        print(f"  Max Loss Per Trade: ₹{self.max_loss_per_trade:.2f}")
        print(f"  DRY_RUN: {DRY_RUN}")
        print(f"  Note: P&L tracked independently from other strategies")
        print("="*70 + "\n")
        
        self.start_websocket()
        
        while self.running:
            try:
                time.sleep(1) # Faster loop, checked frequently
                
                # Update Indicators periodically (every 30s)
                if time.time() - self.last_indicator_update > 30:
                    self.update_indicators()
                    self.last_indicator_update = time.time()
                
                # Check time-based exit
                current_time = datetime.now().time()
                exit_time = datetime.strptime(AUTO_EXIT_TIME, "%H:%M").time()
                
                if current_time >= exit_time:
                    print(f"⏰ TIME EXIT: {current_time.strftime('%H:%M:%S')}")
                    if self.position:
                        self.exit_position("TIME_EXIT")
                    break
                
                # If in position, monitor it
                if self.state == State.SHORT_OPTION:
                    self.monitor_position()
                    continue
                
                # Check status and print updates
                trading_allowed = self.is_trading_allowed()
                
                # Determine status label
                status_label = "MONITORING"
                current_time_obj = datetime.now().time()
                start_time_obj = datetime.strptime(TRADING_START_TIME, "%H:%M").time()
                if current_time_obj < start_time_obj:
                    status_label = f"PRE-START (Starts {TRADING_START_TIME})"
                elif not trading_allowed:
                    status_label = "TRADING PAUSED"
                
                # Print status update if in WAIT state
                if self.state == State.WAIT:
                    self.print_status_update(status_label)
                
                # Check if trading is allowed
                if not trading_allowed:
                    continue
                
                # Check for re-entry opportunity
                if self.check_reentry_allowed():
                    print(f"\n🔄 RE-ENTRY OPPORTUNITY: {self.last_position_type}")
                    if self.check_candle_break_trigger(self.last_position_type):
                        self.enter_position(self.last_position_type, is_reentry=True)
                    continue
                
                # Check for new entry
                if self.state == State.WAIT:
                    # Check SHORT CE conditions
                    if self.standdown_side != 'CE' and self.check_short_ce_entry():
                        if self.check_candle_break_trigger('CE'):
                            print(f"\n🚨 SHORT CE SIGNAL DETECTED (Candle Low Break)")
                            self.enter_position('CE')
                    
                    # Check SHORT PE conditions
                    elif self.standdown_side != 'PE' and self.check_short_pe_entry():
                        if self.check_candle_break_trigger('PE'):
                            print(f"\n🚨 SHORT PE SIGNAL DETECTED (Candle High Break)")
                            self.enter_position('PE')
                
            except KeyboardInterrupt:
                print("\n⚠️ Strategy interrupted by user")
                if self.position:
                    self.exit_position("MANUAL")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                print(f"❌ Loop error: {e}")


def main():
    global data_store
    data_store = DataStore()
    
    strategy = AggressiveDirectionalStrategy()
    if strategy.running:
        strategy.run()
    
    print("\n✅ Strategy ended")


if __name__ == "__main__":
    main()
