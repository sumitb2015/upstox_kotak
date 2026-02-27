# Inside Candle Breakout Strategy

## 📈 Strategy Overview
The Inside Candle strategy is a classic price action system that captures high-momentum breakouts after a period of consolidation. It identifies a "Mother-Baby" relationship between candles and trades the breakout of the Mother candle's range using option selling.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Timeframe**: 5-minute candles.
- **Pattern (Inside Bar)**:
    - **Mother Candle**: The reference high and low.
    - **Baby Candle(s)**: Any subsequent candle where High < Mother High AND Low > Mother Low.
- **Execution (Breakout)**: Watch Nifty Spot Price.
    - **Bullish Breakout**: Price > Mother High. -> **SELL PE (ATM-100)**.
    - **Bearish Breakout**: Price < Mother Low. -> **SELL CE (ATM+100)**.

### 2. 🪜 Trailing Stop Loss (Tiered)
To maximize gains during trending breakouts, the strategy uses a tiered TSL:
- **Initial**: 20% Trail on Option Premium.
- **Phase 1 (Breakeven)**: If Profit > 10%, move TSL to Entry Price.
- **Phase 2 (Locking)**: If Profit > 20%, tighten TSL to 10% Trail.
- **Phase 3 (Aggressive)**: If Profit > 40%, tighten TSL to 5% Trail.

### 3. 🔴 Exit Conditions
- **Spot SL**: 
    - **Sell PE**: Exit if Spot Price < Mother Low.
    - **Sell CE**: Exit if Spot Price > Mother High.
- **Option TSL**: Exit if Option LTP hits the tiered trail levels.
- **Time Square-off**: 15:15 PM.

### 4. ⚖️ Risk Management
- **Persistence**: A Mother Candle can spawn multiple babies. The breakout level remains static until hit.
- **Strike Selection**: Deep OTM strikes (ATM ± 100) are chosen to ensure high probability and managed gamma risk.

---

## 🚀 Overall Strategy Example
1. **Setup (09:15 - 09:25)**:
   - Mother Candle (09:15): High 24,150 | Low 24,050.
   - Baby Candle 1 (09:20): High 24,140 | Low 24,060 (STAYED INSIDE).
2. **Breakout (09:32)**:
   - Spot price reaches 24,151 (Crossed Mother High).
3. **Action**: Bullish signal. Sell 24,050 PE (ATM is ~24,150).
4. **Spot SL**: 24,050.
5. **Move**: Nifty goes to 24,200. Profit on PE reaches 25%.
6. **Trailing**: TSL moves to "Lock 10%" based on Tiered logic.
7. **Exit**: 15:15 PM hits. Trade closed.
