# Futures VWAP Supertrend Options Selling Strategy

## 📈 Strategy Overview
A high-probability directional strategy that combines **VWAP** for intraday value and **Supertrend** for trend direction. It focuses on selling OTM options with high Open Interest (OI) buildup to benefit from both directional momentum and theta decay.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Trend Filter (Supertrend)**: Supertrend (10, 2) on 3-minute Nifty Futures chart.
- **Value Filter (VWAP)**: 
    - **Bearish (Sell CE)**: Price < Supertrend (Red) AND Price < VWAP.
    - **Bullish (Sell PE)**: Price > Supertrend (Green) AND Price > VWAP.
- **Distance Filter**: Price must be within 0.2% of VWAP to avoid chasing late moves.
- **Strike Selection (OI Scan)**:
    - Scans OTM strikes for **Price Decrease >= 20%** and **OI Increase >= 25%** (Short Buildup).
    - Ensures at least 100 points OTM from ATM.

### 2. 🪜 Pyramiding logic
- **Trigger**: Unrealized profit on existing position reaches **10%**.
- **Action**: Add 1 more lot of the same strike.
- **Max Levels**: 2 pyramid levels (Total 3 lots).

### 3. 🔴 Exit Conditions
- **TSL (Tick-by-Tick)**:
    - **Initial**: 10% TSL from lowest price.
    - **After Pyramid 1**: TSL tightens to 5%.
- **Trend Reversal (Candle Close)**:
    - Exit Sell CE if Price > VWAP or Supertrend turns Green.
    - Exit Sell PE if Price < VWAP or Supertrend turns Red.
- **Time Square-off**: 15:15 PM.

### 4. ⚖️ Risk Management
- **LTP Monitoring**: Supertrend and VWAP are monitored on Futures (Reference), while TSL is monitored on the Option LTP.
- **Sentiment Filter**: (Optional) Daily PCR check to confirm trend.

---

## 🚀 Overall Strategy Example
1. **Signal**: 09:45 AM - Nifty Futures is at 24,050. VWAP is 24,030. Supertrend is Green.
2. **Setup**: Price is within 0.2% of VWAP. 23,900 PE shows 30% OI increase and 25% price drop.
3. **Action**: Market is Bullish. Sell 23,900 PE @ ₹50.
4. **Initial TSL**: ₹55 (10% trail).
5. **Profit**: PE drops to ₹40 (20% profit > 10% trigger).
6. **Pyramiding**: Sells 1 more lot of 23,900 PE.
7. **Tightening**: New TSL at 5% from lowest price (e.g., if low is ₹40, TSL is ₹42).
8. **Exit**: Trend reversal or hit TSL or 15:15 PM.
