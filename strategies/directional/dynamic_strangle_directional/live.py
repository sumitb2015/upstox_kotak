"""
Dynamic Strangle Strategy (Hybrid)
Entry: Short Strangle (~0.3 Delta)
Adjustment: Risk-ON (Winner In) -> Straddle -> Risk-OFF (Loser Out) based on CP +15%
"""

import sys
import os
import re
# Add parent directory to path so we can import from api/ and Kotak_Api/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Kotak_Api'))) # Commented to fix lib conflict

import time
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum, auto

# --- Upstox Imports (Data) ---
from lib.api.option_chain import (
    get_option_chain_dataframe,
    get_greeks, get_market_data, get_oi_data, 
    get_atm_strike_from_chain, get_atm_iv
)
from lib.api.market_data import get_market_quotes, fetch_historical_data
from lib.utils.instrument_utils import get_option_instrument_key, get_future_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy
from lib.utils.date_utils import calculate_days_to_expiry

# --- Kotak Imports (Execution) ---
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size

class StrategyState(Enum):
    INITIALIZING = auto()
    WAITING_FOR_ENTRY = auto()
    ENTRY_EXECUTION = auto()
    MONITORING = auto()
    ADJUSTING = auto()
    COOLDOWN = auto()
    EXITING = auto()
    STOPPED = auto()

class Position:
    """Track individual option position"""
    def __init__(self, strike: int, option_type: str, quantity: int, 
                 entry_price: float, direction: int, instrument_key: str,
                 kotak_symbol: str, kotak_token: int):
        self.strike = strike
        self.option_type = option_type
        self.quantity = quantity
        self.entry_price = entry_price
        self.direction = direction
        self.instrument_key = instrument_key
        self.kotak_symbol = kotak_symbol
        self.kotak_token = kotak_token
        self.current_price = 0.0
        self.unrealized_pnl = 0.0

class DynamicStrangleStrategy:
    
    def __init__(self, access_token: str, nse_data, 
                 lot_size: int = 65, 
                 target_delta: float = 0.30,
                 adjustment_pct: float = 0.15,  # Base adjustment (fallback)
                 min_adjustment_pct: float = 0.08,  # Minimum threshold (far from expiry - tight)
                 max_adjustment_pct: float = 0.25,  # Maximum threshold (near expiry - looser)
                 max_loss_points_dte_high: float = 20.0,  # Max point loss far from expiry
                 max_loss_points_dte_low: float = 10.0,   # Max point loss near expiry
                 stop_loss_pct: float = 0.60, # 60% of Premium Collected
                 fixed_stop_loss: float = None, # Optional Hard Cap
                 expiry_type: str = "current_week",
                 product_type: str = "MIS",
                 profit_target_pct: float = 0.60, # 60% of collected premium
                 trailing_sl_trigger_pct: float = 0.5, # Start trailing at 25% of target
                 dry_run: bool = False):
        
        self.access_token = access_token
        self.nse_data = nse_data
        self.product_type = product_type
        self.dry_run = dry_run
        
        # Expiry Selection: "current_week", "next_week", "monthly"
        if expiry_type not in ["current_week", "next_week", "monthly"]:
            raise ValueError(f"Invalid expiry_type: {expiry_type}. Must be 'current_week', 'next_week', or 'monthly'")
        self.expiry_type = expiry_type
        
        if lot_size <= 0: raise ValueError(f"lot_size must be positive")
        self.lot_size = lot_size
        
        # Strategy Param - Adaptive Adjustment (Hybrid: Percentage + Point Cap)
        self.target_entry_delta = target_delta
        self.base_adjustment_pct = adjustment_pct  # Fallback/default
        self.min_adjustment_pct = min_adjustment_pct  # Far from expiry (TIGHT to limit losses)
        self.max_adjustment_pct = max_adjustment_pct  # Near expiry (LOOSER since low premiums)
        self.max_loss_points_dte_high = max_loss_points_dte_high  # Point cap far from expiry
        self.max_loss_points_dte_low = max_loss_points_dte_low    # Point cap near expiry
        # Cooldown removed
        
        self.skew_guard_threshold = 0.40 # Guard for runaway legs (60% to allow asymmetry)
        
        self.entry_time = dt_time(9, 20)
        self.exit_time = dt_time(15, 18) # 3:18 PM Exit
        self.profit_target_pct = profit_target_pct
        self.fixed_stop_loss = fixed_stop_loss
        self.stop_loss_pct = stop_loss_pct
        
        self.trailing_sl_pnl_trigger = trailing_sl_trigger_pct
        self.trailing_sl_lock_pct = 0.50
        
        # Entry Validation (ADX Removed)
        
        # State
        self.positions: List[Position] = []
        self.realized_pnl = 0.0
        self.reference_combined_premium = 0.0
        self.total_premium_collected = 0.0  # Track total premium collected from entries
        self.initial_premium_collected = 0.0 # Track initial entry premium for profit target
        self.peak_pnl = 0.0
        self.current_stop_loss = self.fixed_stop_loss # Initialize to Fixed SL
        self.last_exit_time = None  # Track last exit for cooldown
        
        self.option_chain_df = None
        self.expiry_date = None
        self.atm_strike = None # Used for reference, but strategy tracks legs
        
        self.kotak_broker = None
        self.kotak_order_manager = None
        
        self.is_running = False
        self.last_hedge_time = None
        self._futures_key = None # Cache for NIFTY Futures Key
        self.state = StrategyState.INITIALIZING
        
        self.log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'dynamic_strangle')
        if not os.path.exists(self.log_dir):
            try: os.makedirs(self.log_dir)
            except: pass
        self.log_file = os.path.join(self.log_dir, f"dynamic_strangle_{datetime.now().strftime('%Y%m%d')}.log")

    def log_to_file(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{timestamp}] {message}\n")
        except: pass

    def initialize(self):
        print("🚀 Initializing Dynamic Strangle Strategy...")
        try:
            print("🔐 Authenticating Kotak Neo...")
            self.kotak_broker = BrokerClient()
            self.kotak_broker.authenticate()
            print("📥 Loading Kotak Master Data...")
            self.kotak_broker.load_master_data()
            self.kotak_order_manager = OrderManager(self.kotak_broker.client, dry_run=self.dry_run)
        except Exception as e:
            print(f"❌ Kotak Init Failed: {e}")
            return False

        print(f"📅 Selecting {self.expiry_type} expiry (using cache if available)...")
        try:
            expiry_str = get_expiry_for_strategy(
                access_token=self.access_token,
                expiry_type=self.expiry_type,
                instrument="NIFTY",
                force_refresh=False  # Use cache if available
            )
            self.expiry_date_datetime = datetime.strptime(expiry_str, "%Y-%m-%d")
            self.expiry_date = expiry_str
            print(f"📅 Selected {self.expiry_type} expiry: {expiry_str}")
        except Exception as e:
            print(f"❌ Expiry selection failed: {e}")
            return False
            
        self.refresh_option_chain()
        if self.option_chain_df is None or self.option_chain_df.empty: return False
        
        self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
        print(f"🎯 Current ATM: {self.atm_strike}")
        
        # We perform a fresh start usually, but could sync positions if needed
        # For this new strategy, let's assume fresh start or empty positions first
        return True

    def refresh_option_chain(self):
        self.option_chain_df = get_option_chain_dataframe(self.access_token, "NSE_INDEX|Nifty 50", self.expiry_date)
    
    def resolve_kotak_symbol(self, strike, option_type):
        token, symbol = get_strike_token(self.kotak_broker, strike, option_type, self.expiry_date_datetime)
        return token, symbol
    
    def calculate_days_to_expiry(self) -> float:
        """Calculate days to expiry (delegated to util)"""
        return calculate_days_to_expiry(self.expiry_date_datetime)
    
    def get_atm_iv(self) -> float:
        """Get ATM Implied Volatility (delegated to library)"""
        if self.option_chain_df is not None:
             return get_atm_iv(self.option_chain_df)
        return 15.0
    
    def get_futures_data(self) -> dict:
        """
        Get Data from NIFTY Futures (VWAP, LTP, Open)
        Returns dict with keys: 'vwap', 'ltp', 'open' or None
        
        Uses UpstoxAPI wrapper for clean, tested data fetching
        """
        try:
            # 1. Find NIFTY Futures Key (One time)
            if self._futures_key is None:
                from lib.utils.instrument_utils import get_future_instrument_key
                self._futures_key = get_future_instrument_key("NIFTY", self.nse_data)
                if self._futures_key:
                    print(f"🔒 Locked NIFTY Future for VWAP: {self._futures_key}")
            
            # 2. Fetch Data using Standardized Helpers
            if self._futures_key:
                from lib.api.market_data import get_vwap, get_market_quote_for_instrument
                
                data = {}
                
                # Fetch Full Quote (handles key mapping)
                quote = get_market_quote_for_instrument(self.access_token, self._futures_key)
                
                if quote:
                    # LTP and VWAP from same quote source for consistency
                    data['ltp'] = float(quote.get('last_price', 0.0))
                    data['vwap'] = float(quote.get('average_price', 0.0))
                    
                    # Open (from OHLC)
                    if 'ohlc' in quote and 'open' in quote['ohlc']:
                        data['open'] = float(quote['ohlc']['open'])
                    
                    if data.get('vwap', 0) > 0 and data.get('ltp', 0) > 0:
                        return data
                
        except Exception as e:
            print(f"⚠️ Futures Data Fetch Failed: {e}")
            import traceback
            traceback.print_exc()

        
        return None

    def get_yesterdays_close(self) -> float:
        """
        Fetch Yesterday's Close for NIFTY Futures.
        Returns: float or None
        """
        try:
            # 1. Find NIFTY Futures Key (One time)
            if self._futures_key is None:
                self._futures_key = get_future_instrument_key("NIFTY", self.nse_data)
            
            if not self._futures_key:
                print("⚠️ Could not resolve NIFTY Future Key")
                return None

            # 2. Fetch Historical Data (Last 5 days to handle weekends/holidays)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=5)
            
            # Use import from lib.api.market_data
            df = fetch_historical_data(
                self.access_token, 
                self._futures_key, 
                "days", 
                1, 
                start_date.strftime("%Y-%m-%d"), 
                end_date.strftime("%Y-%m-%d")
            )
            
            if df is not None and not df.empty:
                # Get the last completed candle (yesterday)
                # Ensure we are not picking today's candle if it exists in daily data (API dependency)
                today_str = datetime.now().strftime("%Y-%m-%d")
                df['date_str'] = df['timestamp'].dt.strftime("%Y-%m-%d")
                
                # Filter out today
                past_df = df[df['date_str'] < today_str]
                
                if not past_df.empty:
                    last_close = past_df.iloc[-1]['close']
                    last_date = past_df.iloc[-1]['date_str']
                    print(f"📉 Yesterday's Close ({last_date}): {last_close}")
                    return float(last_close)
                else:
                    print("⚠️ No past historical data found")
            else:
                print("⚠️ Failed to fetch historical data")

        except Exception as e:
            print(f"⚠️ Error fetching yesterday's close: {e}")
            
        return None

    def get_trend_direction(self) -> str:
        """
        Determine trend using VWAP + Momentum (LTP vs Open).
        Returns: "BULLISH", "BEARISH", or "NEUTRAL"
        """
        if self.option_chain_df is None:
            return "NEUTRAL"
        
        # Get Futures Data
        f_data = self.get_futures_data()
        
        # Handle Missing Data
        if f_data is None or 'vwap' not in f_data:
            print("⚠️ Futures Data Missing - Defaulting to NEUTRAL")
            return "NEUTRAL"
        
        vwap = f_data['vwap']
        ltp = f_data.get('ltp', 0)
        open_price = f_data.get('open', 0)
        
        # Fallback if LTP/Open missing (use Spot?)
        # Ideally use Futures LTP for consistency with VWAP
        if ltp == 0: ltp = self.option_chain_df['spot_price'].iloc[0]
        
        # Get Yesterday's Close
        y_close = self.get_yesterdays_close()
        
        # Fallback to Open if History Fails (or use Spot Close?)
        ref_price = y_close if y_close is not None else open_price
        ref_source = "Y_Close" if y_close is not None else "Today_Open"
        
        # Buffer
        buffer = 10
        
        # Logic with Momentum Filter (Modified to check vs Yesterday's Close)
        # Using a threshold to avoid noise (e.g., 0.05% of price ~10-12 pts or fixed buffer)
        trend_threshold = ltp * 0.0005 # 0.05% (~12 pts at 25000)
        
        # Bullish: Above VWAP AND Positive vs Yesterday's Close (> threshold)
        if ltp > vwap + buffer:
            if ltp > (ref_price + trend_threshold):
                return "BULLISH"
            else:
                print(f"⚠️ Trend Conflict: Above VWAP but not significantly above {ref_source} (LTP {ltp:.1f} vs {ref_price:.1f} + {trend_threshold:.1f} pts) -> NEUTRAL")
                return "NEUTRAL"
                
        # Bearish: Below VWAP AND Negative vs Yesterday's Close (< threshold)
        elif ltp < vwap - buffer:
            if ltp < (ref_price - trend_threshold):
                return "BEARISH"
            else:
                print(f"⚠️ Trend Conflict: Below VWAP but not significantly below {ref_source} (LTP {ltp:.1f} vs {ref_price:.1f} - {trend_threshold:.1f} pts) -> NEUTRAL")
                return "NEUTRAL"
        
        return "NEUTRAL"
    
    def get_max_point_loss_for_dte(self, dte: float) -> float:
        """
        Calculate maximum acceptable point loss based on DTE.
        INVERTED LOGIC: Lower point tolerance far from expiry, higher near expiry.
        
        Far from expiry: Tight point control (avoid big losses on high premiums)
        Near expiry: Looser point control (low premiums anyway)
        """
        if dte >= 7:
            return self.max_loss_points_dte_high  # e.g., 20 points
        elif dte >= 3:
            # Interpolate: 20 → 15
            range_start = self.max_loss_points_dte_high
            range_end = (self.max_loss_points_dte_high + self.max_loss_points_dte_low) / 2
            return range_start - ((range_start - range_end) * (7 - dte) / 4)
        elif dte >= 1:
            # Interpolate: 15 → 12
            range_start = (self.max_loss_points_dte_high + self.max_loss_points_dte_low) / 2
            range_end = self.max_loss_points_dte_low + 2
            return range_start - ((range_start - range_end) * (3 - dte) / 2)
        else:
            # Last day: 12 → 10
            return self.max_loss_points_dte_low + (2 * dte)
    
    def calculate_adaptive_adjustment_threshold(self) -> float:
        """
        CORRECTED HYBRID APPROACH:
        Calculate threshold based on acceptable point losses, then derive percentage.
        
        Key change: INVERTED DTE logic
        - Far from expiry: LOW % (e.g., 8-10%) to limit point losses on high premiums
        - Near expiry: HIGH % (e.g., 20-25%) since absolute values are small anyway
        
        Returns: Adaptive adjustment percentage (e.g., 0.08 to 0.25)
        """
        dte = self.calculate_days_to_expiry()
        current_cp = self.reference_combined_premium
        atm_iv = self.get_atm_iv()
        
        # Get max acceptable point loss for this DTE
        max_point_loss = self.get_max_point_loss_for_dte(dte)
        
        # Calculate required percentage to hit this point loss
        if current_cp > 0:
            calculated_pct = max_point_loss / current_cp
        else:
            calculated_pct = self.min_adjustment_pct
        
        # --- Premium-Based Adjustment (INVERTED) ---
        # High premiums: Already caught by point cap, use calculated %
        # Low premiums: Increase % to avoid over-adjustment
        
        if current_cp < 30:
            premium_multiplier = 1.2  # +20% for very low premiums
        elif current_cp < 50:
            premium_multiplier = 1.1  # +10%
        elif current_cp < 100:
            premium_multiplier = 1.0  # No change
        else:
            premium_multiplier = 1.0  # High premiums use point cap
        
        # --- Volatility-Based Adjustment (INVERTED) ---
        # High IV: Tighter % (not looser) to avoid runaway moves
        # Low IV: Slightly looser % (less noise)
        # Note: API returns IV as percentage (11.63 = 11.63%), not fraction
        
        if atm_iv > 25:      # High IV (> 25%)
            vol_multiplier = 0.95  # -5% (tighter in high vol)
        elif atm_iv > 18:    # Medium-high IV (18-25%)
            vol_multiplier = 1.0   # No change
        elif atm_iv > 12:    # Medium-low IV (12-18%)
            vol_multiplier = 1.0   # No change
        else:                # Low IV (< 12%)
            vol_multiplier = 1.05  # +5% (slightly looser in low vol)
        
        # --- Combine All Factors ---
        adjusted_pct = calculated_pct * premium_multiplier * vol_multiplier
        
        # --- Apply Bounds ---
        final_pct = max(self.min_adjustment_pct, min(self.max_adjustment_pct, adjusted_pct))
        
        return final_pct

    def get_current_combined_premium(self):
        cp = 0.0
        for p in self.positions:
            md = get_market_data(self.option_chain_df, p.strike, p.option_type)
            if md:
                p.current_price = md['ltp']
                cp += p.current_price
        return cp

    def calculate_pnl(self):
        unrealized = 0.0
        for p in self.positions:
            md = get_market_data(self.option_chain_df, p.strike, p.option_type)
            if md:
                p.current_price = md['ltp']
                unrealized += (p.current_price - p.entry_price) * p.direction * p.quantity
        
        total = self.realized_pnl + unrealized
        # Calculate profit target based on INITIAL premium collected (Standard Strangle Logic)
        # Re-summing active positions causes target to shift during adjustments unexpectedly
        base_premium = self.initial_premium_collected if self.initial_premium_collected > 0 else 0
        profit_target = base_premium * self.profit_target_pct if base_premium > 0 else float('inf')
        
        return {
            "total": total, 
            "unrealized": unrealized, 
            "realized": self.realized_pnl,
            "stop_loss": self.current_stop_loss,
            "profit_target": profit_target
        }

    def validate_entry(self):
        current_time = datetime.now().time()
        if current_time < self.entry_time:
            print(f"⏳ Waiting for entry time {self.entry_time} (Current: {current_time.strftime('%H:%M:%S')})")
            return False
        return True

    def enter_initial_position(self):
        print(f"🔄 Refreshing Option Chain & ATM before entry...")
        self.refresh_option_chain()
        if self.option_chain_df is None or self.option_chain_df.empty:
            print("❌ Failed to refresh chain!")
            return False
            
        self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
        print(f"🎯 Updated ATM: {self.atm_strike}")
        
        # Detect trend
        trend = self.get_trend_direction()
        f_data = self.get_futures_data()
        vwap = f_data['vwap'] if f_data and 'vwap' in f_data else None
        futures_ltp = f_data.get('ltp', 0) if f_data else 0
        spot_price = self.option_chain_df['spot_price'].iloc[0]
        
        vwap_str = f"{vwap:.1f}" if vwap is not None else "N/A"
        print(f"📊 Trend: {trend} | FUT: {futures_ltp:.1f} (Spot: {spot_price:.1f}) | VWAP: {vwap_str} | Buffer: ±10pts")
        
        if trend != "NEUTRAL":
            # DIRECTIONAL ENTRY: Asymmetric strike selection (15% gap)
            print(f"⚡ {trend} trend detected - using ASYMMETRIC strike selection (15% gap)")
            result = self._select_asymmetric_strikes(trend)
        else:
            # NEUTRAL: Symmetric strike selection (original logic)
            print(f"🔍 NEUTRAL market - using SYMMETRIC strike selection (target delta ~{self.target_entry_delta})")
            result = self._select_symmetric_strikes()
        
        if not result:
            return False
        
        best_ce_strike, best_pe_strike, ce_choice, pe_choice = result
        
        print(f"🎯 Selected Strangle:")
        print(f"   CE {best_ce_strike} | Price: {ce_choice['ltp']:.1f} | Delta: {ce_choice['delta']:.2f}")
        print(f"   PE {best_pe_strike} | Price: {pe_choice['ltp']:.1f} | Delta: {pe_choice['delta']:.2f}")
        print(f"   Gap: {abs(ce_choice['ltp'] - pe_choice['ltp']):.2f} ({abs(ce_choice['ltp'] - pe_choice['ltp']) / max(ce_choice['ltp'], pe_choice['ltp']) * 100:.1f}%)")


        # Execute
        for strike, otype in [(best_ce_strike, "CE"), (best_pe_strike, "PE")]:
             token, sym = self.resolve_kotak_symbol(strike, otype)
             key = get_option_instrument_key("NIFTY", strike, otype, self.nse_data)
             
             # Get Dynamic Lot Size (Validation only)
             base_lot = get_lot_size(self.kotak_broker.master_df, sym)
             
             # Order uses User Configured Quantity
             qty = self.lot_size
             if qty % base_lot != 0:
                 print(f"⚠️ Warning: Configured quantity {qty} is not a multiple of lot size {base_lot}")
             
             order_id = self.kotak_order_manager.place_order(sym, qty, "S", tag="ENTRY", product=self.product_type)
             
             if order_id:
                 # Track
                 md = get_market_data(self.option_chain_df, strike, otype)
                 price = md['ltp'] if md else 0.0
                 pos = Position(strike, otype, qty, price, -1, key, sym, token)
                 self.positions.append(pos)
                 self.total_premium_collected += price * qty
             else:
                 print(f"❌ Entry Order Failed for {sym}. Position not tracked.")
             
        if not self.positions:
            print("❌ No positions were successfully entered. Staying in WAITING state.")
            return False

        self.reference_combined_premium = sum(p.entry_price for p in self.positions)
        self.initial_premium_collected = self.total_premium_collected # Store for stable profit target
        print(f"✅ Entry Complete. Ref CP: {self.reference_combined_premium:.2f} | Initial Credit: {self.initial_premium_collected:.2f}")

        # Set initial stop loss using ratcheting logic
        self.update_stop_loss(is_initial=True)

        return True
    
    def _select_symmetric_strikes(self):
        """Original symmetric strike selection (delta-based, minimal price gap)"""
        # Collect Candidates (Delta 0.15 to 0.50)
        ce_candidates = []
        pe_candidates = []
        
        # Scan CE (ATM to ATM+1500)
        for strike in range(self.atm_strike, self.atm_strike + 1500, 50):
            g = get_greeks(self.option_chain_df, strike, "CE")
            md = get_market_data(self.option_chain_df, strike, "CE")
            if g and md:
                delta = g.get('delta', 0)
                ltp = md.get('ltp', 0)
                if 0.15 <= delta <= 0.50:
                    ce_candidates.append({'strike': strike, 'ltp': ltp, 'delta': delta})

        # Scan PE (ATM to ATM-1500)
        for strike in range(self.atm_strike, self.atm_strike - 1500, -50):
            g = get_greeks(self.option_chain_df, strike, "PE")
            md = get_market_data(self.option_chain_df, strike, "PE")
            if g and md:
                delta = abs(g.get('delta', 0))
                ltp = md.get('ltp', 0)
                if 0.15 <= delta <= 0.50:
                    pe_candidates.append({'strike': strike, 'ltp': ltp, 'delta': delta})
                    
        # Find Best Match (Score = PriceDiff + DeltaPenalty)
        best_pair = None
        min_score = 99999.0
        DELTA_WEIGHT = 200.0
        
        for ce in ce_candidates:
            for pe in pe_candidates:
                price_diff = abs(ce['ltp'] - pe['ltp'])
                avg_delta = (ce['delta'] + pe['delta']) / 2
                delta_deviation = abs(avg_delta - self.target_entry_delta)
                score = price_diff + (delta_deviation * DELTA_WEIGHT)
                
                if score < min_score:
                    min_score = score
                    best_pair = (ce, pe)
                    
        if not best_pair:
             print("❌ Could not find suitable symmetric candidates!")
             return None
             
        ce_choice, pe_choice = best_pair
        return (ce_choice['strike'], pe_choice['strike'], ce_choice, pe_choice)
    
    def _select_asymmetric_strikes(self, trend):
        """Asymmetric strike selection for directional markets (15% price gap)"""
        
        if trend == "BULLISH":
            # CE further OTM (safer), PE closer (will collect more)
            # Target: CE price ≈ 85% of PE price (CE 15% cheaper)
            ce_range = range(self.atm_strike + 200, self.atm_strike + 800, 50)
            pe_range = range(self.atm_strike - 100, self.atm_strike - 400, -50)
            target_ratio = 0.85  # CE/PE ratio
        else:  # BEARISH
            # PE further OTM (safer), CE closer (will collect more)
            # Target: CE price ≈ 118% of PE price (PE 15% cheaper)
            ce_range = range(self.atm_strike + 100, self.atm_strike + 400, 50)
            pe_range = range(self.atm_strike - 200, self.atm_strike - 800, -50)
            target_ratio = 1.18  # CE/PE ratio
        
        # Collect candidates
        ce_candidates = []
        pe_candidates = []
        
        for ce_strike in ce_range:
            g = get_greeks(self.option_chain_df, ce_strike, "CE")
            md = get_market_data(self.option_chain_df, ce_strike, "CE")
            if g and md:
                delta = g.get('delta', 0)
                ltp = md.get('ltp', 0)
                # Still enforce delta bounds
                if 0.15 <= delta <= 0.35:
                    ce_candidates.append({'strike': ce_strike, 'ltp': ltp, 'delta': delta})
        
        for pe_strike in pe_range:
            g = get_greeks(self.option_chain_df, pe_strike, "PE")
            md = get_market_data(self.option_chain_df, pe_strike, "PE")
            if g and md:
                delta = abs(g.get('delta', 0))
                ltp = md.get('ltp', 0)
                if 0.15 <= delta <= 0.35:
                    pe_candidates.append({'strike': pe_strike, 'ltp': ltp, 'delta': delta})
        
        # Find best pair matching target ratio
        best_pair = None
        min_score = 99999.0
        
        for ce in ce_candidates:
            for pe in pe_candidates:
                # Calculate actual ratio
                if pe['ltp'] > 0:
                    actual_ratio = ce['ltp'] / pe['ltp']
                else:
                    continue
                
                # Score based on ratio deviation and delta deviation
                ratio_deviation = abs(actual_ratio - target_ratio)
                delta_deviation = abs(ce['delta'] - pe['delta'])
                
                # Prioritize ratio matching (100x weight), then delta
                score = (ratio_deviation * 100) + (delta_deviation * 50)
                
                if score < min_score:
                    min_score = score
                    best_pair = (ce, pe)
        
        if not best_pair:
            # Fallback to symmetric if asymmetric fails
            print(f"⚠️ Could not find asymmetric pair for {trend} trend, falling back to symmetric")
            return self._select_symmetric_strikes()
        
        ce_choice, pe_choice = best_pair
        return (ce_choice['strike'], pe_choice['strike'], ce_choice, pe_choice)

    
    def update_stop_loss(self, is_initial=False):
        """
        Update stop loss using hybrid ratcheting approach:
        - Calculate SL based on net credit (premium collected + realized PnL)
        - Only allow SL to tighten, never loosen
        
        Args:
            is_initial: True if this is the first SL calculation at entry
        """
        if self.stop_loss_pct <= 0:
            # No dynamic SL configured
            if self.fixed_stop_loss is not None:
                self.current_stop_loss = self.fixed_stop_loss
            return
        
        # Calculate net credit (total premium collected + realized PnL)
        # Realized PnL is negative for losses, so this reduces net credit
        net_credit = self.total_premium_collected + self.realized_pnl
        
        # Calculate SL based on net credit
        calculated_sl = -1 * net_credit * self.stop_loss_pct
        
        if is_initial:
            # First time setting SL
            self.current_stop_loss = calculated_sl
            print(f"🛑 Stop Loss Set: {self.current_stop_loss:.2f} ({self.stop_loss_pct:.1%} of Net Credit {net_credit:.2f})")
            
            # Use fixed if tighter
            if self.fixed_stop_loss is not None and self.fixed_stop_loss > self.current_stop_loss:
                self.current_stop_loss = self.fixed_stop_loss
                print(f"   Using Fixed SL: {self.fixed_stop_loss:.2f} (tighter)")
        else:
            # Ratcheting logic: Only tighten, never loosen
            # More negative = looser SL, less negative = tighter SL
            if calculated_sl > self.current_stop_loss:
                # Would make SL looser (more negative), don't update
                print(f"📍 SL unchanged: {self.current_stop_loss:.2f} (would loosen to {calculated_sl:.2f})")
            else:
                # Making SL tighter (less negative), update it
                old_sl = self.current_stop_loss
                self.current_stop_loss = calculated_sl
                print(f"📈 SL Tightened: {old_sl:.2f} → {self.current_stop_loss:.2f} (Net Credit: {net_credit:.2f})")
                self.log_to_file(f"SL RATCHET | Old: {old_sl:.2f} | New: {self.current_stop_loss:.2f} | Net Credit: {net_credit:.2f}")
            
            # Always respect fixed SL if it's tighter
            if self.fixed_stop_loss is not None and self.fixed_stop_loss > self.current_stop_loss:
                if self.current_stop_loss != self.fixed_stop_loss:
                    print(f"   Overriding with Fixed SL: {self.fixed_stop_loss:.2f}")
                    self.current_stop_loss = self.fixed_stop_loss


    def check_adjustment_conditions(self):
        current_cp = self.get_current_combined_premium()
        
        # Guard: Skip if reference premium is not set
        if self.reference_combined_premium <= 0:
            print("⚠️ Warning: Reference premium is 0, skipping adjustment check")
            return
        
        # --- ADAPTIVE THRESHOLD CALCULATION (HYBRID) ---
        adaptive_pct = self.calculate_adaptive_adjustment_threshold()
        dte = self.calculate_days_to_expiry()
        atm_iv = self.get_atm_iv()
        
        # Get DTE-based point cap
        max_point_cap = self.get_max_point_loss_for_dte(dte)
        
        # Calculate increase using percentage
        increase_pct = self.reference_combined_premium * adaptive_pct
        
        # Apply HYBRID constraint: Use lower of percentage-based or point cap
        increase = min(increase_pct, max_point_cap)
        threshold = self.reference_combined_premium + increase
        effective_pct = (increase / self.reference_combined_premium) if self.reference_combined_premium > 0 else 0

        print(f"📊 CP: {current_cp:.2f} | Ref: {self.reference_combined_premium:.2f} | Trig: {threshold:.2f} (+{increase:.1f}pts/{effective_pct:.1%})")
        print(f"🧠 Adaptive: {adaptive_pct:.1%} → {increase:.1f}pts (cap: {max_point_cap:.0f}pts) | DTE: {dte:.2f}d | IV: {atm_iv:.1f}%")
        
        if current_cp >= threshold:
            msg = f"⚠️ ADAPTIVE ADJUSTMENT | CP: {current_cp:.2f} >= {threshold:.2f} (+{increase:.1f}pts/{effective_pct:.1%}, DTE: {dte:.2f}d)"
            print(msg)
            self.log_to_file(msg)
            self.execute_metric_adjustment(current_cp)
            return

        # ---------------------------
        # Hard Skew Guard
        # ---------------------------
        ce_pos = next((p for p in self.positions if p.option_type == "CE"), None)
        pe_pos = next((p for p in self.positions if p.option_type == "PE"), None)
        
        if ce_pos and pe_pos:
            p1 = ce_pos.current_price
            p2 = pe_pos.current_price
            if max(p1, p2) > 0:
                skew_ratio = min(p1, p2) / max(p1, p2)
                # Use a configurable threshold (e.g., 0.50 or same as balancing 0.60)
                # Providing a default guard threshold of 0.50 if not explicitly set
                guard_threshold = getattr(self, 'skew_guard_threshold', 0.50)
                
                if skew_ratio < guard_threshold:
                    msg = f"🛡️ SKEW GUARD TRIGGERED | Ratio: {skew_ratio:.2f} < {guard_threshold} (CE: {p1:.1f}, PE: {p2:.1f})"
                    print(msg)
                    self.log_to_file(msg)
                    self.execute_metric_adjustment(current_cp)
                    return



    def execute_metric_adjustment(self, current_cp):
        # Identify Winner/Loser
        ce_pos = next((p for p in self.positions if p.option_type == "CE"), None)
        pe_pos = next((p for p in self.positions if p.option_type == "PE"), None)
        
        if not ce_pos or not pe_pos: return
        
        ce_gain = (ce_pos.entry_price - ce_pos.current_price) # Positive if price dropped
        pe_gain = (pe_pos.entry_price - pe_pos.current_price)
        
        # Tested Leg = The one losing money (Price Increased)
        # Untested Leg = The one making money (Price Decreased)
        if ce_pos.current_price > ce_pos.entry_price and pe_pos.current_price < pe_pos.entry_price:
            tested, untested = ce_pos, pe_pos
        elif pe_pos.current_price > pe_pos.entry_price and ce_pos.current_price < ce_pos.entry_price:
            tested, untested = pe_pos, ce_pos
        else:
            # Both losing or both winning? Pick the one with higher LTP as tested
            if ce_pos.current_price > pe_pos.current_price: tested, untested = ce_pos, pe_pos
            else: tested, untested = pe_pos, ce_pos
            
        print(f"⚠️ Tested: {tested.option_type} ({tested.strike}) | Untested: {untested.option_type} ({untested.strike})")
        
        is_straddle = (ce_pos.strike == pe_pos.strike)
        
        if not is_straddle:
            # PHASE 1: RISK-ON (Converge)
            # Close Untested, Move Inward to Match Premium of Tested
            print(f"⚔️ Phase 1: Risk-ON (Converging) | Target Premium: {tested.current_price:.2f}")
            self.close_position(untested)
            
            # Find New Strike matching Tested Premium
            target_premium = tested.current_price
            best_strike = untested.strike
            min_diff = 99999.0
            
            # Search Grid: Move from Untested Strike TOWARDS Tested Strike (Converging)
            # If PE is Untested & Low, we need Higher Premium => Move Up (Higher Strike)
            # If CE is Untested & Low, we need Higher Premium => Move Down (Lower Strike)
            
            step = 50
            search_start = untested.strike
            # Limit search to not cross the tested strike (convert to straddle at most)
            
            if untested.option_type == "PE":
                # PE: Higher Strike = Higher Price. Move UP.
                search_range = range(search_start + step, tested.strike + step, step)
            else:
                # CE: Lower Strike = Higher Price. Move DOWN.
                search_range = range(search_start - step, tested.strike - step, -step)
            
            # Edge case: if search_range is empty (already at/near tested strike)
            if not search_range:
                print(f"⚠️ Already near tested strike, using tested strike: {tested.strike}")
                best_strike = tested.strike
                min_diff = 0
            else:
                for strike in search_range:
                    md = get_market_data(self.option_chain_df, strike, untested.option_type)
                    if md:
                        price = md['ltp']
                        diff = abs(price - target_premium)
                        
                        if diff < min_diff:
                            min_diff = diff
                            best_strike = strike
                        
                        # If we overshoot significantly, we might stop, but prices are noisy so full scan is safer 
                        # within the bounded range (Untested -> Tested)
            
            print(f"🎯 Matched Strike: {best_strike} (Diff: {min_diff:.2f})")
            self.open_position(best_strike, untested.option_type)
            
        else:
            # PHASE 2: RISK-OFF (Defend)
            # Close Tested, Move Outward
            print("🛡️ Phase 2: Risk-OFF (Defending)")
            self.close_position(tested)
            
            # New Strike: 1 step away
            step = 50
            if tested.option_type == "PE":
                new_strike = tested.strike - step # Move Down
            else:
                new_strike = tested.strike + step # Move Up
                
            self.open_position(new_strike, tested.option_type)
            
        # Update Reference to NEW Combined Premium (Post-Adjustment)
        # We must re-calculate because we changed legs, and the new CP is the new baseline.
        new_cp = self.get_current_combined_premium()
        self.reference_combined_premium = new_cp
        msg = f"METRIC ADJUSTMENT COMPLETE | New Ref CP: {self.reference_combined_premium:.2f} | Old Trig CP: {current_cp:.2f}"
        print(f"✅ {msg}")
        self.log_to_file(msg)
        
        # Update stop loss after adjustment (ratcheting logic)
        self.update_stop_loss(is_initial=False)

    def close_position(self, pos):
        print(f"🔻 Closing {pos.kotak_symbol}")
        self.kotak_order_manager.place_order(pos.kotak_symbol, self.lot_size, "B", tag="ADJ_EXIT", product=self.product_type)
        
        pnl = (pos.entry_price - pos.current_price) * pos.quantity # Short Position PnL
        self.realized_pnl += pnl
        self.positions.remove(pos)
        self.log_to_file(f"CLOSE | {pos.kotak_symbol} | PnL: {pnl:.2f}")

    def open_position(self, strike, otype):
        token, sym = self.resolve_kotak_symbol(strike, otype)
        key = get_option_instrument_key("NIFTY", strike, otype, self.nse_data)
        
        # Get Dynamic Lot Size (Validation)
        base_lot = get_lot_size(self.kotak_broker.master_df, sym)
        qty = self.lot_size
        
        print(f"⬆️ Opening {sym}")
        self.kotak_order_manager.place_order(sym, qty, "S", tag="ADJ_ENTRY", product=self.product_type)
        
        md = get_market_data(self.option_chain_df, strike, otype)
        price = md['ltp'] if md else 0.0
        
        pos = Position(strike, otype, qty, price, -1, key, sym, token)
        self.positions.append(pos)
        self.total_premium_collected += price * qty
        self.log_to_file(f"OPEN | {sym} | Price: {price:.2f}")

    def display_status(self):
        pnl = self.calculate_pnl()
        cp = self.get_current_combined_premium()
        spot = self.option_chain_df['spot_price'].iloc[0] if self.option_chain_df is not None else 0
        
        ts = datetime.now().strftime('%H:%M:%S')
        pos_str = " | ".join([f"{p.option_type}{p.strike}({p.current_price:.1f})" for p in self.positions])
        
        print(f"[{ts}] PnL: {pnl['total']:>8.1f} | NIFTY: {spot:.1f} | CP: {cp:.1f} (Ref: {self.reference_combined_premium:.1f}) | {pos_str}")
        self.log_to_file(f"STATUS | PnL: {pnl['total']} | CP: {cp}")

    def exit_strategy(self):
        print("🏁 Exiting...")
        for p in list(self.positions):
            self.close_position(p)
        self.is_running = False

    def run(self, interval=5):
        self.is_running = True
        if not self.initialize(): return
        
        self.state = StrategyState.WAITING_FOR_ENTRY
        while self.is_running:
            try:
                # 0. Global Kill Switch Check
                if os.path.exists("c:/algo/upstox/.STOP_TRADING"):
                    print("🛑 Global Kill Switch Detected (.STOP_TRADING). Stopping Strategy.")
                    self.exit_strategy()
                    self.is_running = False
                    break

                if self.state == StrategyState.WAITING_FOR_ENTRY:
                    if self.validate_entry():
                        if self.enter_initial_position():
                            self.state = StrategyState.MONITORING
                    else: time.sleep(10)
                
                elif self.state == StrategyState.MONITORING:
                    self.refresh_option_chain()
                    self.display_status()
                    self.check_adjustment_conditions()
                    
                    # Exit Checks
                    pnl = self.calculate_pnl()
                    
                    # Trailing Stop-Loss Logic
                    if pnl['total'] > self.peak_pnl:
                        self.peak_pnl = pnl['total']
                        
                        # Check if we've hit trigger threshold (25% of target)
                        if self.peak_pnl >= (pnl['profit_target'] * self.trailing_sl_pnl_trigger):
                            # Calculate new trailing SL (50% of peak)
                            new_sl = self.peak_pnl * self.trailing_sl_lock_pct
                            
                            # Only move SL up, never down
                            if new_sl > self.current_stop_loss:
                                self.current_stop_loss = new_sl
                                print(f"📈 Trailing SL Updated: ₹{self.current_stop_loss:.2f} (Peak: ₹{self.peak_pnl:.2f})")
                    
                    # Check exit conditions
                    if pnl['total'] <= self.current_stop_loss:
                        print(f"🛑 Stop Loss Hit! PnL: {pnl['total']:.2f} | SL: {self.current_stop_loss:.2f}")
                        self.log_to_file(f"STOP LOSS HIT | PnL: {pnl['total']:.2f} | SL: {self.current_stop_loss:.2f}")
                        
                        # Close all positions
                        for p in list(self.positions):
                            self.close_position(p)
                        
                        # Reset state for re-entry
                        self.peak_pnl = 0.0
                        self.current_stop_loss = self.fixed_stop_loss
                        self.reference_combined_premium = 0.0
                        self.last_exit_time = datetime.now()
                        
                        # Enter cooldown instead of exiting
                        self.state = StrategyState.COOLDOWN
                        print("🧊 Entering 5-minute cooldown before re-entry...")
                        
                    elif pnl['total'] >= pnl['profit_target']:
                        print(f"🎉 Profit Target Hit! PnL: {pnl['total']:.2f} (Target: {pnl['profit_target']:.2f})")
                        self.state = StrategyState.EXITING
                    
                    # Time Exit
                    elif datetime.now().time() >= self.exit_time:
                        print(f"⏰ Time Exit Triggered! Current: {datetime.now().strftime('%H:%M:%S')}")
                        self.state = StrategyState.EXITING
                    
                    time.sleep(interval)
                
                elif self.state == StrategyState.COOLDOWN:
                    if self.last_exit_time:
                        elapsed = (datetime.now() - self.last_exit_time).total_seconds()
                        cooldown_duration = 5 * 60  # 5 minutes
                        
                        if elapsed >= cooldown_duration:
                            print("✅ Cooldown complete. Checking for re-entry...")
                            self.state = StrategyState.WAITING_FOR_ENTRY
                        else:
                            remaining = int(cooldown_duration - elapsed)
                            print(f"🧊 Cooldown: {remaining}s remaining...")
                            time.sleep(min(interval, 30))  # Check every 30s during cooldown
                    else:
                        self.state = StrategyState.WAITING_FOR_ENTRY
                
                elif self.state == StrategyState.EXITING:
                    self.exit_strategy()
                    break
                    
            except KeyboardInterrupt:
                self.exit_strategy()
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(interval)

if __name__ == "__main__":
    from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
    from lib.api.market_data import download_nse_market_data
    
    # Auth Logic
    if not check_existing_token():
        try:
            token = perform_authentication()
            save_access_token(token)
        except: sys.exit(1)
            
    with open("lib/core/accessToken.txt", "r") as f: token = f.read().strip()
    nse_data = download_nse_market_data()
    
    strategy = DynamicStrangleStrategy(
        token, nse_data, 
        lot_size=130,                # Trading Quantity (1 Lot)
        target_delta=0.2,          # Initial Entry Delta
        
        # --- CORRECTED ADAPTIVE ADJUSTMENT (HYBRID APPROACH) ---
        # INVERTED LOGIC: Lower % far from expiry, higher % near expiry
        adjustment_pct=0.15,        # Base adjustment (fallback, rarely used)
        min_adjustment_pct=0.08,    # Minimum threshold (far from expiry - TIGHT)
        max_adjustment_pct=0.25,    # Maximum threshold (near expiry - LOOSER)
        
        # POINT CAPS: Control absolute rupee losses
        max_loss_points_dte_high=20.0,  # Max 20 points loss far from expiry
        max_loss_points_dte_low=10.0,   # Max 10 points loss near expiry
        
        stop_loss_pct=0.60,         # MAX LOSS = 60% of Premium
        fixed_stop_loss=None,       # No hard cap

        profit_target_pct=0.60,      # Capture 60% of collected premium
        trailing_sl_trigger_pct=0.25,# Delay trailing until 25% of target reached
        
        expiry_type="current_week",  # Options: "current_week", "next_week", "monthly"
        product_type="MIS",         # "MIS" = Intraday, "NRML" = Margin/Carry Forward
        dry_run=False
    )
    strategy.run()
