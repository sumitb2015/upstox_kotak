"""
EMA Directional Hedge Strategy - Live Execution Engine

This strategy sells credit spreads (Bull Put or Bear Call) based on EMA momentum.

Entry Logic:
- Bull Put Spread: Price > EMAs, EMA9 > EMA20, momentum increasing
- Bear Call Spread: Price < EMAs, EMA9 < EMA20, momentum decreasing

Exit Logic:
- Profit Target: 50% of max profit
- Stop Loss: 1.5x of max profit
- Momentum Exit: EMA direction reverses
- Trailing SL: Breakeven after 30 min, lock profits

CRITICAL: Uses atomic execution for spread orders to prevent naked exposure.
"""

import sys
import time
from datetime import datetime, timedelta
import pandas as pd
from typing import Optional, Tuple

# Add project root to path
import os
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

# Import configuration and core logic
from strategies.directional.ema_hedge_spread.config import CONFIG, validate_config
from strategies.directional.ema_hedge_spread.core import EMAHedgeCore, SpreadPosition

# Import library functions
from lib.core.authentication import get_access_token
from lib.api.historical import get_historical_data_v3, get_intraday_data_v3
from lib.api.order_management import place_order, get_order_details, cancel_order
from lib.api.market_quotes import get_ltp_quote
from lib.utils.instrument_utils import (
    get_instrument_key, 
    get_option_instrument_key,
    get_lot_size
)
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.date_utils import is_market_open
from lib.api.market_data import download_nse_market_data


# ==============================================================================
# CONSOLE OUTPUT HELPERS
# ==============================================================================

def print_box(title, content_lines, emoji="ℹ️"):
    """Print content in a standardized box."""
    print("-" * 60)
    print(f"{emoji} {title}")
    print("-" * 60)
    for line in content_lines:
        print(f"   {line}")
    print("-" * 60)

def print_status_ticker(timestamp, price, ema9, ema20, diff, momentum):
    """Print concise status ticker."""
    print(f"⏰ {timestamp} | Price: {price:.2f} | EMA9: {ema9:.2f} | EMA20: {ema20:.2f} | Diff: {diff:.2f} ({momentum})")

def print_position_status(spread_type, pnl, profit_pct, time_in_trade, tsl):
    """Print position status line."""
    tsl_str = f"₹{tsl:.2f}" if tsl is not None else "None"
    print(f"💼 POS: {spread_type} | P&L: ₹{pnl:.2f} ({profit_pct:.1f}%) | Time: {time_in_trade}m | TSL: {tsl_str}")



def get_quote(access_token, instrument_key):
    """
    Helper to get quote data from LTP quote.
    Wraps get_ltp_quote to return the specific instrument's data dict.
    """
    response = get_ltp_quote(access_token, instrument_key)
    if response and response.get('status') == 'success':
        data = response.get('data', {})
        
        # 1. Direct match
        if instrument_key in data:
            return data[instrument_key]
            
        # 2. Match by replacing pipe with colon (Common Upstox format shift)
        colon_key = instrument_key.replace('|', ':')
        if colon_key in data:
            return data[colon_key]
            
        # 3. Search by payload content (Robust fallback)
        for k, v in data.items():
            if v.get('instrument_token') == instrument_key:
                return v
            # If we only requested one key, and got one result, it's probably it.
            # But safer to match token if possible.
            
    return {}

def get_atm_strike(spot_price, step=50):
    """Calculate ATM strike for Nifty (step=50)."""
    return round(spot_price / step) * step


class EMAHedgeLiveStrategy(EMAHedgeCore):
    """Live execution implementation of EMA Hedge Strategy."""
    
    def __init__(self, config: dict, access_token: str):
        """
        Initialize live strategy.
        
        Args:
            config: Strategy configuration
            access_token: Upstox API access token
        """
        super().__init__(config)
        self.access_token = access_token
        
        # Download NSE Master Data for instrument lookup
        print("📥 Downloading NSE master data...")
        self.nse_data = download_nse_market_data()
        if self.nse_data is None or self.nse_data.empty:
            raise Exception("Failed to download NSE master data")
        print(f"✅ Master data loaded: {len(self.nse_data)} records")
        
        # Get expiry for reference (not used for lookup directly)
        self.expiry_date = get_expiry_for_strategy(
            self.access_token,
            expiry_type=config['expiry_type'],
            instrument=config['underlying']
        )
        print(f"📅 Strategy Target Expiry: {self.expiry_date}")
        
        # Get Nifty Index instrument key
        if config['underlying'] == 'NIFTY':
            self.underlying_key = "NSE_INDEX|Nifty 50"
        elif config['underlying'] == 'BANKNIFTY':
            self.underlying_key = "NSE_INDEX|Nifty Bank"
        else:
             self.underlying_key = "NSE_INDEX|Nifty 50" # Default
             
        print(f"📊 Underlying: {self.underlying_key}")
    
    # ========== DATA FETCHING ==========
    
    def fetch_candles(self) -> Optional[pd.DataFrame]:
        """
        Fetch candles for Nifty Index (for EMA calculations).
        
        Merges historical + intraday data for accurate indicators.
        """
        try:
            interval = self.config['candle_interval_minutes']
            lookback = self.config['lookback_candles']
            
            # Fetch last 2 days historical
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
            
            historical = get_historical_data_v3(
                self.access_token,
                self.underlying_key,
                "minutes",
                interval,
                from_date,
                to_date
            )
            
            # Fetch today's intraday
            intraday = get_intraday_data_v3(
                self.access_token,
                self.underlying_key,
                "minutes",
                interval
            )
            
            # Merge data
            if historical and intraday:
                all_candles = historical + intraday
            elif historical:
                all_candles = historical
            elif intraday:
                all_candles = intraday
            else:
                print("❌ No candle data available")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(all_candles)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            df = df.drop_duplicates(subset=['timestamp'], keep='last')
            
            # Keep only lookback candles
            df = df.tail(lookback).reset_index(drop=True)
            
            if len(df) < max(self.config['ema_fast'], self.config['ema_slow']):
                print(f"⚠️ Insufficient candles: {len(df)}")
                return None
            
            return df
            
        except Exception as e:
            print(f"❌ Error fetching candles: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_option_prices(self, short_key: str, long_key: str) -> Tuple[float, float]:
        """
        Get current prices for spread legs.
        
        Args:
            short_key: Instrument key for short leg
            long_key: Instrument key for long leg (hedge)
            
        Returns:
            (short_price, long_price)
        """
        try:
            short_quote = get_quote(self.access_token, short_key)
            long_quote = get_quote(self.access_token, long_key)
            
            short_price = short_quote.get('last_price', 0) if short_quote else 0
            long_price = long_quote.get('last_price', 0) if long_quote else 0
            
            return short_price, long_price
            
        except Exception as e:
            print(f"❌ Error fetching option prices: {e}")
            return 0.0, 0.0
    
    # ========== ATOMIC SPREAD ORDER EXECUTION ==========
    
    def execute_spread_entry(self, spread_type: str, atm_strike: int) -> Optional[SpreadPosition]:
        """
        Execute spread order with ATOMIC execution (CRITICAL).
        
        This ensures both legs fill together or neither fills, preventing naked exposure.
        
        Args:
            spread_type: 'BULL_PUT_SPREAD' or 'BEAR_CALL_SPREAD'
            atm_strike: Current ATM strike
            
        Returns:
            SpreadPosition object if successful, None otherwise
        """

        # Header
        header_lines = [
            f"Type: {spread_type}",
            f"ATM:  {atm_strike}"
        ]
        print_box(f"EXECUTING {spread_type}", header_lines, "🎯")
        
        try:
            # Determine strikes and option type
            otm_offset = self.config['strikes_otm'] * 50  # Nifty moves in 50-point increments
            hedge_distance = self.config['hedge_distance']
            
            if spread_type == 'BULL_PUT_SPREAD':
                # Sell PUT 1 strike OTM (below ATM), Buy PUT further below
                short_strike = atm_strike - otm_offset
                long_strike = short_strike - hedge_distance
                option_type = 'PE'
                
            else:  # BEAR_CALL_SPREAD
                # Sell CALL 1 strike OTM (above ATM), Buy CALL further above
                short_strike = atm_strike + otm_offset
                long_strike = short_strike + hedge_distance
                option_type = 'CE'
            
            print(f"📍 Strikes: Short={short_strike} {option_type}, Long={long_strike} {option_type}")
            
            # Get instrument keys
            short_key = get_option_instrument_key(
                self.config['underlying'],
                short_strike,
                option_type,
                self.nse_data,
                expiry_date=self.expiry_date
            )
            long_key = get_option_instrument_key(
                self.config['underlying'],
                long_strike,
                option_type,
                self.nse_data,
                expiry_date=self.expiry_date
            )
            
            if not short_key or not long_key:
                print(f"❌ Failed to find instrument keys: Short={short_key}, Long={long_key}")
                return None
            
            print(f"📝 Short Leg: {short_key}")
            print(f"📝 Long Leg: {long_key}")
            
            # Get current prices
            short_price, long_price = self.get_option_prices(short_key, long_key)
            
            if short_price == 0 or long_price == 0:
                print("❌ Failed to fetch option prices")
                return None
            
            net_credit = short_price - long_price
            print(f"💰 Net Credit: ₹{net_credit:.2f} (Short: ₹{short_price:.2f}, Long: ₹{long_price:.2f})")
            
            if net_credit <= 0:
                print("❌ Invalid spread: Net credit is zero or negative")
                return None
            
            # Calculate lot size from broker data
            lot_multiplier = get_lot_size(self.config['underlying'])
            if lot_multiplier is None:
                lot_multiplier = 50  # Default for Nifty
                print(f"⚠️ Using default lot size: {lot_multiplier}")
            
            quantity = self.config['lot_size'] * lot_multiplier
            
            # ========== ATOMIC EXECUTION (CRITICAL) ==========
            print(f"\n🔐 ATOMIC EXECUTION START")
            print(f"{'='*60}")
            
            short_order_id = None
            long_order_id = None
            
            try:
                # Step 1: Place SHORT leg (sell)
                print("📤 Step 1: Placing SHORT leg...")
                short_response = place_order(
                    self.access_token,
                    instrument_token=short_key,
                    quantity=quantity,
                    transaction_type="SELL",
                    order_type="MARKET",
                    product=self.config['product_type'],
                    tag="ema_hedge_short"
                )
                
                if not short_response or short_response.get('status') != 'success':
                    raise Exception(f"Short leg order failed: {short_response}")
                
                short_order_id = short_response['data']['order_id']
                print(f"✅ Short leg order placed: {short_order_id}")
                
                # Wait briefly for order to process
                time.sleep(1)
                
                # 2: Place LONG leg (buy hedge)
                print("📤 Step 2: Placing LONG leg (hedge)...")
                long_response = place_order(
                    self.access_token,
                    instrument_token=long_key,
                    quantity=quantity,
                    transaction_type="BUY",
                    order_type="MARKET",
                    product=self.config['product_type'],
                    tag="ema_hedge_long"
                )
                
                if not long_response or long_response.get('status') != 'success':
                    raise Exception(f"Long leg order failed: {long_response}")
                
                long_order_id = long_response['data']['order_id']
                print(f"✅ Long leg order placed: {long_order_id}")
                
                # Step 3: Verify both orders filled
                time.sleep(2)
                
                short_status = self.verify_order_filled(short_order_id)
                long_status = self.verify_order_filled(long_order_id)
                
                if not short_status['filled']:
                    raise Exception(f"Short leg not filled: {short_status['status']}")
                if not long_status['filled']:
                    raise Exception(f"Long leg not filled: {long_status['status']}")
                
                print(f"\n✅ SPREAD EXECUTION SUCCESSFUL")
                print(f"💰 Short Avg: ₹{short_status['avg_price']:.2f} | Long Avg: ₹{long_status['avg_price']:.2f}")
                print(f"{'='*60}")
                
                # Create position object
                position = SpreadPosition(
                    spread_type=spread_type,
                    short_strike=short_strike,
                    long_strike=long_strike,
                    short_entry_price=short_status['avg_price'],
                    long_entry_price=long_status['avg_price'],
                    lot_size=quantity,
                    short_instrument_key=short_key,
                    long_instrument_key=long_key,
                    pnl_multiplier=1.0  # Already multiplied by lot size in quantity
                )
                
                return position
                
            except Exception as e:
                # ========== ROLLBACK LOGIC (CRITICAL) ==========
                print(f"\n❌ SPREAD EXECUTION FAILED: {e}")
                print(f"🔄 INITIATING ROLLBACK...")
                
                # Cancel any pending orders
                if short_order_id:
                    print(f"🔄 Attempting to cancel short leg: {short_order_id}")
                    try:
                        cancel_order(self.access_token, short_order_id)
                    except Exception as cancel_err:
                        print(f"⚠️ Failed to cancel short leg: {cancel_err}")
                
                if long_order_id:
                    print(f"🔄 Attempting to cancel long leg: {long_order_id}")
                    try:
                        cancel_order(self.access_token, long_order_id)
                    except Exception as cancel_err:
                        print(f"⚠️ Failed to cancel long leg: {cancel_err}")
                
                # If one leg filled (even partially) and other didn't, close the filled quantity
                if short_order_id:
                    short_check = self.verify_order_filled(short_order_id)
                    filled_qty = short_check.get('filled_quantity', 0)
                    if filled_qty > 0:
                        print(f"⚠️ Short leg partially/fully filled ({filled_qty}) - closing for safety")
                        self.emergency_close_position(short_key, filled_qty, "BUY")
                
                if long_order_id:
                    long_check = self.verify_order_filled(long_order_id)
                    filled_qty = long_check.get('filled_quantity', 0)
                    if filled_qty > 0:
                        print(f"⚠️ Long leg partially/fully filled ({filled_qty}) - closing for safety")
                        self.emergency_close_position(long_key, filled_qty, "SELL")
                
                print(f"❌ ROLLBACK COMPLETE - No position entered")
                return None
                
        except Exception as e:
            print(f"❌ Fatal error in spread execution: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def verify_order_filled(self, order_id: str) -> dict:
        """Verify if an order is filled with retries to handle API eventual consistency."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                details = get_order_details(self.access_token, order_id)
                if details and len(details) > 0:
                    latest = details[-1]
                    status = latest.get('status', '')
                    
                    # If order is still being processed, wait and retry
                    if status in ['put order req received', 'validation pending']:
                        time.sleep(1)
                        continue
                        
                    filled_qty = latest.get('filled_quantity', 0)
                    total_qty = latest.get('quantity', 0)
                    avg_price = latest.get('average_price', 0)
                    
                    return {
                        'filled': status == 'complete' and filled_qty == total_qty,
                        'status': status,
                        'filled_quantity': filled_qty,
                        'avg_price': avg_price
                    }
            except Exception as e:
                print(f"❌ Error verifying order {order_id} (Attempt {attempt+1}): {e}")
            
            if attempt < max_attempts - 1:
                time.sleep(1)
        
        return {'filled': False, 'status': 'timeout', 'filled_quantity': 0, 'avg_price': 0}
    
    def emergency_close_position(self, instrument_key: str, quantity: int, side: str):
        """Emergency close a position due to failed spread execution."""
        try:
            print(f"🚨 Emergency close: {quantity} {side} {instrument_key}")
            place_order(
                self.access_token,
                instrument_token=instrument_key,
                quantity=quantity,
                transaction_type=side,
                order_type="MARKET",
                product=self.config['product_type'],
                tag="emergency_close"
            )
            # Do not raise exception - best effort close
        except Exception as e:
            print(f"❌ Emergency close failed: {e}")
    
    def execute_pyramid_entry(self, quantity: int) -> bool:
        """
        Execute pyramid entry (add to existing position) with ATOMIC execution.
        """
        if not self.position:
            return False
            
        print_box(f"EXECUTING PYRAMID ENTRY (+{quantity} lots)", ["Adding to winning position"], "🚀")
        
        try:
            # Determine keys (already known)
            short_key = self.position.short_instrument_key
            long_key = self.position.long_instrument_key
            
            # ATOMIC EXECUTION
            short_order_id = None
            long_order_id = None
            
            try:
                # 1. Place SHORT leg
                print(f"📤 Step 1: Placing SHORT leg (+{quantity} lots)...")
                short_response = place_order(
                    self.access_token, short_key, quantity, "SELL", "MARKET", 
                    self.config['product_type'], "ema_hedge_pyramid_short"
                )
                
                if not short_response or short_response.get('status') != 'success':
                    raise Exception("Short leg failed")
                short_order_id = short_response['data']['order_id']
                
                time.sleep(1)
                
                # 2. Place LONG leg
                print(f"📤 Step 2: Placing LONG leg (+{quantity} lots)...")
                long_response = place_order(
                    self.access_token, long_key, quantity, "BUY", "MARKET", 
                    self.config['product_type'], "ema_hedge_pyramid_long"
                )
                
                if not long_response or long_response.get('status') != 'success':
                    raise Exception("Long leg failed")
                long_order_id = long_response['data']['order_id']
                
                time.sleep(2)
                
                # 3. Verify
                short_status = self.verify_order_filled(short_order_id)
                long_status = self.verify_order_filled(long_order_id)
                
                if not short_status['filled']:
                    raise Exception(f"Short leg not filled: {short_status['status']}")
                if not long_status['filled']:
                    raise Exception(f"Long leg not filled: {long_status['status']}")
                    
                print(f"✅ PYRAMID EXECUTION SUCCESSFUL")
                print(f"💰 Pyramid Short Avg: ₹{short_status['avg_price']:.2f} | Long Avg: ₹{long_status['avg_price']:.2f}")
                
                # Update Position
                self.position.add_lots(
                    quantity, 
                    short_status['avg_price'], 
                    long_status['avg_price']
                )
                
                # Update next milestone manually here
                step_pct = self.config['pyramid_step_profit_pct']
                self.position.next_pyramid_milestone += step_pct
                print(f"📈 New Targets: Next Pyramid @ {self.position.next_pyramid_milestone*100:.0f}% Profit")
                
                return True
                
            except Exception as e:
                print(f"❌ PYRAMID FAILED: {e}")
                print(f"🔄 Rolling back pyramid orders...")
                
                # Close filled quantities from THIS pyramid attempt only
                if short_order_id:
                    check = self.verify_order_filled(short_order_id)
                    qty = check.get('filled_quantity', 0)
                    if qty > 0:
                        self.emergency_close_position(short_key, qty, "BUY")
                        
                if long_order_id:
                    check = self.verify_order_filled(long_order_id)
                    qty = check.get('filled_quantity', 0)
                    if qty > 0:
                        self.emergency_close_position(long_key, qty, "SELL")
                
                return False
                
        except Exception as e:
            print(f"❌ Fatal pyramid error: {e}")
            return False

    def execute_spread_exit(self):
        """Exit spread position by closing both legs with verification."""
        if not self.position:
            return
        
        # Header
        exit_lines = [
            f"Type: {self.position.spread_type}",
            f"Lots: {self.position.lot_size}",
            f"P&L:  ₹{self.position.get_current_pnl():.2f}"
        ]
        print_box(f"EXITING POSITION", exit_lines, "🚪")
        
        try:
            # 1. Close SHORT leg (buy back)
            short_token = self.position.short_instrument_key
            qty = self.position.lot_size * self.lot_size
            
            print(f"📤 Closing SHORT leg ({self.position.lot_size} lots)...")
            short_response = place_order(
                self.access_token,
                instrument_token=short_token,
                quantity=qty,
                transaction_type="BUY",
                order_type="MARKET",
                product=self.config['product_type'],
                tag="ema_hedge_exit_short"
            )
            
            # 2. Close LONG leg (sell)
            long_token = self.position.long_instrument_key
            print(f"📤 Closing LONG leg ({self.position.lot_size} lots)...")
            long_response = place_order(
                self.access_token,
                instrument_token=long_token,
                quantity=qty,
                transaction_type="SELL",
                order_type="MARKET",
                product=self.config['product_type'],
                tag="ema_hedge_exit_long"
            )
            
            # Step 3: Verify both orders
            time.sleep(2)
            
            if short_response and short_response.get('status') == 'success':
                short_oid = short_response['data']['order_id']
                res = self.verify_order_filled(short_oid)
                if not res['filled']:
                    print(f"⚠️ SHORT leg not fully filled: {res['status']}")
            
            if long_response and long_response.get('status') == 'success':
                long_oid = long_response['data']['order_id']
                res = self.verify_order_filled(long_oid)
                if not res['filled']:
                    print(f"⚠️ LONG leg not fully filled: {res['status']}")
            
            print("✅ Exit orders executed")
                
        except Exception as e:
            print(f"❌ Error during spread exit: {e}")
        finally:
            self.clear_position()

    def exit_all(self):
        """Mandatory Graceful Shutdown: Close all positions and clear state."""
        print_box("GRACEFUL SHUTDOWN", ["Closing all positions...", "Clearing memory state"], "🛑")
        if self.position:
            self.execute_spread_exit()
        
        # Reset core state
        self.clear_position()
        print("✅ Shutdown complete")
    
    # ========== MAIN STRATEGY LOOP ==========
    
    def run(self):
        """Main strategy execution loop."""
        print(f"\n{'='*80}")
        print(f"🚀 EMA DIRECTIONAL HEDGE STRATEGY - LIVE")
        print(f"{'='*80}")
        print(f"⚙️  Config: {self.config['candle_interval_minutes']}min candles, EMA{self.config['ema_fast']}/{self.config['ema_slow']}")
        print(f"📊 Threshold: {self.config['min_ema_diff_threshold']} points")
        print(f"🎯 Targets: {self.config['profit_target_pct']*100:.0f}% profit, {self.config['stop_loss_multiplier']}x SL")
        if self.config.get('enable_pyramiding'):
            print(f"🪜 Pyramiding: Enabled (Max {self.config['max_lots']} lots)")
        print(f"{'='*80}\n")
        
        # Validate config
        validate_config()
        
        # Standard Startup Banner
        startup_lines = [
            f"Config:    {self.config['candle_interval_minutes']}min candles | EMA{self.config['ema_fast']}/{self.config['ema_slow']}",
            f"Threshold: {self.config['min_ema_diff_threshold']} points",
            f"Targets:   {self.config['profit_target_pct']*100:.0f}% Profit | {self.config['stop_loss_multiplier']}x SL",
            f"Expiry:    {self.expiry_date} ({self.config['expiry_type']})"
        ]
        print_box("EMA DIRECTIONAL HEDGE STRATEGY - LIVE", startup_lines, "🚀")
        
        # Main loop
        check_interval = self.config['candle_interval_minutes'] * 60  # seconds
        last_check = 0
        
        while True:
            try:
                current_time = datetime.now()
                
                # Check trading hours
                if not is_market_open():
                    print(f"⏸️  Market closed - waiting...")
                    time.sleep(60)
                    continue
                
                # Check if past entry time
                entry_start = datetime.strptime(self.config['entry_start_time'], '%H:%M').time()
                entry_end = datetime.strptime(self.config['entry_end_time'], '%H:%M').time()
                
                if current_time.time() < entry_start:
                    print(f"⏸️  Before entry time ({self.config['entry_start_time']}) - waiting...")
                    time.sleep(60)
                    continue
                
                # Mandatory exit time
                exit_time = datetime.strptime(self.config['exit_time'], '%H:%M').time()
                if current_time.time() >= exit_time:
                    if self.position:
                        print(f"⏰ Mandatory exit time ({self.config['exit_time']}) reached")
                        self.execute_spread_exit()
                    print(f"✅ Strategy complete for the day")
                    break
                
                # Throttle checks to candle interval
                if time.time() - last_check < check_interval:
                    time.sleep(10)
                    continue
                
                last_check = time.time()
                
                # Fetch and update indicators
                # (Silenced "Checking signals..." to reduce clutter)
                
                candles = self.fetch_candles()
                if candles is None or candles.empty:
                    print("⚠️ No candle data - skipping")
                    continue
                
                self.update_indicators(candles)
                
                # Display current state
                if len(self.ema9_history) >= 2:
                    price = self.price_history[-1]
                    ema9 = self.ema9_history[-1]
                    ema20 = self.ema20_history[-1]
                    diff = ema9 - ema20
                    momentum = self.get_ema_difference_momentum(2)
                    
                    print_status_ticker(
                        current_time.strftime('%H:%M:%S'),
                        price, ema9, ema20, diff, momentum
                    )
                
                # Check position status
                if self.position:
                    # Update option prices
                    short_price, long_price = self.get_option_prices(
                        self.position.short_instrument_key,
                        self.position.long_instrument_key
                    )
                    self.update_position_prices(short_price, long_price)
                    
                    summary = self.get_position_summary()
                    print_position_status(
                        summary['spread_type'], 
                        summary['current_pnl'], 
                        summary['profit_pct'], 
                        summary['minutes_in_trade'], 
                        summary.get('trailing_sl')
                    )
                    print(f"   Lots: {self.position.lot_size} / {self.config['max_lots']}")
                    
                    # Check Pyramiding
                    should_pyramid, p_reason = self.check_pyramid_signal()
                    if should_pyramid:
                        print(f"🪜 Pyramid Signal: {p_reason}")
                        # Calculate lot size (1 lot * multiplier)
                        lot_multiplier = get_lot_size(self.config['underlying']) or 50
                        qty_to_add = 1 * lot_multiplier
                        
                        self.execute_pyramid_entry(qty_to_add)
                    
                    # Check exit signals
                    should_exit, exit_type, reason = self.check_exit_signal()
                    if should_exit:
                        print_box("EXIT SIGNAL DETECTED", [f"Type: {exit_type}", f"Reason: {reason}"], "🚨")
                        self.execute_spread_exit()
                
                else:
                    # Check entry signals
                    if current_time.time() < entry_end:
                        should_enter, spread_type, reason = self.check_entry_signal()
                        
                        if should_enter:
                            entry_lines = [
                                f"Direction: {spread_type}",
                                f"Reason:    {reason}"
                            ]
                            print_box("ENTRY SIGNAL DETECTED", entry_lines, "🎯")
                            
                            # Get ATM strike
                            current_price = self.price_history[-1]
                            atm = get_atm_strike(current_price)
                            
                            # Execute spread entry
                            position = self.execute_spread_entry(spread_type, atm)
                            
                            if position:
                                self.position = position
                                print(f"✅ Position entered successfully")
                            else:
                                print(f"❌ Failed to enter position")
                
            except KeyboardInterrupt:
                print(f"\n⚠️ Strategy interrupted by user")
                self.exit_all()
                break
                
            except Exception as e:
                print(f"❌ Error in main loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)


def main():
    """Entry point for live strategy."""
    print("🔐 Authenticating...")
    access_token = get_access_token()
    
    print("✅ Authentication successful")
    
    # Initialize and run strategy
    strategy = EMAHedgeLiveStrategy(CONFIG, access_token)
    strategy.run()


if __name__ == "__main__":
    main()
