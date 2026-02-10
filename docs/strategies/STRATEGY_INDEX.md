# Strategy Documentation Index

This folder contains detailed documentation for all trading strategies in the Upstox Algorithmic Trading System.

## 📈 Directional Strategies (Trend Following)

| Strategy Name | Description | Status | Values |
| :--- | :--- | :--- | :--- |
| **[Futures VWAP EMA](futures_vwap_ema.md)** | Options selling based on Futures Price vs VWAP & EMA crossovers. | ✅ Active | Trend, VWAP, EMA, PCR |
| **[Dual Renko Dip](dual_renko_dip.md)** | Momentum strategy using multi-layer Renko bricks for macro trend and entry timing. | ✅ Active | Renko, Momentum, RSI |
| **Futures Breakout** | Breakout strategy (Details pending). | ⚠️ Beta | Breakout, Volume |
| **ORB Retest** | Opening Range Breakout with retest confirmation. | ⚠️ Beta | ORB, Price Action |

---

## 📉 Non-Directional Strategies (Premium Selling)

| Strategy Name | Description | Status | Values |
| :--- | :--- | :--- | :--- |
| **[Dynamic Strangle](dynamic_strangle.md)** | Adaptive short strangle that shifts legs based on delta/premium to stay neutral. | ✅ Active | Delta Neutral, Adaptive Pivot |
| **[VWAP Straddle V2](vwap_straddle_v2.md)** | Intraday straddle using VWAP of combined premiums to define skew/entry validity. | ✅ Active | VWAP, Combined Premium, Skew |
| **Delta Neutral** | Classic delta neutral strategy (details pending). | ⚠️ Legacy | Delta, Theta |
| **ATM Straddle Ratio** | Ratio spreads anchored on ATM. | ⚠️ Beta | Ratio, Decay |

---

## 🛠️ Strategy Selection Guide

### When to use what?

1.  **Market Trending Strong?** -> Use **Futures VWAP EMA** or **Dual Renko Dip**.
2.  **Market Sideways / Volatile?** -> Use **Dynamic Strangle** (Adaptive) or **VWAP Straddle V2**.
3.  **Opening Volatility (9:15-10:00)?** -> **ORB Retest** (if active).

### How to Run?

Use the `run_strategy.py` launcher (if available) or execute the strategy's `live.py` file directly:
```bash
# Example
python strategies/directional/futures_vwap_ema/live.py
```
