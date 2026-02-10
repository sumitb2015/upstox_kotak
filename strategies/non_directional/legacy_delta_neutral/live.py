"""
Delta-Neutral Option Selling Strategy

A market-neutral strategy that sells ATM straddles and maintains delta neutrality
through automatic hedging using real-time Greeks from the option chain.

Strategy Flow:
1. Fetch option chain with Greeks using api/option_chain.py
2. Sell ATM straddle (CE + PE)
3. Monitor portfolio delta continuously
4. Auto-hedge when delta breaches thresholds
5. Exit on profit target or stop loss
"""

import sys
import os
# Add parent directory to path so we can import from api/
# File is now in strategies/upstox_only/ -> Root is ../../
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import time
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional
from enum import Enum, auto

# Import existing library functions
from lib.api.option_chain import (
    get_option_chain_dataframe, get_nearest_expiry,
    get_greeks, get_market_data, get_oi_data, get_premium_data,
    get_atm_strike_from_chain
)

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
from lib.api.order_management import place_order, get_order_book
from lib.api.market_quotes import get_ltp_quote
from lib.utils.instrument_utils import get_option_instrument_key


class Position:
    """Track individual option position with Greeks"""
    def __init__(self, strike: int, option_type: str, quantity: int, 
                 entry_price: float, direction: int, instrument_key: str):
        self.strike = strike
        self.option_type = option_type  # "CE" or "PE"
        self.quantity = quantity
        self.entry_price = entry_price
        self.direction = direction  # -1 for short, +1 for long
        self.instrument_key = instrument_key
        self.current_delta = 0.0
        self.current_price = 0.0
        self.unrealized_pnl = 0.0


class DeltaNeutralStrategy:
    """
    Delta-neutral option selling strategy with automatic position management.
    
    Uses existing library code:
    - api/option_chain.py for Greeks and market data
    - api/order_management.py for order placement
    - api/market_quotes.py for price quotes
    """
    
    def __init__(self, access_token: str, nse_data, lot_size: int = 65):
        self.access_token = access_token
        self.nse_data = nse_data
        
        # Validate lot_size
        if lot_size <= 0:
            raise ValueError(f"lot_size must be positive, got {lot_size}")
        self.lot_size = lot_size
        
        # Strategy parameters
        self.base_hedge_delta = 15.0  # Trigger threshold
        self.base_target_delta = 5.0  # Target threshold (Stop hedging once reached)
        self.delta_step_multiplier = 1.5  # Progressive widening
        self.max_adjustments = 3  # Max hedging rounds
        self.max_total_lots = 5  # Max lots across all positions
        self.hedge_cooldown_minutes = 5  # Min time between hedges
        
        # Entry/Exit parameters
        self.entry_time = dt_time(9, 20)  # Start after morning volatility
        self.profit_target_pct = 0.5  # 50% of collected premium
        self.stop_loss_multiplier = 0.3  # -0.3x collected premium (30% loss)
        
        self.trailing_sl_pnl_trigger = 0.25  # Start trailing at 25% of target
        self.trailing_sl_lock_pct = 0.50     # Lock 50% of peak P&L
        
        # Risk Management Limits
        self.max_gamma = 0.50              # Emergency exit if Gamma > 0.50
        
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
        
        # Status
        self.is_running = False
        self.last_hedge_time = None
        self.state = StrategyState.INITIALIZING
        
    def initialize(self):
        """Initialize strategy - fetch option chain and identify ATM"""
        print("🚀 Initializing Delta-Neutral Strategy...")
        
        # Get nearest expiry using library function
        self.expiry_date = get_nearest_expiry(self.access_token, "NSE_INDEX|Nifty 50")
        
        if not self.expiry_date:
            print("❌ Failed to get expiry date")
            return False
        
        print(f"📅 Using expiry: {self.expiry_date}")
        
        # Fetch option chain with all Greeks
        self.refresh_option_chain()
        
        if self.option_chain_df is None or self.option_chain_df.empty:
            print("❌ Failed to fetch option chain")
            return False
        
        # Get ATM strike
        self.atm_strike = get_atm_strike_from_chain(self.option_chain_df)
        print(f"🎯 ATM Strike identified: {self.atm_strike}")
        
        return True
    
    def refresh_option_chain(self):
        """Refresh option chain data with latest Greeks"""
        self.option_chain_df = get_option_chain_dataframe(
            self.access_token,
            "NSE_INDEX|Nifty 50",
            self.expiry_date
        )
    
    def calculate_portfolio_delta(self) -> float:
        """
        Calculate total portfolio delta.
        
        Uses get_greeks() from option_chain.py to get current deltas.
        """
        if not self.positions:
            return 0.0
        
        # Refresh option chain for latest Greeks
        self.refresh_option_chain()
        
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
                # Portfolio delta = position delta × quantity × direction
                # Direction: -1 for short (sold), +1 for long (bought)
                position_delta = greeks['delta'] * position.quantity * position.direction
                total_delta += position_delta
            else:
                print(f"⚠️  WARNING: Greeks unavailable for {position.option_type} strike {position.strike}")
        
        return total_delta
    
    def calculate_portfolio_greeks(self) -> Dict:
        """Calculate all portfolio Greeks"""
        # Refresh option chain for latest Greeks
        self.refresh_option_chain()
        
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
            else:
                print(f"⚠️  WARNING: Greeks unavailable for {position.option_type} strike {position.strike}")
        
        return {
            'delta': total_delta,
            'gamma': total_gamma,
            'theta': total_theta,
            'vega': total_vega
        }
    
    def calculate_pnl(self) -> Dict:
        """
        Calculate portfolio P&L.
        
        Uses get_market_data() from option_chain.py for current prices.
        """
        total_unrealized_pnl = 0.0
        
        for position in self.positions:
            # Get current market price using library function
            market = get_market_data(
                self.option_chain_df,
                position.strike,
                position.option_type
            )
            
            if market:
                position.current_price = market['ltp']
                # For short positions, profit = entry_price - current_price
                # For long positions, profit = current_price - entry_price
                pnl_per_unit = (position.entry_price - position.current_price) * position.direction * -1
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
    
    def enter_initial_position(self):
        """
        Enter initial ATM straddle.
        
        Uses existing library functions for order placement.
        """
        print(f"\n🎯 Entering initial ATM straddle at strike {self.atm_strike}")
        
        # Get instrument keys using library function
        ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
        pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
        
        if not ce_key or not pe_key:
            print("❌ Failed to get instrument keys")
            return False
        
        # Get current premiums
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        
        if not ce_data or not pe_data:
            print("❌ Failed to get market data")
            return False
        
        ce_price = ce_data['ltp']
        pe_price = pe_data['ltp']
        
        print(f"📊 CE Premium: ₹{ce_price:.2f}, PE Premium: ₹{pe_price:.2f}")
        print(f"💰 Total Premium: ₹{(ce_price + pe_price) * self.lot_size:.2f}")
        
        # Place orders using library function (paper trading for now)
        print("📝 Placing orders (Paper Trading)...")
        
        # Track positions
        ce_position = Position(
            strike=self.atm_strike,
            option_type="CE",
            quantity=self.lot_size,
            entry_price=ce_price,
            direction=-1,  # Short
            instrument_key=ce_key
        )
        
        pe_position = Position(
            strike=self.atm_strike,
            option_type="PE",
            quantity=self.lot_size,
            entry_price=pe_price,
            direction=-1,  # Short
            instrument_key=pe_key
        )
        
        self.positions.append(ce_position)
        self.positions.append(pe_position)
        
        self.total_premium_collected = (ce_price + pe_price) * self.lot_size
        
        print(f"✅ Initial straddle entered successfully")
        print(f"💵 Premium collected: ₹{self.total_premium_collected:.2f}")
        
        return True
    
    def check_and_hedge(self):
        """Check delta and execute hedging if needed with Hysteresis & Safety constraints"""
        portfolio_delta = self.calculate_portfolio_delta()
        
        # Calculate Progressive Thresholds
        progressive_mult = self.delta_step_multiplier ** self.adjustment_count
        trigger_threshold = self.base_hedge_delta * progressive_mult
        target_threshold = self.base_target_delta * progressive_mult
        
        # Check Total Lots
        total_lots = sum(p.quantity for p in self.positions) / self.lot_size
        
        # --- Hysteresis Logic ---
        # 1. Start rebalancing if delta crosses trigger threshold
        if abs(portfolio_delta) > trigger_threshold:
            self.is_rebalancing = True
            
        # 2. Stop rebalancing if delta is inside target threshold
        if self.is_rebalancing and abs(portfolio_delta) <= target_threshold:
            self.is_rebalancing = False
            print(f"✨ Hysteresis: Target range (±{target_threshold:.1f}) reached. Stopping rebalancing.")

        # Determine effective threshold based on current state
        # If we are in "rebalancing mode", we aim for the target (e.g. ±5)
        # If we are in "stable mode", we only act if we hit the trigger (e.g. ±15)
        effective_threshold = target_threshold if self.is_rebalancing else trigger_threshold

        print(f"\n📊 Strategy Status:")
        print(f"   Delta: {portfolio_delta:.1f} | Mode: {'🔄 REBALANCING' if self.is_rebalancing else '✅ STABLE'}")
        print(f"   Limits: Trigger ±{trigger_threshold:.1f} | Target ±{target_threshold:.1f}")
        print(f"   Rounds: {self.adjustment_count}/{self.max_adjustments} | Lots: {total_lots}/{self.max_total_lots}")

        if abs(portfolio_delta) <= effective_threshold:
            return

        # --- Safety Checks for Rebalancing ---
        
        # 1. Round Limit check
        if self.adjustment_count >= self.max_adjustments:
            print(f"⚠️  Limit Reached: Rounds ({self.adjustment_count}/{self.max_adjustments}). Initiating Rolling Hedge.")
            self.execute_rolling_hedge(portfolio_delta)
            return

        # 2. Total Lot Limit check
        if total_lots >= self.max_total_lots:
            print(f"⚠️  Limit Reached: Total Lots ({total_lots}/{self.max_total_lots}). Initiating Rolling Hedge.")
            self.execute_rolling_hedge(portfolio_delta)
            return

        # 3. Cooldown check
        if self.last_hedge_time:
            seconds_since_hedge = (datetime.now() - self.last_hedge_time).total_seconds()
            cooldown_period = self.hedge_cooldown_minutes * 60
            if seconds_since_hedge < cooldown_period:
                # We should be in COOLDOWN state
                print(f"❄️ Still in cooldown (Safety check). Transitioning to COOLDOWN state.")
                self.state = StrategyState.COOLDOWN
                return

        # --- Execute Hedge ---
        print(f"⚠️  Action needed! Portfolio delta: {portfolio_delta:.1f} (Effective Threshold: {effective_threshold:.1f})")
        print("🔄 Executing hedge...")
        
        if portfolio_delta > effective_threshold:
            print(f"🔴 Selling PE to rebalance")
            self.hedge_with_put_sell()
            self.adjustment_count += 1
        elif portfolio_delta < -effective_threshold:
            print(f"🔵 Selling CE to rebalance")
            self.hedge_with_call_sell()
            self.adjustment_count += 1
            
        # Transition to Cooldown after hedge
        print("❄️ Hedge complete. Transitioning to COOLDOWN.")
        self.state = StrategyState.COOLDOWN
    
    def hedge_with_put_sell(self):
        """Hedge by selling additional PE"""
        print(f"🔄 Hedging: Selling additional PE at ATM strike {self.atm_strike}")
        
        # Get PE data
        pe_data = get_market_data(self.option_chain_df, self.atm_strike, "PE")
        if not pe_data:
            print("❌ Failed to get PE data")
            return
        
        pe_key = get_option_instrument_key("NIFTY", self.atm_strike, "PE", self.nse_data)
        
        # Add hedge position
        hedge_position = Position(
            strike=self.atm_strike,
            option_type="PE",
            quantity=self.lot_size,
            entry_price=pe_data['ltp'],
            direction=-1,
            instrument_key=pe_key
        )
        
        self.positions.append(hedge_position)
        self.total_premium_collected += pe_data['ltp'] * self.lot_size
        
        print(f"✅ Hedge executed: Sold PE @ ₹{pe_data['ltp']:.2f}")
        self.last_hedge_time = datetime.now()
    
    def hedge_with_call_sell(self):
        """Hedge by selling additional CE"""
        print(f"🔄 Hedging: Selling additional CE at ATM strike {self.atm_strike}")
        
        # Get CE data
        ce_data = get_market_data(self.option_chain_df, self.atm_strike, "CE")
        if not ce_data:
            print("❌ Failed to get CE data")
            return
        
        ce_key = get_option_instrument_key("NIFTY", self.atm_strike, "CE", self.nse_data)
        
        # Add hedge position
        hedge_position = Position(
            strike=self.atm_strike,
            option_type="CE",
            quantity=self.lot_size,
            entry_price=ce_data['ltp'],
            direction=-1,
            instrument_key=ce_key
        )
        
        self.positions.append(hedge_position)
        self.total_premium_collected += ce_data['ltp'] * self.lot_size
        
        print(f"✅ Hedge executed: Sold CE @ ₹{ce_data['ltp']:.2f}")
        self.last_hedge_time = datetime.now()
    
    def execute_rolling_hedge(self, current_delta: float):
        """
        Execute rolling hedge when limits are reached.
        Strategy: Close ITM position and Roll to OTM strike.
        """
        print(f"\n🔄 ROLLING HEDGE TRIGGERED | Delta: {current_delta:.2f}")
        self.state = StrategyState.ROLLING
        
        # Determine losing side (The ITM side causing skew)
        # If Delta > 0, we have too much Positive Delta -> Short Puts are ITM
        # If Delta < 0, we have too much Negative Delta -> Short Calls are ITM
        losing_type = "PE" if current_delta > 0 else "CE"
        target_side = -1 if losing_type == "PE" else 1 # -1 for PE (to reduce +Delta), +1 for CE (to reduce -Delta)
        
        # 1. Find the deepest ITM position of losing type
        # For PE: Higher strike = More ITM
        # For CE: Lower strike = More ITM
        candidates = [p for p in self.positions if p.option_type == losing_type]
        if not candidates:
            print("❌ No candidates found for rolling hedge.")
            print("🔙 Reverting to MONITORING state.")
            self.state = StrategyState.MONITORING
            return

        if losing_type == "PE":
            position_to_roll = max(candidates, key=lambda p: p.strike) # Highest strike PE is deeply ITM
            new_strike = position_to_roll.strike - 100 # Move Down (OTM)
        else:
            position_to_roll = min(candidates, key=lambda p: p.strike) # Lowest strike CE is deeply ITM
            new_strike = position_to_roll.strike + 100 # Move Up (OTM)
            
        print(f"📍 rolling {losing_type}: Closing {position_to_roll.strike} -> Opening {new_strike}")
        
        # 2. Check Feasibility & Limits
        # Count current lots for this side
        side_lots = sum(p.quantity for p in self.positions if p.option_type == losing_type) / self.lot_size
        
        if side_lots > 3:
            print(f"🚫 Roll BLOCKED: Side limit exceeded ({side_lots} > 3).")
            print("🚨 Strategy Failed: Cannot roll without exceeding risk limits.")
            self.emergency_exit_all()
            return
            
        # 3. Execution (Paper Trade)
        # A. Close Old Position
        print(f"   🔻 Closing old position: {position_to_roll.strike} {losing_type}")
        self.positions.remove(position_to_roll) # Remove from logic tracking
        
        # B. Open New Position
        new_key = get_option_instrument_key("NIFTY", new_strike, losing_type, self.nse_data)
        market_data = get_market_data(self.option_chain_df, new_strike, losing_type)
        
        if not market_data:
            print("❌ Failed to get market data for new strike. Roll aborted.")
            print("🔙 Reverting to MONITORING state.")
            self.state = StrategyState.MONITORING
            return

        new_position = Position(
            strike=new_strike,
            option_type=losing_type,
            quantity=self.lot_size, # Start with 1 lot
            entry_price=market_data['ltp'],
            direction=-1,
            instrument_key=new_key
        )
        
        self.positions.append(new_position)
        print(f"   ✅ Rolled to new position: {new_strike} {losing_type} @ ₹{market_data['ltp']:.2f}")
        
        # Update trackers
        self.last_hedge_time = datetime.now()
        
        print("❄️ Rolling complete. Transitioning to COOLDOWN.")
        self.state = StrategyState.COOLDOWN

    def emergency_exit_all(self):
        """Close all positions immediately"""
        print("\n🚨 EMERGENCY EXIT TRIGGERED")
        self.state = StrategyState.EXITING # Or STOPPED? 
        # Ideally EXITING handlers do the work, but this function does it immediately.
        
        if not self.positions:
            print("   No positions to close.")
            self.is_running = False
            self.state = StrategyState.STOPPED
            return
            
        print(f"   Closing {len(self.positions)} positions...")
        # In paper mode, we just clear the list and update status
        # In live mode, place BUY orders
        for p in self.positions:
            print(f"   ❌ Closing {p.strike} {p.option_type} (Paper)")
        
        self.positions.clear()
        self.is_running = False
        print("   ✅ All positions closed.")
        self.state = StrategyState.STOPPED

    def check_exit_conditions(self) -> bool:
        """Check if any exit condition is met with Trailing SL & Gamma support"""
        greeks = self.calculate_portfolio_greeks()
        pnl_info = self.calculate_pnl()
        total_pnl = pnl_info['total']
        
        # 1. Check Gamma Risk (Emergency Exit)
        # Gamma for short options is negative. We check the absolute value for "exposure".
        abs_gamma = abs(greeks['gamma'])
        if abs_gamma >= self.max_gamma:
            print(f"\n☢️  GAMMA BREACH! Portfolio Gamma: {abs_gamma:.4f} (Limit: {self.max_gamma})")
            print("🚨 Emergency Exit: Gamma risk too high.")
            return True
        
        # 2. Initial Stop Loss if not set
        # Note: stop_loss is negative (e.g., -₹4,958 for 30% loss)
        if self.current_stop_loss == 0.0:
            self.current_stop_loss = pnl_info['stop_loss']
        
        # Update Peak P&L for Trailing SL
        if total_pnl > self.peak_pnl:
            self.peak_pnl = total_pnl
            
            # If we've hit the trigger (e.g. 25% of target), update trailing SL
            target = pnl_info['profit_target']
            if self.peak_pnl >= (target * self.trailing_sl_pnl_trigger):
                # Lock in a percentage of the peak profit
                # Trail SL = Peak P&L * 0.5 (or whatever lock pct is)
                # But don't move it lower than original SL
                new_sl = self.peak_pnl * self.trailing_sl_lock_pct
                if new_sl > self.current_stop_loss:
                    self.current_stop_loss = new_sl
                    print(f"📈 Trailing SL updated to: ₹{self.current_stop_loss:.2f} (Peak: ₹{self.peak_pnl:.2f})")
        
        # Check profit target
        if total_pnl >= pnl_info['profit_target']:
            print(f"\n🎯 Profit target hit! P&L: ₹{total_pnl:.2f}")
            return True
        
        # Check dynamic stop loss
        if total_pnl <= self.current_stop_loss:
            print(f"\n🛑 Stop loss hit! P&L: ₹{total_pnl:.2f} (Limit: ₹{self.current_stop_loss:.2f})")
            return True
        
        # Check time exit (3:15 PM)
        now = datetime.now().time()
        if now >= dt_time(15, 15):
            print(f"\n⏰ Time exit: Market closing")
            return True
        
        return False
    
    def display_status(self):
        """Display current portfolio status"""
        greeks = self.calculate_portfolio_greeks()
        pnl = self.calculate_pnl()
        
        print(f"\n{'='*80}")
        print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}")
        print(f"📊 Portfolio Greeks:")
        print(f"   Delta: {greeks['delta']:>8.1f} | Gamma: {greeks['gamma']:>8.4f} (Limit: {self.max_gamma})")
        print(f"   Theta: {greeks['theta']:>8.2f} | Vega:  {greeks['vega']:>8.2f}")
        print(f"\n💰 P&L Status:")
        print(f"   Premium Collected: ₹{pnl['premium_collected']:>10,.2f}")
        print(f"   Current P&L:       ₹{pnl['total']:>10,.2f} (Peak: ₹{self.peak_pnl:,.2f})")
        print(f"   Profit Target:     ₹{pnl['profit_target']:>10,.2f}")
        print(f"   Current SL:        ₹{self.current_stop_loss:>10,.2f}")
        print(f"\n📋 Positions: {len(self.positions)}")
        for i, pos in enumerate(self.positions, 1):
            direction_str = "SHORT" if pos.direction == -1 else "LONG"
            print(f"   {i}. {direction_str} {pos.strike} {pos.option_type} @ ₹{pos.entry_price:.2f} "
                  f"| Current: ₹{pos.current_price:.2f} | P&L: ₹{pos.unrealized_pnl:>8,.2f}")
        print(f"{'='*80}")
    
    def run(self, interval_seconds: int = 30):
        """Execute strategy using FSM Loop"""
        print(f"🚀 Delta-Neutral Strategy Running (FSM Mode)...")
        print(f"⏱️  Check interval: {interval_seconds} seconds")
        
        self.is_running = True
        self.state = StrategyState.INITIALIZING  # CRITICAL: Reset state
        
        while self.is_running:
            try:
                # Execute logic based on current state
                if self.state == StrategyState.INITIALIZING:
                    self._handle_initializing()
                elif self.state == StrategyState.WAITING_FOR_ENTRY:
                    self._handle_waiting_for_entry(interval_seconds)
                elif self.state == StrategyState.ENTRY_EXECUTION:
                    self._handle_entry_execution()
                elif self.state == StrategyState.MONITORING:
                    self._handle_monitoring(interval_seconds)
                elif self.state == StrategyState.REBALANCING:
                    self._handle_rebalancing()
                elif self.state == StrategyState.ROLLING:
                    # Rolling is handled by execute_rolling_hedge() which transitions to COOLDOWN
                    # If we're here, something went wrong
                    print("⚠️ Unexpected ROLLING state. Transitioning to MONITORING.")
                    self.state = StrategyState.MONITORING 
                elif self.state == StrategyState.COOLDOWN:
                    self._handle_cooldown(interval_seconds)
                elif self.state == StrategyState.EXITING:
                    self._handle_exiting()
                elif self.state == StrategyState.STOPPED:
                    break
                    
            except KeyboardInterrupt:
                print("\n🛑 Strategy stopped by user")
                self.exit_strategy()
                break
            except Exception as e:
                print(f"❌ Error in FSM Loop: {e}")
                # Optional: Transition to EXITING on critical error
                import traceback
                traceback.print_exc()
                time.sleep(interval_seconds)

    def _handle_initializing(self):
        """Handle INITIALIZING state"""
        if self.initialize():
            print("✅ Initialization Complete. Transitioning to WAITING_FOR_ENTRY.")
            self.state = StrategyState.WAITING_FOR_ENTRY
        else:
            print("❌ Initialization Failed. STOPPING.")
            self.state = StrategyState.STOPPED

    def _handle_waiting_for_entry(self, interval_seconds):
        """Handle WAITING_FOR_ENTRY state"""
        current_time = datetime.now().time()
        
        if current_time >= self.entry_time:
            print(f"⏰ Entry time {self.entry_time} reached. Transitioning to ENTRY_EXECUTION.")
            self.state = StrategyState.ENTRY_EXECUTION
        else:
            # Wait efficiently
            now = datetime.now()
            entry_datetime = datetime.combine(now.date(), self.entry_time)
            wait_seconds = (entry_datetime - now).total_seconds()
            
            print(f"⏳ Waiting for entry time... ({wait_seconds/60:.1f} min remaining)")
            sleep_time = min(interval_seconds, wait_seconds)
            time.sleep(sleep_time)

    def _handle_entry_execution(self):
        """Handle ENTRY_EXECUTION state"""
        try:
            if self.enter_initial_position():
                print("🚀 Positions Entered. Transitioning to MONITORING.")
                self.state = StrategyState.MONITORING
            else:
                print("❌ Entry Failed. STOPPING.")
                self.state = StrategyState.STOPPED
        except Exception as e:
            print(f"❌ Error during entry execution: {e}")
            import traceback
            traceback.print_exc()
            self.state = StrategyState.STOPPED

    def _handle_monitoring(self, interval_seconds):
        """Handle MONITORING state"""
        # 1. Refresh Data
        self.refresh_option_chain()
        self.display_status()
        
        # 2. Check Exits (includes time exit at 3:15 PM)
        if self.check_exit_conditions():
            self.state = StrategyState.EXITING
            return

        # 3. Check Hedging (Rebalancing or Rolling)
        self.check_and_hedge()
        
        # Sleep
        time.sleep(interval_seconds)

    def _handle_rebalancing(self):
        """Handle REBALANCING state (Safety fallback)"""
        # Rebalancing is handled by check_and_hedge() which transitions to COOLDOWN
        # If we're here, something went wrong
        print("⚠️ Unexpected REBALANCING state. Transitioning to MONITORING.")
        self.state = StrategyState.MONITORING

    def _handle_cooldown(self, interval_seconds):
        """Handle COOLDOWN state"""
        # Edge case: entered COOLDOWN without hedge time
        if not self.last_hedge_time:
            print("⚠️ No hedge time recorded. Returning to MONITORING.")
            self.state = StrategyState.MONITORING
            return
            
        seconds_since_hedge = (datetime.now() - self.last_hedge_time).total_seconds()
        cooldown_period = self.hedge_cooldown_minutes * 60
        
        if seconds_since_hedge >= cooldown_period:
            print("❄️ Cooldown complete. Resuming MONITORING.")
            self.state = StrategyState.MONITORING
            return
        
        # Still cooling down
        remaining = cooldown_period - seconds_since_hedge
        print(f"🧊 Cooling down... ({remaining:.0f}s left)")
        time.sleep(interval_seconds)

    def _handle_exiting(self):
        """Handle EXITING state"""
        print("🏁 Exiting strategy...")
        self.exit_strategy()
        self.state = StrategyState.STOPPED

    def exit_strategy(self):
        """Close all positions and cleanup"""
        print("\n📊 Final Status:")
        self.display_status()
        
        if self.positions:
            print(f"\n🔄 Closing {len(self.positions)} positions...")
            # In paper mode, just clear positions
            # In live mode, place BUY orders for each position
            for position in self.positions:
                print(f"   Closing {position.strike} {position.option_type}")
            self.positions.clear()
            print("✅ All positions closed")
        
        self.is_running = False
        print("🏁 Strategy stopped")

def main():
    """Test the delta-neutral strategy"""
    from lib.core.authentication import check_existing_token
    from lib.api.market_data import download_nse_market_data
    
    print("🚀 Delta-Neutral Option Strategy Test\n")
    
    # Get access token
    if not check_existing_token():
        print("❌ No access token found")
        return
    
    with open("lib/core/accessToken.txt", "r") as file:
        token = file.read().strip()
    
    # Load NSE data
    print("📥 Downloading NSE market data...")
    nse_data = download_nse_market_data()
    
    if nse_data is None:
        print("❌ Failed to download NSE data")
        return
    
    # Initialize strategy
    strategy = DeltaNeutralStrategy(
        access_token=token,
        nse_data=nse_data,
        lot_size=65
    )
    
    # Run strategy
    strategy.run(interval_seconds=5)


if __name__ == "__main__":
    main()
