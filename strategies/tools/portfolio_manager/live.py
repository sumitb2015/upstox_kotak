"""
Portfolio Manager - Live Execution
----------------------------------
Monitors Global P&L for Kotak account and triggers square-off if limits are hit.
Acts as a kill-switch for all other strategies.
"""

import sys
import os
import time
import logging
from datetime import datetime

# Adjust Python Path to reach project root
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root not in sys.path:
    sys.path.append(root)

from strategies.tools.portfolio_manager.config import CONFIG, validate_config
from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager

# Logging Setup
logger = logging.getLogger("PortfolioManager")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class PortfolioManager:
    def __init__(self):
        self.broker = None
        self.order_manager = None
        self.running = False
        self.running = False
        self.pnl_history = [] 
        self.highest_profit = -float('inf') # Track highest PnL for trailing lock
        
    def get_active_lock(self):
        """Calculate the currently locked profit based on high water mark."""
        if 'PROFIT_LOCKING' not in CONFIG:
            return 0.0
            
        step_lock = 0.0
        current_buffer = None
        
        # Iterate to find:
        # 1. The max step lock we've achieved
        # 2. The trailing buffer corresponding to the highest level reached
        for level in CONFIG['PROFIT_LOCKING']:
            if self.highest_profit >= level['reach']:
                step_lock = max(step_lock, level['lock_min'])
                current_buffer = level.get('trail_buffer')
        
        # Calculate Trailing Lock if valid buffer found
        trail_lock = 0.0
        if current_buffer is not None:
             trail_lock = self.highest_profit - current_buffer
            
        return max(step_lock, trail_lock)
        
    def initialize(self):
        """Connect to Kotak API."""
        logger.info("🚀 Initializing Portfolio Manager...")
        try:
            validate_config()
            self.broker = BrokerClient()
            self.broker.authenticate()
            # We don't necessarily need master data unless we are doing symbol resolution, 
            # but order manager might need it. Let's load it to be safe.
            self.broker.load_master_data() 
            self.order_manager = OrderManager(self.broker.client, dry_run=CONFIG['DRY_RUN'])
            logger.info("✅ Connected to Kotak Neo API")
            return True
        except Exception as e:
            logger.error(f"❌ Initialization Failed: {e}")
            return False

    def get_global_pnl(self):
        """Calculate Total Realized + Unrealized P&L for the day."""
        try:
            positions_resp = self.broker.positions()
            
            if not positions_resp or not isinstance(positions_resp, dict):
                logger.warning("⚠️ Could not fetch positions")
                return 0.0, []

            data = positions_resp.get('data', [])
            if not data:
                return 0.0, []
            
            total_pnl = 0.0
            open_positions = []
            open_tokens = []
            
            # 1. Identify Open Positions and Calculate Net Qty
            for pos in data:
                # Calculate Net Qty Manually
                fl_buy = float(pos.get('flBuyQty', 0))
                fl_sell = float(pos.get('flSellQty', 0))
                cf_buy = float(pos.get('cfBuyQty', 0))
                cf_sell = float(pos.get('cfSellQty', 0))
                
                net_qty = int((fl_buy + cf_buy) - (fl_sell + cf_sell))
                pos['netQty'] = net_qty # Inject for later use
                
                if net_qty != 0:
                    open_positions.append(pos)
                    # For quotes, we need instrument token and exchange segment
                    open_tokens.append({
                        "instrument_token": pos.get('tok'),
                        "exchange_segment": pos.get('exSeg', 'nse_fo')
                    })
            
            # 2. Fetch LTPs for Open Positions
            ltp_map = {}
            if open_tokens:
                try:
                    # Fetch LTPs in batch
                    quotes = self.broker.client.quotes(instrument_tokens=open_tokens, quote_type="ltp")
                    
                    # Handle both List and Dict response formats
                    q_data = []
                    if isinstance(quotes, list):
                        q_data = quotes
                    elif isinstance(quotes, dict) and 'message' in quotes:
                        q_data = quotes['message']
                    
                    if not q_data:
                        logger.warning(f"[WARN] No quotes data received. Response: {quotes}")
                        
                    for q in q_data:
                        tk = str(q.get('instrument_token', ''))
                        # API can return 'ltp' or 'last_price'
                        lp = float(q.get('ltp', q.get('last_price', 0)))
                        ex_tk = str(q.get('exchange_token', '')) 
                        
                        if tk: ltp_map[tk] = lp
                        if ex_tk: ltp_map[ex_tk] = lp
                        
                    # Fallback Check
                    for ot in open_tokens:
                        tk = str(ot['instrument_token'])
                        if tk not in ltp_map or ltp_map[tk] == 0:
                            logger.warning(f"[WARN] LTP missing for {tk}. Trying get_ltp fallback...")
                            # Try fetching individual
                            # But we need symbol? We only have token here.
                            pass

                except Exception as e:
                    logger.error(f"[ERROR] Failed to fetch LTPs: {e}")

            # 3. Calculate Total PnL
            for pos in data:
                # PnL = (Total Sell Amt - Total Buy Amt) + (NetQty * LTP)
                buy_amt = float(pos.get('buyAmt', 0)) + float(pos.get('cfBuyAmt', 0))
                sell_amt = float(pos.get('sellAmt', 0)) + float(pos.get('cfSellAmt', 0))
                
                net_qty = pos['netQty']
                current_val = 0.0
                
            # 3. Calculate Total PnL
            pnl_valid = True
            
            for pos in data:
                # PnL = (Total Sell Amt - Total Buy Amt) + (NetQty * LTP)
                buy_amt = float(pos.get('buyAmt', 0)) + float(pos.get('cfBuyAmt', 0))
                sell_amt = float(pos.get('sellAmt', 0)) + float(pos.get('cfSellAmt', 0))
                
                net_qty = pos['netQty']
                current_val = 0.0
                
                if net_qty != 0:
                    tok = str(pos.get('tok'))
                    ltp = ltp_map.get(tok, 0.0)
                    if ltp == 0:
                        logger.warning(f"[WARN] LTP 0 for {pos.get('trdSym')} (Token: {tok}). Marking PnL as INVALID.")
                        pnl_valid = False
                    current_val = net_qty * ltp
                
                pnl = (sell_amt - buy_amt) + current_val
                
                # Debug Log for each position
                # logger.info(f"Pos: {pos.get('trdSym')} | Net: {net_qty} | PnL: {pnl:.2f}")
                
                total_pnl += pnl
                
            return total_pnl, open_positions, pnl_valid
            
        except Exception as e:
            logger.error(f"[ERROR] Error calculating P&L: {e}")
            return 0.0, [], False

    def activate_kill_switch(self, reason):
        """Create lock file to stop other strategies."""
        if not CONFIG['ENABLE_KILL_SWITCH']:
            return
            
        lock_file = CONFIG['LOCK_FILE_PATH']
        try:
            with open(lock_file, 'w') as f:
                f.write(f"STOP_TRADING triggered at {datetime.now()}\nReason: {reason}")
            logger.info(f"[LOCK] KILL SWITCH ACTIVATED: {lock_file} created.")
        except Exception as e:
            logger.error(f"[ERROR] Failed to create lock file: {e}")

    def square_off_all(self, open_positions):
        """Close all open positions."""
        logger.info(f"[ALERT] SQUARING OFF {len(open_positions)} POSITIONS...")
        
        for pos in open_positions:
            try:
                symbol = pos.get('trdSym', '')
                net_qty = int(pos.get('netQty', 0))
                token = pos.get('tkn')
                
                if net_qty > 0:
                    tx_type = "S"
                    qty = abs(net_qty)
                elif net_qty < 0:
                    tx_type = "B"
                    qty = abs(net_qty)
                else:
                    continue
                    
                logger.info(f"Closing {symbol}: {tx_type} {qty} Qty")
                
                # Market Order for Exit
                self.order_manager.place_order(
                    symbol=symbol,
                    qty=qty,
                    transaction_type=tx_type,
                    tag="PORTFOLIO_EXIT",
                    product="MIS" 
                )
                
            except Exception as e:
                logger.error(f"[ERROR] Failed to close {pos.get('trdSym')}: {e}")

    def run(self):
        if not self.initialize():
            return
            
        self.running = True
        logger.info("[START] Portfolio Monitor Started")
        logger.info(f"Target: {CONFIG['TARGET_PROFIT']} | Max Loss: {CONFIG['MAX_LOSS']}")
        
        try:
            while self.running:
                pnl, open_positions, is_valid = self.get_global_pnl()
                
                log_msg = f"Global P&L: {pnl:.2f} | Open Pos: {len(open_positions)}"
                
                # Add Lock Indication
                active_lock = self.get_active_lock()
                if active_lock > 0:
                    log_msg += f" | Locked: {active_lock:.2f}"
                
                if not is_valid:
                    log_msg += " [INVALID DATA]"
                
                logger.info(log_msg)
                
                if not is_valid:
                    # Skip logic if data invalid
                    time.sleep(CONFIG['POLL_INTERVAL'])
                    continue

                # Check Thresholds
                triggered = False
                reason = ""
                
                if pnl >= CONFIG['TARGET_PROFIT']:
                    reason = f"Target Profit Hit ({pnl:.2f} >= {CONFIG['TARGET_PROFIT']})"
                    triggered = True
                    logger.info(f"[TRIGGER] {reason}")
                    
                elif pnl <= CONFIG['MAX_LOSS']:
                    reason = f"Max Loss Hit ({pnl:.2f} <= {CONFIG['MAX_LOSS']})"
                    triggered = True
                    logger.warning(f"[TRIGGER] {reason}")
                    
                # Profit Locking Logic
                if not triggered and 'PROFIT_LOCKING' in CONFIG:
                    # 1. Update High Water Mark
                    if pnl > self.highest_profit:
                        self.highest_profit = pnl
                        # logger.info(f"[INFO] New High Profit: {self.highest_profit:.2f}")

                    # 2. Check Locks
                    active_lock = self.get_active_lock()
                    
                    if active_lock > 0:
                        if pnl < active_lock:
                            reason = f"Profit Locking Hit (High: {self.highest_profit:.2f}, Current: {pnl:.2f} < Lock: {active_lock:.2f})"
                            triggered = True
                            logger.warning(f"[TRIGGER] {reason}")
                
                if triggered:
                    # 1. Activate Global Kill Switch
                    self.activate_kill_switch(reason)
                    
                    # 2. Log wait status
                    if open_positions:
                        logger.info(f"[INFO] Kill switch activated. Waiting for {len(open_positions)} active strategies to exit themselves.")
                    else:
                        logger.info("[INFO] No open positions to close.")
                        
                    # 3. Stop Monitoring
                    logger.info("[EXIT] Portfolio Manager Exiting after Limit Hit.")
                    self.running = False
                    break
                
                time.sleep(CONFIG['POLL_INTERVAL'])
                
        except KeyboardInterrupt:
            logger.info("🛑 Stopped by User")
        except Exception as e:
            logger.error(f"❌ Runtime Error: {e}")

if __name__ == "__main__":
    pm = PortfolioManager()
    pm.run()
