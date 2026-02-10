import pandas as pd
from strategy_core import InsideCandleAnalyzer

def test_multi_baby_logic():
    print("🧪 Testing Multi-Baby Candle Logic...")
    analyzer = InsideCandleAnalyzer()
    
    # 1. Setup Data: Mother + Inside 1 + Inside 2 + Breakout
    data = [
        {'time': '09:15', 'open': 100, 'high': 200, 'low': 100, 'close': 150}, # Candle 0
        {'time': '09:20', 'open': 120, 'high': 180, 'low': 120, 'close': 140}, # Candle 1: INSIDE (Baby 1)
        {'time': '09:25', 'open': 130, 'high': 170, 'low': 130, 'close': 140}, # Candle 2: INSIDE (Baby 2)
        {'time': '09:30', 'open': 140, 'high': 210, 'low': 140, 'close': 200}, # Candle 3: BREAKOUT UP
    ]
    
    df = pd.DataFrame(data)
    
    # Step 1: Feed first 2 candles (Mother + Baby 1)
    print("\n--- Feeding Candle 0 & 1 ---")
    current_df = df.iloc[:2]
    is_pattern = analyzer.detect_pattern(current_df)
    print(f"Pattern Detected? {is_pattern}")
    assert is_pattern == True
    assert analyzer.mother_candle['time'] == '09:15'
    
    # Step 2: Feed Candle 2 (Baby 2 - Still Inside Mother)
    print("\n--- Feeding Candle 2 ---")
    current_df = df.iloc[:3]
    is_pattern = analyzer.detect_pattern(current_df)
    print(f"Pattern Still Active? {is_pattern}")
    assert is_pattern == True
    assert len(analyzer.baby_candles) == 2
    
    # Step 3: Check Breakout (Price = 190, Inside Mother)
    print("\n--- Check Price 190 (Inside MotherH 200) ---")
    sig = analyzer.check_breakout(190)
    print(f"Signal: {sig}")
    assert sig is None
    
    # Step 4: Check Breakout (Price = 205, Above MotherH 200)
    print("\n--- Check Price 205 (Breakout MotherH) ---")
    sig = analyzer.check_breakout(205)
    print(f"Signal: {sig}")
    assert sig is not None
    assert sig['type'] == 'BULLISH'
    assert sig['trigger_price'] == 205
    
    print("\n✅ Multi-Baby Logic Verified Successfully!")

if __name__ == "__main__":
    test_multi_baby_logic()
