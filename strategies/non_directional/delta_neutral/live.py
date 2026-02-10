"""
Delta-Neutral Option Selling Strategy (Kotak Neo Execution)

A market-neutral strategy that sells ATM straddles and maintains delta neutrality
through automatic hedging.

Hybrid Architecture:
1. Data Ingestion: Upstox API (Option Chain, Greeks, Market Data)
2. Trade Execution: Kotak Neo API (via Kotak_Api lib)
"""

import sys
import os
import re
# Add parent directory to path so we can import from api/ and Kotak_Api/
# File is now in strategies/hybrid/ -> Root is ../../
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# Kotak_Api is in root/Kotak_Api
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

import time
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional
from enum import Enum, auto

# --- Upstox Imports (Data) ---
from lib.api.option_chain import (
    get_option_chain_dataframe, get_nearest_expiry,
    get_greeks, get_market_data, get_oi_data, get_premium_data,
    get_atm_strike_from_chain
)
from lib.utils.instrument_utils import get_option_instrument_key

# --- Kotak Imports (Execution) ---
from Kotak_Api.lib.broker import BrokerClient
from Kotak_Api.lib.order_manager import OrderManager
from Kotak_Api.lib.trading_utils import get_strike_token, get_lot_size

class StrategyState(Enum):
    INITIALIZING = auto()
    WAITING_FOR_ENTRY = auto()
    ENTRY_EXECUTION = auto()
    MONITORING = auto()
    REBALANCING = auto()
    ROLLING = auto()
    COOLDOWN = auto()
    EXITING = auto()
    STOPPED = auto()

class Position:
    """Track individual option position with Greeks and Kotak specifics"""
    def __init__(self, strike: int, option_type: str, quantity: int, 
                 entry_price: float, direction: int, instrument_key: str,
                 kotak_symbol: str, kotak_token: int):
        self.strike = strike
        self.option_type = option_type  # "CE" or "PE"
        self.quantity = quantity
        self.entry_price = entry_price
        self.direction = direction  # -1 for short, +1 for long
        
        # Upstox Key (Data)
        self.instrument_key = instrument_key
        
        # Kotak Details (Execution)
        self.kotak_symbol = kotak_symbol
        self.kotak_token = kotak_token
        self.kotak_order_id = None # Set after placement
        
        # Tracking
        self.current_delta = 0.0
        self.current_price = 0.0
        self.unrealized_pnl = 0.0

class DeltaNeutralKotakStrategy:
    """
    Delta-neutral option selling strategy (Hybrid).
    - Data: Upstox
    - Execution: Kotak Neo
    """
    
    def __init__(self, access_token: str, nse_data, lot_size: int = 65, dry_run: bool = False):
        self.access_token = access_token
        self.nse_data = nse_data
        self.dry_run = dry_run
        
        # Validate lot_size
        if lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {lot_size}")
        self.lot_size = lot_size
        
        # Strategy parameters (BALANCED MODE)
        self.base_hedge_delta = 12.0  # Trigger threshold (Increased for stability)
        self.base_target_delta = 6.0  # Target threshold (Relaxed to avoid over-hedging)
        self.delta_step_multiplier = 1.2 # Less widening, stay tight
        self.max_adjustments = 5      # More adjustments allowed
        self.max_total_lots = 5       # Max lots across all positions
        self.hedge_cooldown_minutes = 1 # Faster cooldown (Reduced from 2)
        
        # Entry/Exit parameters
        self.entry_time = dt_time(9, 20)  # Start after morning volatility
        self.profit_target_pct = 0.5  # 50% of collected premium
        self.stop_loss_multiplier = 0.3  # -0.3x collected premium (30% loss)
        
        self.trailing_sl_pnl_trigger = 0.25  # Start trailing at 25% of target
        self.trailing_sl_lock_pct = 0.50     # Lock 50% of peak P&L
        
        # Risk Management Limits
        self.max_gamma = 0.50              # Emergency exit if Gamma > 0.50
        
        # Entry Validation Parameters
        self.max_entry_adx = 25            # Don't enter if ADX >= 25 (strong trend)
        self.max_straddle_width_pct = 0.20 # Straddle premium should be < 20% of spot
        self.adx_history = []              # Track ADX values to detect rising/falling trend
        
        # Position tracking
        self.positions: List[Position] = []
        self.total_premium_collected = 0.0
        self.realized_pnl = 0.0
        self.adjustment_count = 0  # To track hedging rounds
        self.is_rebalancing = False # Hysteresis state
        self.peak_pnl = 0.0        # For trailing SL
        self.current_stop_loss = 0.0 # Dynamic SL
        
        # Option chain data
        self.option_chain_df = None
        self.expiry_date = None
        self.atm_strike = None
        
        # Kotak Components
        self.kotak_broker = None
        self.kotak_order_manager = None
        
        # Status
        self.is_running = False
        self.last_hedge_time = None
        self.state = StrategyState.INITIALIZING
        
        # Logging Setup
        self.log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'delta_neutral')
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except: pass
        self.log_file = os.path.join(self.log_dir, f"delta_neutral_{datetime.now().strftime('%Y%m%d')}.log")

    def log_to_file(self, message):
        """Append a message to the strategy log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
        except: pass

    def initialize(self):
        """Initialize strategy - Authenticate Kotak and fetch Upstox Chain"""
        print("🚀 Initializing Delta-Neutral Strategy (Hybrid Mode)...")
        
        # 1. Initialize Kotak
        try:
            print("🔐 Authenticating Kotak Neo...")
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            print("📥 Loading Kotak Master Data...")
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
            print("✅ Kotak Initialization Complete")
        except Exception as e:
            print(f"❌ Kotak Initialization Failed: {e}")
            return False

        # 2. Initialize Upstox Data
        # Get nearest expiry using library function
        print("📅 Fetching nearest expiry from Upstox...")
        expiry_str = get_nearest_expiry(self.access_token, "NSE_INDEX|Nifty 50")
        
        if not expiry_str:
            print("❌ Failed to get expiry date")
            return False
        
        # Convert string expiry to datetime object for Kotak compatibility
        # But keep the string version for Upstox API calls
        try:
            self.expiry_date_datetime = datetime.strptime(expiry_str, "%Y-%m-%d")
            self.expiry_date = expiry_str  # Keep string format for Upstox
            print(f"📅 Using expiry: {expiry_str}")
        except Exception as e:
            print(f"❌ Error parsing expiry date '{expiry_str}': {e}")
            return False
            
        # 3. Fetch option chain with all Greeks
        self.refresh_option_chain()
        
        if self.option_chain_df is None or self.option_chain_df.empty:
            print("❌ Failed to fetch option chain")
            return False
        
        # Get ATM strike
        self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
        print(f"🎯 ATM Strike identified: {self.atm_strike}")
        
        return True


    
    def refresh_option_chain(self):
        """Refresh option chain data from Upstox"""
        self.option_chain_df = get_option_chain_dataframe(
            self.access_token,
            "NSE_INDEX|Nifty 50",
            self.expiry_date
        )
    
    def resolve_kotak_symbol(self, strike, option_type):
        """Helper to resolve Upstox parameters to Kotak Symbol"""
        token, symbol = get_strike_token(
            self.kotak_broker, 
            strike, 
            option_type, 
            self.expiry_date_datetime  # Kotak needs datetime object
        )
        return token, symbol

    def calculate_portfolio_delta(self) -> float:
        """Calculate total portfolio delta using Upstox Greeks"""
        if not self.positions:
            return 0.0
        
        # Note: Option chain should be refreshed before calling this method
        total_delta = 0.0
        
        for position in self.positions:
            # Get current Greeks using library function
            greeks = get_greeks(
                self.option_chain_df,
                position.strike,
                position.option_type
            )
            
            if greeks:
                position.current_delta = greeks['delta']
                position_delta = greeks['delta'] * position.quantity * position.direction
                total_delta += position_delta
            else:
                print(f"⚠️  WARNING: Greeks unavailable for {position.option_type} strike {position.strike}")
        
        return total_delta
    
    def calculate_portfolio_greeks(self) -> Dict:
        """Calculate all portfolio Greeks"""
        self.refresh_option_chain() # Ensure fresh data
        
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        
        for position in self.positions:
            greeks = get_greeks(
                self.option_chain_df,
                position.strike,
                position.option_type
            )
            
            if greeks:
                total_delta += greeks['delta'] * position.quantity * position.direction
                total_gamma += greeks['gamma'] * position.quantity * position.direction
                total_theta += greeks['theta'] * position.quantity * position.direction
                total_vega += greeks['vega'] * position.quantity * position.direction
        
        return {
            'delta': total_delta,
            'gamma': total_gamma,
            'theta': total_theta,
            'vega': total_vega
        }
    
    def calculate_pnl(self) -> Dict:
        """Calculate portfolio P&L using Upstox Market Data (More Reliable/Fast for logic)"""
        total_unrealized_pnl = 0.0
        
        for position in self.positions:
            market = get_market_data(
                self.option_chain_df,
                position.strike,
                position.option_type
            )
            
            if market:
                position.current_price = market['ltp']
                # For SHORT (direction=-1): profit when price drops (current < entry)
                # For LONG (direction=+1): profit when price rises (current > entry)
                # Formula: (Current - Entry) * Direction * Qty
                pnl_per_unit = (position.current_price - position.entry_price) * position.direction
                position.unrealized_pnl = pnl_per_unit * position.quantity
                total_unrealized_pnl += position.unrealized_pnl
            else:
                print(f"⚠️  WARNING: Market data unavailable for {position.option_type} strike {position.strike}")
        
        total_pnl = self.realized_pnl + total_unrealized_pnl
        
        return {
            'realized': self.realized_pnl,
            'unrealized': total_unrealized_pnl,
            'total': total_pnl,
            'premium_collected': self.total_premium_collected,
            'profit_target': self.total_premium_collected * self.profit_target_pct,
            'stop_loss': -self.total_premium_collected * self.stop_loss_multiplier
        }
    
    def validate_entry_conditions(self) -> bool:
        """
        Validate if market conditions are suitable for straddle entry.
        Returns: True if safe to enter, False otherwise
        """
        print("\n🔍 Validating entry conditions...")
        
        # Refresh option chain to ensure we check LATEST prices
        self.refresh_option_chain()
        
        # Get spot price and ATM option premiums
        spot_price = self.option_chain_df['spot_price'].iloc[0] if not self.option_chain_df.empty else 0
        
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        
        if not ce_data or not pe_data or spot_price == 0:
            print("❌ Unable to fetch market data for validation")
            return False
        
        ce_price = ce_data['ltp']
        pe_price = pe_data['ltp']
        straddle_premium = ce_price + pe_price
        
        # Validate premium data
        if straddle_premium <= 0 or ce_price <= 0 or pe_price <= 0:
            print("❌ Invalid premium data (zero or negative)")
            return False
        
        # 1. Check Straddle Skew (Difference between CE and PE as % of total premium)
        # This ensures we don't enter if premiums are vastly unbalanced (already directional)
        price_diff = abs(ce_price - pe_price)
        skew_pct = price_diff / straddle_premium if straddle_premium > 0 else 0
        
        print(f"   ⚖️ Straddle Skew: {skew_pct*100:.2f}% (Limit: {self.max_straddle_width_pct*100:.0f}%)")
        print(f"      CE: ₹{ce_price:.2f} | PE: ₹{pe_price:.2f} | Diff: ₹{price_diff:.2f}")
        
        if skew_pct > self.max_straddle_width_pct:
            print(f"   ❌ Skew too high! Difference is {skew_pct*100:.1f}% of total premium")
            return False
        
        # 2. Check ADX (trend strength)
        # For simplicity, we'll use a basic ADX calculation from recent price action
        # In production, you'd want to use proper historical data
        try:
            # Fetch historical candle data for ADX calculation
            # This is a simplified version - ideally use proper historical API
            from lib.api.historical import get_historical_data
            
            # Get 1-minute candles for last 200 minutes to allow ADX to settle
            historical_data = get_historical_data(
                self.access_token,
                "NSE_INDEX|Nifty 50",
                "1minute",
                200
            )
            
            if historical_data is not None and len(historical_data) >= 28: # Need at least 2x period
                # Calculate ADX (returns value and timestamp of the last candle used)
                last_candle_time = historical_data[-1]['timestamp']
                adx_value = self.calculate_adx(historical_data)
                
                # Manage ADX History (Only add unique 1-min candles)
                # Store tuples: (timestamp, value)
                if not self.adx_history or self.adx_history[-1][0] != last_candle_time:
                    self.adx_history.append((last_candle_time, adx_value))
                    if len(self.adx_history) > 3:
                        self.adx_history.pop(0)
                        
                # ADX is falling if last 3 readings are declining (Strict check)
                if len(self.adx_history) >= 3:
                    current = self.adx_history[-1][1]
                    prev1 = self.adx_history[-2][1]
                    prev2 = self.adx_history[-3][1]
                    adx_falling = (current < prev1) and (prev1 < prev2)
                    history_str = f"[{prev2:.1f} -> {prev1:.1f} -> {current:.1f}]"
                else:
                    adx_falling = False # need more data
                    history_str = "(Need 3 mins data)"
                
                print(f"   📈 ADX(14): {adx_value:.2f} {history_str}")
                print(f"      Status: {'↘️ Falling' if adx_falling else '↗️ Rising/Unstable'}")
                
                # REVISED LOGIC:
                # 1. If ADX > 40: Too strong, don't enter regardless (Risk of continuation)
                # 2. If ADX 25-40: Enter ONLY if Falling (Trend cooling down)
                # 3. If ADX < 25: Safe to enter (Sideways/Weak trend)
                
                if adx_value >= 40:
                    print(f"   ❌ ADX too high! {adx_value:.2f} >= 40 (Strong Trend)")
                    return False
                    
                if adx_value > 25 and not adx_falling:
                    print(f"   ❌ ADX rising (strengthening trend)! {adx_value:.2f} > 25")
                    return False
                
                # If we get here:
                # - ADX < 25 (Safe)
                # - OR ADX 25-40 AND Falling (Cooling down) -> Safe
                print(f"   ✅ ADX condition met ({adx_value:.2f})")
                
                # 3. Check ATM OI PCR (Open Interest Balance)
                # Ensure "Smart Money" is also neutral/fighting at this level
                ce_oi_data = get_oi_data(self.option_chain_df, self.atm_strike, "CE")
                pe_oi_data = get_oi_data(self.option_chain_df, self.atm_strike, "PE")
                
                if ce_oi_data and pe_oi_data:
                    ce_oi = ce_oi_data['oi']
                    pe_oi = pe_oi_data['oi']
                    
                    if ce_oi > 0:
                        pcr = pe_oi / ce_oi
                        print(f"   📊 ATM PCR: {pcr:.2f} (Call OI: {ce_oi}, Put OI: {pe_oi})")
                        
                        if 0.5 <= pcr <= 2.0:
                            print(f"   ✅ OI is Balanced (0.5 <= {pcr:.2f} <= 2.0)")
                        else:
                            print(f"   ❌ OI Imbalance! Market biased (PCR {pcr:.2f})")
                            return False
                    else:
                        print("   ⚠️ Zero Call OI, skipping PCR check")
                else:
                    print("   ⚠️ OI Data unavailable, skipping PCR check")

            else:
                print("   ⚠️ Insufficient historical data for ADX, proceeding with caution")
                
        except ImportError:
            print("   ⚠️ Historical data module not available, skipping ADX check")
        except Exception as e:
            print(f"   ⚠️ ADX calculation error: {e}, proceeding with caution")
        
        print("   ✅ Entry conditions validated successfully")
        return True
    
    def calculate_adx(self, historical_data, period=14):
        """Calculate ADX using Wilder's Smoothing for better accuracy"""
        import pandas as pd
        import numpy as np
        
        df = pd.DataFrame(historical_data)
        
        # Calculate True Range using the previous close
        df['prev_close'] = df['close'].shift(1)
        df['h-l'] = df['high'] - df['low']
        df['h-pc'] = abs(df['high'] - df['prev_close'])
        df['l-pc'] = abs(df['low'] - df['prev_close'])
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        
        # Directional Movement
        df['h_diff'] = df['high'] - df['high'].shift(1)
        df['l_diff'] = df['low'].shift(1) - df['low']
        
        df['pdm'] = np.where((df['h_diff'] > df['l_diff']) & (df['h_diff'] > 0), df['h_diff'], 0)
        df['ndm'] = np.where((df['l_diff'] > df['h_diff']) & (df['l_diff'] > 0), df['l_diff'], 0)
        
        # Wilder's Smoothing (alpha = 1/n)
        alpha = 1 / period
        
        # Initialize first values (simple average) then smooth
        # However, ewm(alpha=...) matches Wilder's if adjust=False
        
        df['atr'] = df['tr'].ewm(alpha=alpha, adjust=False).mean()
        df['pdi'] = 100 * (df['pdm'].ewm(alpha=alpha, adjust=False).mean() / df['atr'])
        df['ndi'] = 100 * (df['ndm'].ewm(alpha=alpha, adjust=False).mean() / df['atr'])
        
        # DX
        df['dx'] = 100 * abs(df['pdi'] - df['ndi']) / (df['pdi'] + df['ndi'])
        
        # ADX (Smooth DX)
        adx = df['dx'].ewm(alpha=alpha, adjust=False).mean().iloc[-1]
        
        return adx
    
    
    def enter_initial_position(self):
        """Enter initial ATM straddle using Kotak"""
        
        # 0. SCAN FOR BEST DELTA STRIKE
        # Instead of just taking ATM, check ATM-50, ATM, ATM+50 to see which has lowest delta
        base_atm = self.atm_strike
        candidate_strikes = [base_atm - 50, base_atm, base_atm + 50]
        best_strike = base_atm
        min_delta = 999.0
        
        print(f"\n🔍 Scanning for best delta-neutral strike...")
        
        # Get lot size for delta calculation (assume same for all)
        # We need a dummy symbol to get lot size first, or just use 50/75 standard
        # But we can get it from the loop below
        
        for strike in candidate_strikes:
            # Fetch Greeks
            ce_greeks = get_greeks(self.option_chain_df, strike, "CE")
            pe_greeks = get_greeks(self.option_chain_df, strike, "PE")
            
            if not ce_greeks or not pe_greeks:
                continue
                
            # Calculate Straddle Delta (Sell CE + Sell PE)
            # Short Call Delta = -Delta
            # Short Put Delta = -Delta (Put delta is negative, so short put is positive)
            # Total = -(CE_Delta) - (PE_Delta)
            
            # Calculate net delta for this strike
            qty = self.lot_size
            ce_delta_total = ce_greeks['delta'] * qty
            pe_delta_total = pe_greeks['delta'] * qty
            
            # Net Delta = Short CE (-ve) + Short PE (+ve)
            # = ( -1 * ce_delta ) + ( -1 * pe_delta )
            # CE delta is positive (e.g. 0.5), PE delta is negative (e.g. -0.5)
            # Short CE -> -0.5
            # Short PE -> -(-0.5) = +0.5
            
            net_delta = (-1 * ce_delta_total) + (-1 * pe_delta_total)
            
            print(f"   Strike {strike}: Net Delta {net_delta:.2f} (CE: {ce_delta_total:.2f}, PE: {pe_delta_total:.2f})")
            
            if abs(net_delta) < abs(min_delta):
                min_delta = net_delta
                best_strike = strike
        
        self.atm_strike = best_strike
        print(f"🎯 Selected Best Strike: {self.atm_strike} (Est. Delta: {min_delta:.2f})")
        
        print(f"🚀 Entering initial straddle at {self.atm_strike}")
        
        # 1. Resolve Symbols (Upstox & Kotak)
        # Upstox Keys (for Data)
        ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
        pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
        
        # Kotak Symbols (for Execution)
        ce_token, ce_symbol_kotak = self.resolve_kotak_symbol(self.atm_strike, "CE")
        pe_token, pe_symbol_kotak = self.resolve_kotak_symbol(self.atm_strike, "PE")
        
        if not all([ce_key, pe_key, ce_symbol_kotak, pe_symbol_kotak]):
            print("❌ Failed to resolve instrument keys/symbols")
            return False
            
        # Get actual lot size
        self.lot_size = get_lot_size(self.kotak_broker.master_df, ce_symbol_kotak)
        print(f"📝 Trading Symbols: {ce_symbol_kotak}, {pe_symbol_kotak} | Lot Size: {self.lot_size}")

        # 2. Get Premium Data (Upstox for estimation)
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        
        if not ce_data or not pe_data:
            print("❌ Failed to get market data")
            return False
            
        ce_price = ce_data['ltp']
        pe_price = pe_data['ltp']
        
        print(f"📊 Est. Premium: CE ₹{ce_price:.2f}, PE ₹{pe_price:.2f}")
        
        # 3. Execute Orders (Kotak)
        print("🚀 Executing ORDERS via KOTAK NEO...")
        
        # Place CE Order
        ce_order_id = self.kotak_order_manager.place_order(
            symbol=ce_symbol_kotak, 
            qty=self.lot_size, 
            transaction_type="S", # Sell
            tag="STRADDLE_CE"
        )
        
        # Place PE Order
        pe_order_id = self.kotak_order_manager.place_order(
            symbol=pe_symbol_kotak, 
            qty=self.lot_size, 
            transaction_type="S", # Sell
            tag="STRADDLE_PE"
        )
        
        if not (ce_order_id and pe_order_id):
            print("❌ Order Placement Failed (Partial or Total)")
            if self.dry_run:
                print("   (Dry Run Mode - Proceeding despite 'failure' flags if any)")
            else:
                return False

        # 4. Track Positions
        ce_position = Position(
            strike=self.atm_strike, option_type="CE", quantity=self.lot_size,
            entry_price=ce_price, direction=-1, instrument_key=ce_key,
            kotak_symbol=ce_symbol_kotak, kotak_token=ce_token
        )
        
        pe_position = Position(
            strike=self.atm_strike, option_type="PE", quantity=self.lot_size,
            entry_price=pe_price, direction=-1, instrument_key=pe_key,
            kotak_symbol=pe_symbol_kotak, kotak_token=pe_token
        )
        
        self.positions.append(ce_position)
        self.positions.append(pe_position)
        
        self.total_premium_collected = (ce_price + pe_price) * self.lot_size
        
        print(f"✅ Initial straddle entered successfully")
        return True
    
    def check_and_hedge(self):
        """Check delta and execute hedging"""
        portfolio_delta = self.calculate_portfolio_delta()
        
        # Threshold Logic (Same as original)
        progressive_mult = self.delta_step_multiplier ** self.adjustment_count
        trigger_threshold = self.base_hedge_delta * progressive_mult
        target_threshold = self.base_target_delta * progressive_mult
        
        total_lots = sum(p.quantity for p in self.positions) / self.lot_size
        
        # Hysteresis
        if abs(portfolio_delta) > trigger_threshold:
            self.is_rebalancing = True
        if self.is_rebalancing and abs(portfolio_delta) <= target_threshold:
            self.is_rebalancing = False
            print(f"✨ Hysteresis: Target range reached. Stopping rebalancing.")

        effective_threshold = target_threshold if self.is_rebalancing else trigger_threshold

        if abs(portfolio_delta) <= effective_threshold:
            return

        # Safety Checks
        if self.adjustment_count >= self.max_adjustments:
            print(f"⚠️  Max Rounds Reached. Initiating Rolling Hedge.")
            self.execute_rolling_hedge(portfolio_delta)
            return

        if total_lots >= self.max_total_lots:
            print(f"⚠️  Max Lots Reached. Initiating Rolling Hedge.")
            self.execute_rolling_hedge(portfolio_delta)
            return
            
        # Execute Hedge
        print(f"⚠️  Action needed! Portfolio delta: {portfolio_delta:.1f}")
        
        # CORRECTED LOGIC:
        # Negative delta (bearish) → Sell PUT (adds positive delta to neutralize)
        # Positive delta (bullish) → Sell CALL (adds negative delta to neutralize)
        if portfolio_delta > effective_threshold:
            self.hedge_with_call_sell()  # SWAPPED: was put_sell
            self.adjustment_count += 1
        elif portfolio_delta < -effective_threshold:
            self.hedge_with_put_sell()  # SWAPPED: was call_sell
            self.adjustment_count += 1
            
        print("❄️ Hedge complete. Transitioning to COOLDOWN.")
        self.state = StrategyState.COOLDOWN
    
    def hedge_with_put_sell(self):
        """Hedge by selling additional PE via Kotak"""
        print(f"🔄 Hedging: Selling additional PE at ATM {self.atm_strike}")
        
        # Resolve
        pe_token, pe_symbol = self.resolve_kotak_symbol(self.atm_strike, "PE")
        pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
        
        # Execute
        order_id = self.kotak_order_manager.place_order(pe_symbol, self.lot_size, "S", tag="HEDGE_PE")
        if order_id:
             print(f"✅ Hedge Order Placed: {order_id}")
        
        # Data
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        entry_price = pe_data['ltp'] if pe_data else 0.0
        
        # Track
        pos = Position(self.atm_strike, "PE", self.lot_size, entry_price, -1, pe_key, pe_symbol, pe_token)
        self.positions.append(pos)
        self.total_premium_collected += entry_price * self.lot_size
        self.last_hedge_time = datetime.now()
        
        # Explicit Log
        self.log_to_file(f"ADJUSTMENT | Sold PE | Strike: {self.atm_strike} | Price: {entry_price} | Reason: Delta Hedging")

    def hedge_with_call_sell(self):
        """Hedge by selling additional CE via Kotak"""
        print(f"🔄 Hedging: Selling additional CE at ATM {self.atm_strike}")
        
        # Resolve
        ce_token, ce_symbol = self.resolve_kotak_symbol(self.atm_strike, "CE")
        ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
        
        # Execute
        order_id = self.kotak_order_manager.place_order(ce_symbol, self.lot_size, "S", tag="HEDGE_CE")
        if order_id:
             print(f"✅ Hedge Order Placed: {order_id}")
        
        # Data
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        entry_price = ce_data['ltp'] if ce_data else 0.0
        
        # Track
        pos = Position(self.atm_strike, "CE", self.lot_size, entry_price, -1, ce_key, ce_symbol, ce_token)
        self.positions.append(pos)
        self.total_premium_collected += entry_price * self.lot_size
        self.last_hedge_time = datetime.now()

        # Explicit Log
        self.log_to_file(f"ADJUSTMENT | Sold CE | Strike: {self.atm_strike} | Price: {entry_price} | Reason: Delta Hedging")

    def execute_rolling_hedge(self, current_delta: float):
        """Execute rolling hedge via Kotak"""
        print(f"\n🔄 ROLLING HEDGE TRIGGERED | Delta: {current_delta:.2f}")
        self.state = StrategyState.ROLLING
        
        losing_type = "PE" if current_delta > 0 else "CE"
        candidates = [p for p in self.positions if p.option_type == losing_type]
        
        if not candidates:
            print("❌ No candidates for rolling")
            self.state = StrategyState.MONITORING
            return

        # Select deepest ITM
        if losing_type == "PE":
            position_to_roll = max(candidates, key=lambda p: p.strike)
            new_strike = position_to_roll.strike - 100
        else:
            position_to_roll = min(candidates, key=lambda p: p.strike)
            new_strike = position_to_roll.strike + 100
            
        print(f"📍 Rolling {losing_type}: {position_to_roll.strike} -> {new_strike}")
        
        # 1. Close Old (Buy to Cover) - use actual position quantity
        print(f"   🔻 Closing {position_to_roll.kotak_symbol}")
        exit_oid = self.kotak_order_manager.place_order(position_to_roll.kotak_symbol, position_to_roll.quantity, "B", tag="ROLL_EXIT")
        if exit_oid: print(f"   ✅ Exit Order: {exit_oid}")
        
        # Capture realized P&L from the closed position
        closed_pnl = position_to_roll.unrealized_pnl
        self.realized_pnl += closed_pnl
        print(f"   💰 Realized P&L from roll: ₹{closed_pnl:.2f}")
        
        self.positions.remove(position_to_roll)
        
        # 2. Open New (Sell)
        ntoken, nsymbol = self.resolve_kotak_symbol(new_strike, losing_type)
        nkey = get_option_instrument_key("NIFTY", new_strike, losing_type, self.nse_data)
        
        # Use configured lot_size for consistency
        print(f"   ✅ Opening {nsymbol}")
        entry_oid = self.kotak_order_manager.place_order(nsymbol, self.lot_size, "S", tag="ROLL_ENTRY")
        if entry_oid: print(f"   ✅ Entry Order: {entry_oid}")
        
        # Track
        market_data = get_market_data(self.option_chain_df, new_strike, losing_type)
        entry_price = market_data['ltp'] if market_data else 0.0
        
        new_pos = Position(new_strike, losing_type, self.lot_size, entry_price, -1, nkey, nsymbol, ntoken)
        self.positions.append(new_pos)
        
        self.last_hedge_time = datetime.now()
        self.state = StrategyState.COOLDOWN
        
        # Explicit Log
        self.log_to_file(f"ADJUSTMENT | Rolling Hedge | Closed: {position_to_roll.kotak_symbol} | Opened: {nsymbol} | Realized PnL: {closed_pnl}")

    def check_exit_conditions(self) -> bool:
        """Check exit conditions (Same logic as original)"""
        pnl_info = self.calculate_pnl()
        total_pnl = pnl_info['total']
        greeks = self.calculate_portfolio_greeks()
        
        # Gamma Check
        if abs(greeks['gamma']) >= self.max_gamma:
            print(f"☢️  GAMMA BREACH! {abs(greeks['gamma']):.4f}")
            return True

        if self.current_stop_loss == 0.0:
            self.current_stop_loss = pnl_info['stop_loss']
            
        # Trailing SL Logic
        if total_pnl > self.peak_pnl:
            self.peak_pnl = total_pnl
            target = pnl_info['profit_target']
            if self.peak_pnl >= (target * self.trailing_sl_pnl_trigger):
                new_sl = self.peak_pnl * self.trailing_sl_lock_pct
                if new_sl > self.current_stop_loss:
                    self.current_stop_loss = new_sl
                    print(f"📈 Trailing SL updated: ₹{self.current_stop_loss:.2f}")

        # P&L Checks
        if total_pnl >= pnl_info['profit_target']:
            print(f"🎯 Profit target hit! ₹{total_pnl:.2f}")
            return True
            
        if total_pnl <= self.current_stop_loss:
            print(f"🛑 Stop loss hit! ₹{total_pnl:.2f}")
            return True
            
        # Time Check
        if datetime.now().time() >= dt_time(15, 15):
            print("⏰ Time exit")
            return True
            
        return False

    def display_status(self):
        """Display current portfolio status in a single concise line"""
        greeks = self.calculate_portfolio_greeks()
        pnl = self.calculate_pnl()
        mode = 'REBAL' if self.is_rebalancing else 'STABLE'
        
        # Get ATM prices for context
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        ce_price = ce_data['ltp'] if ce_data else 0.0
        pe_price = pe_data['ltp'] if pe_data else 0.0
        
        # Get Spot Price
        spot_price = self.option_chain_df['spot_price'].iloc[0] if not self.option_chain_df.empty else 0.0

        timestamp = datetime.now().strftime('%H:%M:%S')
        status_line = f"[{timestamp}] PNL: {pnl['total']:>8.2f} | NIFTY: {spot_price:.1f} | Delta: {greeks['delta']:>6.1f} | Mode: {mode:<6} | Pos: {len(self.positions)} | ATM: {self.atm_strike} (CE:{ce_price:.1f} PE:{pe_price:.1f})"
        print(status_line)
        
        # Log detailed state to file (still useful for history)
        log_msg = f"STATUS | P&L: {pnl['total']:.2f} | NIFTY: {spot_price:.1f} | Delta: {greeks['delta']:.1f} | Gamma: {greeks['gamma']:.4f} | PosCount: {len(self.positions)}"
        self.log_to_file(log_msg)

    def exit_strategy(self):
        """Close all positions using Kotak"""
        print("\n🏁 EXITING STRATEGY: Closing all positions...")
        
        # Consolidate positions by symbol to avoid duplicate orders
        positions_by_symbol = {}
        for pos in self.positions:
            if pos.kotak_symbol not in positions_by_symbol:
                positions_by_symbol[pos.kotak_symbol] = 0
            positions_by_symbol[pos.kotak_symbol] += pos.quantity
        
        # Execute consolidated exit orders
        for symbol, total_qty in positions_by_symbol.items():
            print(f"   Closing {total_qty} x {symbol}")
            self.kotak_order_manager.place_order(symbol, total_qty, "B", tag="STRATEGY_EXIT")
            
        self.positions.clear()
        self.is_running = False
        print("✅ All positions closed. Strategy Stopped.")

    def run(self, interval_seconds: int = 30):
        """Main FSM Loop"""
        print(f"🚀 Delta-Neutral Hybrid Strategy Running...")
        self.is_running = True
        self.state = StrategyState.INITIALIZING
        
        while self.is_running:
            try:
                if self.state == StrategyState.INITIALIZING:
                    if self.initialize():
                        self.state = StrategyState.WAITING_FOR_ENTRY
                    else:
                        self.state = StrategyState.STOPPED
                        
                elif self.state == StrategyState.WAITING_FOR_ENTRY:
                    # Skip entry if we already have positions (restored from Kotak)
                    if self.positions:
                        print("📌 Positions already exist (restored). Skipping entry.")
                        self.state = StrategyState.MONITORING
                    # Time check
                    elif datetime.now().time() >= self.entry_time:
                        self.state = StrategyState.ENTRY_EXECUTION
                    else:
                        print(f"⏳ Waiting... {datetime.now().strftime('%H:%M:%S')}")
                        time.sleep(min(interval_seconds, 60))
                        
                elif self.state == StrategyState.ENTRY_EXECUTION:
                    # Validate entry conditions before placing orders
                    if self.validate_entry_conditions():
                        if self.enter_initial_position():
                            self.state = StrategyState.MONITORING
                        else:
                            self.state = StrategyState.STOPPED
                    else:
                        print("⏸️  Entry conditions not met. Waiting for next check...")
                        # Wait and retry validation (go back to waiting)
                        time.sleep(10)  # Wait 10 seconds before retrying
                        self.state = StrategyState.WAITING_FOR_ENTRY
                        
                elif self.state == StrategyState.MONITORING:
                    self.refresh_option_chain()
                    # Display Detailed Status
                    self.display_status()
                    
                    if self.check_exit_conditions():
                        self.state = StrategyState.EXITING
                    else:
                        self.check_and_hedge()
                    
                    time.sleep(interval_seconds)
                    
                elif self.state == StrategyState.COOLDOWN:
                    if self.last_hedge_time:
                        elapsed = (datetime.now() - self.last_hedge_time).total_seconds()
                        if elapsed >= self.hedge_cooldown_minutes * 60:
                            self.state = StrategyState.MONITORING
                        else:
                            print(f"🧊 Cooling... {int(elapsed)}s")
                            time.sleep(interval_seconds)
                    else:
                        self.state = StrategyState.MONITORING
                        
                elif self.state == StrategyState.EXITING:
                    self.exit_strategy()
                    self.state = StrategyState.STOPPED
                    
                elif self.state == StrategyState.STOPPED:
                    break
                    
            except KeyboardInterrupt:
                print("\n🛑 Stopped by User")
                self.exit_strategy()
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(interval_seconds)

if __name__ == "__main__":
    from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
    from lib.api.market_data import download_nse_market_data
    
    print("🔬 TESTING Hybrid Strategy")
    
    # Upstox Auth
    if not check_existing_token():
        try:
            print("🔄 Token invalid or missing. Attempting to authenticate...")
            token = perform_authentication()
            save_access_token(token)
        except Exception as e:
            print(f"❌ Authentication Failed: {e}")
            sys.exit(1)
            
    # Load token (now guaranteed to exist if auth succeeded)
    with open("lib/core/accessToken.txt", "r") as f:
        token = f.read().strip()
    
    print("📥 Upstox Data...")
    nse_data = download_nse_market_data()
    
    # Initialize Strategy (Dry Run Mode)
    strategy = DeltaNeutralKotakStrategy(token, nse_data, dry_run=False)
    strategy.run(interval_seconds=5)
