# Option Scalper (Depth & Momentum)

## 📈 Strategy Overview
The Option Scalper is a high-frequency directional strategy that searches for very short-term momentum opportunities in OTM options. It combines **Market Depth (L2 Order Book)** analysis with **Price Momentum** to identify "Buy/Sell Walls" and swift premium changes.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Market Depth Imbalance**: Monitors the ratio of Buy Quantity vs. Sell Quantity in the top 5 levels of the limit order book.
    - **Wall Detection**: Identifies large orders (walls) that price is likely to bounce from or break through.
- **Price Momentum**: Uses a fast 10-tick rate-of-change (ROC) to confirm immediate momentum.
- **Filter**: 
    - **Bullish (Sell PE)**: Depth Imbalance favors Bids + Rising ROC.
    - **Bearish (Sell CE)**: Depth Imbalance favors Asks + Falling ROC.

### 2. 🪜 Scalping Logic
- **Quick In-Out**: Designed for holding times of 2-10 minutes.
- **Multiple Targets**: Small incremental profit targets to secure fast gains.

### 3. 🔴 Exit Conditions
- **Fixed SL**: 15% of premium or 5 points (whichever is closer).
- **Target**: 10% of premium.
- **Momentum Stall**: Exit if Price ROC flattens for more than 30 seconds.
- **Opposing Wall**: Exit if a massive opposing wall appears in the order book.

### 4. ⚖️ Risk Management
- **WebSocket Only**: Relies on real-time Upstox WebSocket data (`full` mode) for order book visibility.
- **Execution Speed**: Uses direct market orders for near-instant execution.

---

## 🚀 Overall Strategy Example
1. **Setup**: Monitoring 24,100 CE. 
2. **Scan**: Bid side total is 50,000 units. Ask side total is 200,000 units. 
3. **Signal**: Clear "Sell Wall" at ₹85. Price ROC is falling.
4. **Action**: Bearish momentum confirmed. Sell 24,100 CE @ ₹82.
5. **Trade**: Price drops to ₹74 in 90 seconds.
6. **Exit**: Target of 10% reached. Strategy covers the short.
