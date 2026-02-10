from datetime import datetime

class MonthlyStrangleCore:
    def __init__(self, config):
        self.config = config
        
    def get_target_strikes(self, spot_price):
        """Calculate Deep OTM strikes."""
        offset = self.config['strike_offset']
        atm = round(spot_price / 50) * 50
        
        ce_strike = atm + offset
        pe_strike = atm - offset
        
        return ce_strike, pe_strike

    def check_exit_condition(self, entry_price, current_price, option_type):
        """
        Check SL and Target.
        Short Position Logic:
        - Loss = Current > Entry
        - Profit = Current < Entry
        """
        if entry_price <= 0: return None
        
        pnl_pct = (entry_price - current_price) / entry_price
        
        # Stop Loss (Negative PnL)
        # Verify: If Entry 100, SL 30%. Loss triggers at 130.
        # (100 - 130) / 100 = -0.30
        if pnl_pct <= -self.config['stop_loss_pct']:
            return "STOP_LOSS"
            
        # Target Profit (Positive PnL)
        # Entry 100, Target 50%. triggers at 50.
        # (100 - 50) / 100 = 0.50
        if pnl_pct >= self.config['target_profit_pct']:
            return "TARGET_PROFIT"
            
        return None
