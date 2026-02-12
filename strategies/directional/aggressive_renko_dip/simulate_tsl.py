
# Simulating the old TSL Logic
class MockStrategy:
    def __init__(self, avg_price, brick_size, dynamic_tightening=True, tighten_after=2, tighten_mult=1.5):
        self.avg_price = avg_price
        self.option_renko = type('obj', (object,), {'brick_size': brick_size})
        self.config = {
            'dynamic_tightening': dynamic_tightening,
            'tighten_after_bricks': tighten_after,
            'tightened_multiplier': tighten_mult,
            'tsl_brick_count': 3 # User setting, was ignored in old code
        }
        self.pyramid_count = 0
        self.ltp_cache = {}
        self.current_option_token = "OPT"

    def get_tsl_multiplier(self, current_price):
        # 1. Base Multiplier (OLD CODE: HARDCODED 2.0)
        base_mult = 2.0 - (self.pyramid_count * 0.2)
        final_mult = max(1.0, base_mult)
        
        # 2. Dynamic Tightening
        if self.config.get('dynamic_tightening', False):
            # simulate ltp_cache
            curr = current_price
            if curr > 0:
                # Short Option: Profit = Avg - Current
                points_gained = self.avg_price - curr
                bricks_gained = points_gained / self.option_renko.brick_size
                
                tighten_after = self.config.get('tighten_after_bricks', 4)
                print(f"DEBUG: PtsGained={points_gained:.1f}, BricksGained={bricks_gained:.2f}, Threshold={tighten_after}")
                
                if bricks_gained >= tighten_after:
                    tightened_mult = self.config.get('tightened_multiplier', 1.5)
                    if tightened_mult < final_mult:
                        # print(f"DEBUG: Tightening triggered! {final_mult} -> {tightened_mult}")
                        final_mult = tightened_mult
        return final_mult

# Scenario: Entry 100, Brick 5 (5%).
# Tighten after 2 bricks = 10 pts profit.
# Price drops to 89 (11 pts profit).

s = MockStrategy(avg_price=100, brick_size=5.0)
curr_price = 89.0
mult = s.get_tsl_multiplier(curr_price)
print(f"Price: {curr_price}, Profit: {100-curr_price}, Multiplier: {mult}")

# Scenario 2: Price drops to 91 (9 pts profit - < 2 bricks)
curr_price = 91.0
mult = s.get_tsl_multiplier(curr_price)
print(f"Price: {curr_price}, Profit: {100-curr_price}, Multiplier: {mult}")
