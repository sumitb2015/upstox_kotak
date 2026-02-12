
# Simulating TSL Trailing Logic

class MockBrick:
    def __init__(self, close, color, index):
        self.close = close
        self.color = color
        self.index = index

class MockRenko:
    def __init__(self, brick_size):
        self.brick_size = brick_size
        self.bricks = []
    
    def update(self, price, ts):
        # Primitive mock logic
        if not self.bricks:
            self.bricks.append(MockBrick(price, 'RED', 0))
            return 1
        
        last = self.bricks[-1]
        diff = last.close - price # Short: Price drop is profit/trend
        
        if diff >= self.brick_size: # New Low (RED)
            self.bricks.append(MockBrick(price, 'RED', last.index + 1))
            return 1
        elif price - last.close >= self.brick_size: # Reversal (GREEN)
             self.bricks.append(MockBrick(price, 'GREEN', last.index + 1))
             return 1
        return 0

class MockStrategy:
    def __init__(self, tsl_type='staircase'):
        self.config = {'tsl_type': tsl_type, 'tsl_brick_count': 3, 'wait_for_candle_close': True}
        self.best_option_low = 100.0
        self.option_renko = MockRenko(brick_size=5.0)
        self.option_renko.bricks.append(MockBrick(100.0, 'RED', 0))
        self.logs = []

    def get_tsl_multiplier(self):
        return 3.0 # Fixed for simplicity

    def on_tick(self, price):
        # 1. Update Renko
        new_bricks = self.option_renko.update(price, None)
        
        # 2. Logic from live.py (SIMULATED)
        if new_bricks > 0:
            if self.config.get('tsl_type') == 'staircase':
                last_brick = self.option_renko.bricks[-1]
                # ORIGINAL LOGIC: Only updates on RED (Continuation)
                if last_brick.color == 'RED':
                    self.best_option_low = last_brick.close
                    self.logs.append(f"Brick {last_brick.index} RED @ {last_brick.close}. New Low: {self.best_option_low}")
                else:
                    self.logs.append(f"Brick {last_brick.index} GREEN @ {last_brick.close}. Low unchanged: {self.best_option_low}")

        tsl = self.best_option_low + (5.0 * 3.0)
        return tsl

s = MockStrategy('staircase')
print(f"Start: 100. TSL: {100 + 15} = 115")

# Price drops to 95 (1 Brick Profit)
tsl = s.on_tick(95.0)
print(f"Price 95. TSL: {tsl}") 

# Price drops to 90 (2 Bricks Profit)
tsl = s.on_tick(90.0)
print(f"Price 90. TSL: {tsl}")
