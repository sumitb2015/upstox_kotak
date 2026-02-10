"""
Option Scalper Strategy - Core Logic
Contains pure business logic for Depth Analysis, Momentum Detection, and Trade Lifecycle.
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple, Any

# Configure Logger
logger = logging.getLogger("OptionScalperCore")

class OptionScalperCore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.lock = threading.Lock()
        
        # State Variables
        self.current_entry_state = "WAITING"  # WAITING, IN_TRADE
        self.active_position = None
        
        # Market State (Shared between threads)
        self.ce_stats = {'imbalance': 0.0, 'has_buy_wall': False, 'has_sell_wall': False}
        self.pe_stats = {'imbalance': 0.0, 'has_buy_wall': False, 'has_sell_wall': False}
        
        self.tick_history_ce = [] # List of (timestamp, ltp) for CE
        self.tick_history_pe = [] # List of (timestamp, ltp) for PE
        
        # Configuration Shortcuts
        self.imbalance_threshold = config.get('depth_imbalance_threshold', 2.0)
        self.wall_size = config.get('depth_wall_size', 25000)
        self.momentum_threshold = config.get('momentum_threshold', 2.0)
        self.target_points = config.get('target_points', 10.0)
        self.stop_loss_points = config.get('stop_loss_points', 5.0)
        self.max_hold_time = config.get('max_hold_time_seconds', 180)
        
    def analyze_market_depth(self, depth_data: Dict[str, Any]) -> Tuple[float, bool, bool]:
        """
        Analyze market depth to determine Buy/Sell pressure.
        
        Args:
            depth_data: Dictionary extracted from market_quotes
            
        Returns:
            Tuple(Imbalance Ratio, Has Buy Wall, Has Sell Wall)
        """
        if not depth_data or 'buy' not in depth_data or 'sell' not in depth_data:
            return 0.0, False, False
            
        # 1. Total Quantity Analysis (Top 5)
        total_buy_qty = sum(item['quantity'] for item in depth_data['buy'])
        total_sell_qty = sum(item['quantity'] for item in depth_data['sell'])
        
        if total_sell_qty == 0:
            return 999.0, False, False # Infinite buy pressure
            
        imbalance_ratio = total_buy_qty / total_sell_qty
        
        # 2. Wall Detection
        # Check if any single order level has huge quantity
        avg_buy_qty = total_buy_qty / 5 if depth_data['buy'] else 0
        avg_sell_qty = total_sell_qty / 5 if depth_data['sell'] else 0
        
        has_buy_wall = any(item['quantity'] > self.wall_size for item in depth_data['buy'])
        has_sell_wall = any(item['quantity'] > self.wall_size for item in depth_data['sell'])
        
        return imbalance_ratio, has_buy_wall, has_sell_wall

    def check_momentum(self, current_ltp: float, timestamp: datetime, side: str) -> float:
        """
        Calculate momentum based on price change over last few ticks/seconds for a specific side.
        """
        history = self.tick_history_ce if side == "CE" else self.tick_history_pe
        
        # Add current tick
        history.append((timestamp, current_ltp))
        
        # Keep only last 60 seconds
        cutoff_time = timestamp.timestamp() - 60
        while history and history[0][0].timestamp() < cutoff_time:
            history.pop(0)
            
        if len(history) < 2:
            return 0.0
            
        # Compare current LTP with LTP at the start of the window
        start_ltp = history[0][1]
        momentum = current_ltp - start_ltp
        return momentum

    def check_entry_signal(self, 
                          imbalance_ratio: float, 
                          momentum: float, 
                          has_wall: bool,
                          side: str) -> bool:
        """
        Determine if entry conditions are met for Short Selling.
        SHORT Scalping Logic:
        - We SELL the option when we see STRENGTH in that direction (to collect fast decay/vol rejection).
        - Or we SELL when we see REJECTION.
        For this momentum scalper:
        - Signal = Buy Imbalance on CE -> Sell PE (Bullish view).
        - Signal = Sell Imbalance on CE -> Sell CE (Bearish view - betting on resistance).
        
        Let's stick to trend following:
        - Bullish Signal (Imbalance > threshold, Momentum +ve) -> SELL PE.
        - Bearish Signal (Sell Imbalance < 1/threshold, Momentum -ve) -> SELL CE.
        """
        if self.current_entry_state != "WAITING":
            return False
            
        threshold = self.imbalance_threshold
        mom_threshold = self.momentum_threshold
        
        mode = self.config.get('execution_mode', 'LONG')
        
        if side == "CE":
            # Bearish Signal: High Sell Volume/Wall on CE and Price falling
            # Imbalance < 0.5 (more sellers)
            if imbalance_ratio <= (1/threshold) and momentum <= -mom_threshold:
                logger.info(f"🐻 SHORT SIGNAL (CE): Ratio {imbalance_ratio:.2f} | Mom {momentum:.2f} | Wall {has_wall}")
                return True
        else:
            # Bullish Signal: High Buy Volume/Wall on PE and Price falling? 
            # No, for PE we want Buy Pressure on the Index -> Price of PE falling.
            # Usually, high Buy Quantity on PE = Support -> Sell PE.
            if imbalance_ratio >= threshold and momentum >= mom_threshold:
                 logger.info(f"🐂 SHORT SIGNAL (PE): Ratio {imbalance_ratio:.2f} | Mom {momentum:.2f} | Wall {has_wall}")
                 return True
            
        return False

    def check_exit_conditions(self, current_ltp: float, timestamp: datetime) -> Tuple[bool, str]:
        """
        Check if active trade should be exited.
        Returns: (Should Exit, Reason)
        """
        if self.current_entry_state != "IN_TRADE" or not self.active_position:
            return False, ""
            
        entry_price = self.active_position['entry_price']
        entry_time = self.active_position['entry_time']
        mode = self.config.get('execution_mode', 'LONG')
        
        # 1. Target Profit
        # LONG: LTP >= Entry + Target
        # SHORT: LTP <= Entry - Target
        if mode == "SHORT":
            if current_ltp <= entry_price - self.target_points:
                return True, "TARGET_REACHED"
        else:
            if current_ltp >= entry_price + self.target_points:
                return True, "TARGET_REACHED"
            
        # 2. Stop Loss
        # LONG: LTP <= Entry - SL
        # SHORT: LTP >= Entry + SL
        if mode == "SHORT":
            if current_ltp >= entry_price + self.stop_loss_points:
                return True, "STOP_LOSS_HIT"
        else:
            if current_ltp <= entry_price - self.stop_loss_points:
                return True, "STOP_LOSS_HIT"
            
        # 3. Time Decay Exit
        duration = (timestamp - entry_time).total_seconds()
        if duration >= self.max_hold_time:
            return True, "TIME_LIMIT_EXCEEDED"
            
        return False, ""

    def register_entry(self, price: float, timestamp: datetime, qty: int):
        with self.lock:
            self.current_entry_state = "IN_TRADE"
            self.active_position = {
                'entry_price': price,
                'entry_time': timestamp,
                'qty': qty,
                'highest_price': price
            }
        logger.info(f"🟢 ENTRY REGISTERED @ {price}")

    def register_exit(self, price: float, timestamp: datetime, reason: str):
        with self.lock:
            if not self.active_position: return
            
            pnl_factor = 1 if self.config.get('execution_mode', 'LONG') == 'LONG' else -1
            pnl = (price - self.active_position['entry_price']) * self.active_position['qty'] * pnl_factor
            
            duration = (timestamp - self.active_position['entry_time']).total_seconds()
            
            logger.info(f"🔴 EXIT REGISTERED @ {price} | PnL: {pnl:.2f} | Reason: {reason} | Time: {duration}s")
            
            self.current_entry_state = "WAITING"
            self.active_position = None

    def update_market_stats(self, instrument_key: str, imbalance: float, has_buy_wall: bool, has_sell_wall: bool, side: str):
        """Update shared market state from polling thread."""
        with self.lock:
            if side == "CE":
                self.ce_stats = {
                    'imbalance': imbalance,
                    'has_buy_wall': has_buy_wall,
                    'has_sell_wall': has_sell_wall
                }
            else:
                self.pe_stats = {
                    'imbalance': imbalance,
                    'has_buy_wall': has_buy_wall,
                    'has_sell_wall': has_sell_wall
                }
