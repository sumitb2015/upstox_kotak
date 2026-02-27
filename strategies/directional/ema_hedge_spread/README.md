# EMA Hedge Spread Strategy

## 📈 Strategy Overview
The EMA Hedge Spread is a directional credit strategy that uses EMA crossovers and momentum to enter **Bull Put Spreads** or **Bear Call Spreads**. By using spreads, the strategy limits maximum risk while maintaining a bullish or bearish bias.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **EMA Alignment**: Uses EMA(9) and EMA(20) crossover on 3-minute candles.
- **Directional Triggers**:
    - **Bullish**: EMA(9) > EMA(20) + Price > EMA(9). -> **Enter Bull Put Spread**.
    - **Bearish**: EMA(9) < EMA(20) + Price < EMA(9). -> **Enter Bear Call Spread**.
- **Strike Selection**:
    - **Short Leg**: ATM or 1 strike OTM.
    - **Hedge Leg**: 3 strikes further OTM (protects against tail risk).

### 2. 🪜 Pyramiding logic
- **Locking**: Once the first spread reaches 30% of its max profit (credit), the strategy locks the profit via TSL.
- **Scaling**: Adds another spread of the same strikes if the momentum remains strong (RSI > 60 for Bullish, RSI < 40 for Bearish).

### 3. 🔴 Exit Conditions
- **Momentum Reversal**: Exit if EMA(9) crosses back through EMA(20).
- **Hard SL**: Total spread value increases by 50% (Net Credit Loss).
- **TSL**: 20% trailing from peak profit.
- **Time Square-off**: 15:18 PM.

### 4. ⚖️ Risk Management
- **Atomic Execution**: Place both Short and Hedge legs simultaneously to avoid execution risk and ensure margin benefit.
- **Spread Width**: Fixed at 150 points for Nifty (approx 3 strikes).

---

## 🚀 Overall Strategy Example
1. **Signal**: 10:30 AM - Nifty EMA(9) crosses above EMA(20). RSI is 58.
2. **Action**: Market is Bullish.
3. **Execution**: Sells 24,000 PE and Buys 23,850 PE (150-pt Bull Put Spread).
4. **Credit**: Collects ₹45 net premium.
5. **Trend**: Nifty goes to 24,150. Spread premium drops to ₹15.
6. **Pyramiding**: 30% profit reached. TSL locked. Adds 1 more lot of the same spread.
7. **Exit**: 15:18 PM hits. Both spreads closed for profit.
