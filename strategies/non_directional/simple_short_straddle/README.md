# Simple Short Straddle Strategy

## 📈 Strategy Overview
This is an optimized execution wrapper for the Short Straddle strategy. It provides a clean, automated interface for atmospheric (non-directional) option selling with built-in market validation and real-time monitoring.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Starts at **09:20 AM**.
- **Market Validation**: Automatically checks exchange connectivity, funds, and instrument availability before execution.
- **Strike Selection**: Automatically identifies the Nifty ATM strike for the current weekly expiry.

### 2. ⚖️ Position Management
This strategy utilizes the robust management logic from the **Legacy Straddle** core:
- **Stop Loss**: Fixed loss limit (Default **₹3,000**).
- **Profit Target**: Fixed profit goal (Default **₹3,000**).
- **Trailing SL**: Tiered trailing system that locks profit at specific P&L milestones (30%, 50%, 80%, 100%).

### 3. 🔴 Exit Conditions
- **Profit/Loss Hit**: Automatically exits all legs when the total MTM hits defined targets.
- **Time Exit**: Strictly squares off all intraday positions at **15:18**.

### 4. 📡 Real-time Monitoring
- Includes a background WebSocket feed to monitor Nifty Index and premium prices, ensuring the strategy responds instantly to market moves.

---

## 🚀 Overall Strategy Example
1. **09:15 AM**: Strategy starts and validates connection to Upstox.
2. **09:20 AM**: ATM Strike (e.g., 24,000) is identified.
3. **Entry**: Short 1 lot of Nifty 24,000 CE and PE.
4. **Monitoring**: Strategy displays real-time P&L on the console.
5. **12:00 PM**: P&L reaches ₹1,500. TSL locks ₹500 profit.
6. **14:30 PM**: P&L drops back to ₹500. TSL hit.
7. **Exit**: Strategy closes both legs and prints the final performance summary.
