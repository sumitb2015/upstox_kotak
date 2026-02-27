# Intraday Short Straddle (Legacy)

## 📈 Strategy Overview
This is a comprehensive intraday short straddle implementation that incorporates OI sentiment analysis, pivot level monitoring (CPR/Camarilla), and dynamic risk management.

---

## 🎯 Details

### 1. 🟢 Entry Conditions
- **Time Check**: Typically starts at **09:15 - 09:20 AM**.
- **Market Suitability**: Checks if straddle width is within threshold (**< 20% of spot price**).
- **Pivot Filter**: Monitors proximity to PDH (Prev Day High) and PDL (Prev Day Low).
- **OI Sentiment**: Optionally waits for neutral or favorable OI signals before entry.

### 2. ⚖️ Dynamic Management
- **Ratio Threshold**: Manages positions based on the premium ratio between CE and PE.
- **Position Scaling**: Can scale position size (up to 3x) if profit exceeds 30% and OI confidence is high.
- **Safe OTM Additions**: On expiry days, adds safe OTM leg selling to boost theta collection if RSI/OI conditions permit.

### 3. 🔴 Exit Conditions
- **Profit Target**: Fixed amount (Default **₹3,000**), adjustable based on risk multipliers.
- **Stop Loss**: Fixed amount (Default **₹3,000**).
- **Time Exit**: Automatic square-off at **15:18**.

### 4. 🔒 Tiered Trailing SL
The strategy uses a milestone-based trailing system:
- **30% Profit Target reached**: Lock **10%** profit.
- **50% Profit Target reached**: Lock **25%** profit.
- **80% Profit Target reached**: Lock **60%** profit.
- **100% Profit Target reached**: Lock **85%** profit.

---

## 🚀 Overall Strategy Example
1. **09:15 AM**: Strategy fetches CPR and Camarilla levels for Nifty.
2. **09:20 AM**: Nifty ATM is 24,000. Combined premium is ₹200. Conditions passed.
3. **Entry**: Short 1 lot of CE and PE at ATM strike.
4. **11:00 AM**: Nifty stays range-bound. Both legs decay. Total profit reaches ₹1,000 (33% of ₹3k target).
5. **TSL Update**: Strategy locks ₹300 profit as a dynamic floor.
6. **13:00 PM**: OI Analysis detects bullish build-up. Strategy adds a safe OTM Put to capture more premium.
7. **14:45 PM**: Total Profit reaches ₹3,000. Target hit.
8. **Exit**: Strategy squares off all positions and logs the day's P&L.
