"""
Dynamic Straddle Skew - Core Logic

This module handles:
- Premium skew detection between CE/PE
- Pyramiding triggers on winning side
- Defensive reduction logic
- Position state management
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional, List, Dict
from datetime import datetime
import threading

class LegPosition:
    """Tracks a single leg (CE or PE) within the straddle."""
    def __init__(self, option_type: str, strike: int, entry_price: float, 
                 lots: int, instrument_key: str):
        self.option_type = option_type
        self.strike = strike
        self.base_entry_price = entry_price  # Original entry price (before pyramiding)
        self.entry_price = entry_price       # Weighted average entry price
        self.current_price = entry_price
        self.lots = lots
        self.instrument_key = instrument_key
        self.lowest_price = entry_price
        self.entry_time = datetime.now()
        self.last_update_time = datetime.now()

    def update_price(self, price: float):
        self.current_price = price
        self.last_update_time = datetime.now()
        if price < self.lowest_price:
            self.lowest_price = price

    def reset_lowest_price(self, price: float):
        """Reset lowest price anchor (e.g., after a reduction event)."""
        self.lowest_price = price

    def add_lots(self, new_lots: int, price: float):
        """Update average entry price when adding lots."""
        total_cost = (self.entry_price * self.lots) + (price * new_lots)
        self.lots += new_lots
        self.entry_price = total_cost / self.lots if self.lots > 0 else 0

    def get_profit_pct(self) -> float:
        if self.entry_price == 0: return 0.0
        return (self.entry_price - self.current_price) / self.entry_price

    def get_recovery_pct_from_low(self) -> float:
        """Percentage price has recovered from its individual lowest point."""
        if self.lowest_price == 0: return 0.0
        return (self.current_price - self.lowest_price) / self.lowest_price

class DynamicStraddleSkewCore(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.ce_leg: Optional[LegPosition] = None
        self.pe_leg: Optional[LegPosition] = None
        self.lock = threading.RLock()
        
        # Internal State
        self.skew_persistence = {'CE': 0, 'PE': 0}
        
        # Strategy State
        self.winning_type = None  # 'CE' or 'PE'
        self.base_entered = False
        self.last_pyramid_price = 0.0
        self.last_pyramid_entry_price = 0.0 # Track entry price of specifically the last added lot
        self.last_pyramid_total_prem = 0.0 # Track total premium anchor
        self.last_reduction_map = {} # {'CE': (time, price), 'PE': ...}
        self.last_action_time = datetime.min # Global cooldown tracker
        
        # Profit Tracking
        self.max_profit_reached = 0.0
        self.locked_profit = 0.0
        self.initial_capital = 0.0 # Set by live.py on entry
        self.global_cooldown_seconds = 60 # 1 minute between aggressive actions

    def mark_action_executed(self):
        """Call this after any successful trade (Reduce, Pyramid, Roll)."""
        self.last_action_time = datetime.now()

    def is_global_cooldown_active(self) -> Tuple[bool, str]:
        """Check if we are in a global cooldown period."""
        elapsed = (datetime.now() - self.last_action_time).total_seconds()
        if elapsed < self.global_cooldown_seconds:
            return True, f"Global Cooldown ({elapsed:.0f}/{self.global_cooldown_seconds}s)"
        return False, ""

    def check_profit_goals(self, current_pnl: float) -> Tuple[bool, str]:
        """Check Max Profit and Profit Locking (Percentage Based)."""
        cfg = self.config
        
        # 0. Safety: No capital set yet
        if self.initial_capital <= 0: return False, ""
        
        # 1. Update High Water Mark
        if current_pnl > self.max_profit_reached:
            self.max_profit_reached = current_pnl
            
        # 2. Max Loss Check
        if current_pnl <= -abs(cfg['max_loss_per_day']):
            return True, f"Max Loss Hit: {current_pnl:.2f}"

        # 3. Target Profit (% of Capital)
        if cfg.get('target_profit_pct'):
            target_amt = self.initial_capital * cfg['target_profit_pct']
            if current_pnl >= target_amt:
                 return True, f"Target Profit Hit: {current_pnl:.2f} (> {cfg['target_profit_pct']*100:.1f}%)"
             
        # 4. Profit Locking (% of Peak Profit)
        pl_cfg = cfg.get('profit_locking', {})
        if pl_cfg.get('enabled'):
            lock_threshold = self.initial_capital * pl_cfg['lock_threshold_pct']
            
            if self.max_profit_reached >= lock_threshold:
                # 1. Determine Lock Ratio based on Tiers
                lock_ratio = 0.50 # Default Fallback
                
                # Check if 'lock_tiers' exists (New Config) or use 'lock_ratio' (Legacy)
                if 'lock_tiers' in pl_cfg:
                    for tier_profit, tier_ratio in pl_cfg['lock_tiers']:
                        if self.max_profit_reached >= tier_profit:
                            lock_ratio = tier_ratio
                else:
                    lock_ratio = pl_cfg.get('lock_ratio', 0.50)
                
                # 2. Calculate Lock Amount
                lock_amt = self.max_profit_reached * lock_ratio
                
                # Ensure lock amount never decreases (Ratchet)
                if lock_amt > self.locked_profit:
                    self.locked_profit = lock_amt
                
                if current_pnl <= lock_amt:
                    return True, f"Profit Lock Hit: {current_pnl:.2f} <= {lock_amt:.2f} (Peak: {self.max_profit_reached:.2f})"
                
        # 5. Individual Leg SL Check (Optional)
        sl_pct = cfg.get('individual_sl_pct')
        if sl_pct is not None:  # Only check if SL is enabled
            for leg in [self.ce_leg, self.pe_leg]:
                if leg:
                    loss_pct = (leg.current_price - leg.entry_price) / leg.entry_price
                    if loss_pct > sl_pct:
                        return True, f"{leg.option_type} Leg SL Hit: {loss_pct*100:.1f}% > {sl_pct*100:.1f}%"
        
        return False, ""

    def check_skew_signal(self, ce_price: float, pe_price: float) -> Optional[str]:
        """
        Detect which side is winning based on skew threshold.
        Requires Persistence: Condition must be True for N consecutive ticks.
        """
        if ce_price <= 0 or pe_price <= 0: return None
        
        # === Hysteresis Loop Fix (Total Premium) ===
        # If we recently reduced a leg, don't re-declare it winner immediately
        now = datetime.now()
        cooldown_sec = 120
        reentry_buffer_pct = 0.05
        
        def is_in_cooldown(chk_type):
            if chk_type in self.last_reduction_map:
                last_time, last_total_prem = self.last_reduction_map[chk_type]
                if (now - last_time).total_seconds() < cooldown_sec:
                    if self.ce_leg and self.pe_leg:
                        curr_tot = (self.ce_leg.current_price * self.ce_leg.lots) + \
                                   (self.pe_leg.current_price * self.pe_leg.lots)
                        # Strict re-entry check
                        if curr_tot > last_total_prem * (1 - reentry_buffer_pct):
                            return True
            return False

        thresh = self.config['skew_threshold_pct']
        persistence_target = self.config.get('skew_persistence_ticks', 3)
        
        # Reset counters if no skew detected this tick
        curr_ce_skew = False
        curr_pe_skew = False
        
        # Check CE Winning (Market going Down)
        if ce_price < pe_price * (1 - thresh):
            curr_ce_skew = True
        
        # Check PE Winning (Market going Up)
        if pe_price < ce_price * (1 - thresh):
            curr_pe_skew = True
            
        # Update Persistence Logic
        if curr_ce_skew:
            self.skew_persistence['CE'] += 1
            self.skew_persistence['PE'] = 0 # Reset opposition
        elif curr_pe_skew:
            self.skew_persistence['PE'] += 1
            self.skew_persistence['CE'] = 0
        else:
            self.skew_persistence['CE'] = 0
            self.skew_persistence['PE'] = 0
            
        # Return Confirmed Signal
        if self.skew_persistence['CE'] >= persistence_target:
            if not is_in_cooldown('CE'):
                # Reset counter after confirmation to avoid spamming (though caller handles state)
                return 'CE'
                
        if self.skew_persistence['PE'] >= persistence_target:
            if not is_in_cooldown('PE'):
                return 'PE'
            
        return None

    def check_pyramid_signal(self) -> Tuple[bool, str]:
        """
        Check if we should add another lot to the winning side.
        New Logic: Independent Leg Decay (Aggressive Trend Follow).
        Trigger: Winning Leg Price < Reference Price * (1 - decay_pct)
        Reference: Entry Price (first time) or Last Pyramid Price.
        """
        # 0. Global Cooldown Check
        is_cd, reason = self.is_global_cooldown_active()
        if is_cd: return False, reason

        if not self.winning_type or not self.ce_leg or not self.pe_leg:
            return False, "No winning side or leg missing"
            
        winning_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        losing_leg = self.pe_leg if self.winning_type == 'CE' else self.ce_leg
        
        # Max lots check
        if winning_leg.lots >= self.config['initial_lots'] + self.config['max_pyramid_lots']:
            return False, "Max pyramid lots reached"
            
        # Determine Reference Price (Independent Leg Tracking)
        if self.last_pyramid_price > 0:
            reference_price = self.last_pyramid_price
        else:
            reference_price = winning_leg.entry_price
            
        trigger_decay_pct = self.config.get('pyramid_trigger_decay_pct', 0.10)
        target_price = reference_price * (1 - trigger_decay_pct)
        
        # === Safety Checks ===
        # 1. Inversion Check
        if winning_leg.current_price >= losing_leg.current_price:
             return False, f"Inversion Detected: Winning {self.winning_type} ({winning_leg.current_price:.1f}) >= Losing ({losing_leg.current_price:.1f})"
        
        # 2. Lot Size Safety
        if winning_leg.lots < losing_leg.lots:
             return False, f"Lot Mismatch: Winning {self.winning_type} ({winning_leg.lots}) < Losing ({losing_leg.lots})"

        # 3. Net Profit Guard (Corrected)
        # Check if we are currently in a Net Profit state.
        # Logic: Total Entry Premium (Weighted) > Total Current Premium
        # (Since we are Shorting, Lower Current Premium = Profit)
        
        ce_entry_val = self.ce_leg.entry_price * self.ce_leg.lots
        pe_entry_val = self.pe_leg.entry_price * self.pe_leg.lots
        total_entry_prem = ce_entry_val + pe_entry_val
        
        current_total_prem = (self.ce_leg.current_price * self.ce_leg.lots) + (self.pe_leg.current_price * self.pe_leg.lots)
        
        # If Current Value > Entry Value, we are in a NET LOSS.
        if current_total_prem > total_entry_prem:
             return False, f"Net Loss Protection: Total Current {current_total_prem:.1f} > Entry {total_entry_prem:.1f}. Portfolio bleeding."

        # === Trigger Check ===
        if winning_leg.current_price < target_price:
            return True, f"{self.winning_type} Price {winning_leg.current_price:.1f} < Ref {reference_price:.1f} (-{trigger_decay_pct*100}%)"
            
        return False, "Decay threshold not hit"

    def check_reduction_signal(self) -> Tuple[bool, str]:
        """Check if we should reduce (defensive) the winning side."""
        if not self.winning_type:
            return False, "No winning side"
            
        winning_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        
        # Only reduce if we have pyramid lots
        if winning_leg.lots <= self.config['initial_lots']:
            return False, "No pyramid lots to reduce"
            
        # 1. Inversion Check (Critical Safety)
        # If the side we are pyramiding (Winning) becomes more expensive than the other side,
        # we are definitely on the wrong side. Reduce immediately.
        losing_leg = self.pe_leg if self.winning_type == 'CE' else self.ce_leg
        if winning_leg.current_price > losing_leg.current_price:
             return True, "INVERSION_CRITICAL"

        # 2. Recovery check
        recovery_thresh = self.config['reduction_recovery_pct']
        if winning_leg.get_recovery_pct_from_low() > recovery_thresh:
            return True, f"{self.winning_type} recovered {recovery_thresh*100}% from low"
            
        return False, "No reversal detected"

    def check_profit_booking_signal(self) -> Tuple[bool, str]:
        """
        Check if the last added pyramid lot has gained enough profit to book.
        Trigger: Current Price < Last Pyramid Entry * (1 - profit_booking_pct)
        """
        if not self.winning_type or self.last_pyramid_entry_price <= 0:
            return False, "No active pyramid lot to book"
            
        winning_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        
        # Safety: Ensure we actually have extra lots
        if winning_leg.lots <= self.config['initial_lots']:
             return False, "No pyramid lots"
             
        current_price = winning_leg.current_price
        entry_price = self.last_pyramid_entry_price
        
        target_gain_pct = self.config.get('pyramid_profit_booking_pct', 0.15)
        target_price = entry_price * (1 - target_gain_pct)
        
        if current_price < target_price:
            return True, f"Pyramid Lot Gain {target_gain_pct*100}% Hit: {current_price:.1f} < {target_price:.1f} (Entry: {entry_price:.1f})"
            
        return False, "Target not reached"

    def check_roll_signal(self) -> Tuple[bool, str]:
        """
        Check if we should ROLL the winning side to a closer strike.
        Trigger: Skew > 35% AND Winning Prem < Losing Prem * match_pct
        """
        # 0. Global Cooldown Check
        is_cd, reason = self.is_global_cooldown_active()
        if is_cd: return False, reason

        if not self.config.get('roll_adjustment_enabled', False):
            return False, "Disabled"
            
        if not self.winning_type or not self.ce_leg or not self.pe_leg:
            return False, "No winning side"
            
        winning_leg = self.ce_leg if self.winning_type == 'CE' else self.pe_leg
        losing_leg = self.pe_leg if self.winning_type == 'CE' else self.ce_leg
        
        # === Hybrid Logic Update: Pyramid First ===
        # If we have pyramided lots (Trend Following Mode), DO NOT Roll yet.
        # Only Roll if we hit Max Lots (Full Capacity) AND Skew is still high.
        # This prevents "Profit Booking" from killing the trend early.
        max_allowed_lots = self.config['initial_lots'] + self.config['max_pyramid_lots']
        
        if winning_leg.lots > self.config['initial_lots'] and winning_leg.lots < max_allowed_lots:
             return False, f"Pyramiding Active ({winning_leg.lots}/{max_allowed_lots}). Skipping Roll."
        
        w_price = winning_leg.current_price
        l_price = losing_leg.current_price
        
        if w_price <= 0 or l_price <= 0: return False, "Invalid prices"
        
        # 1. Skew Check
        # Skew = Difference / Max -> if PE=100, CE=50, Skew=50/100=50%
        skew = abs(w_price - l_price) / max(w_price, l_price)
        thresh = self.config.get('roll_skew_threshold', 0.40)
        
        if skew <= thresh:
            return False, f"Skew {skew*100:.1f}% <= {thresh*100:.1f}%"
            
        # 2. Premium Gap Check
        # We only roll if the winning leg is significantly cheaper (i.e. we are winning)
        # Verify winning leg is indeed cheaper
        if w_price >= l_price:
             return False, "Winning leg is not cheaper (Paradox)"
             
        # Check if gap is wide enough to warrant a roll
        # e.g. Win=30, Lose=90. Target=72 (0.8*90). 30 < 72 -> ROLL.
        match_ratio = self.config.get('roll_premium_match_pct', 0.80)
        target_prem = l_price * match_ratio
        
        if w_price < target_prem:
            return True, f"Skew {skew*100:.1f}% & Prem GAP: {w_price:.1f} < {target_prem:.1f} (Target)"
            
        return False, "Premium gap not wide enough"

    @abstractmethod
    def execute_trade(self, option_type: str, action: str, lots: int, price: float, strike: int = None):
        """Implement in live.py"""
        pass
