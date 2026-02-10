# Dual-Renko Dip Strategy Documentation

The Dual-Renko Dip strategy is a trend-following momentum system designed for option selling. It uses two Renko layers for the underlying (main trend + timing) and one Renko layer for the option premium (trailing exit).

## 1. Key Indicators

| Indicator | Parameter | Purpose |
| :--- | :--- | :--- |
| **Mega Renko** | 60 pts | **Macro Trend**: Determines if we are in a Bullish or Bearish regime. |
| **Signal Renko** | 5 pts | **Entry Timing**: Identifies pullbacks ("dips") and resumptions. |
| **RSI** | 14 periods | **Momentum Filter**: Ensures we don't enter into over-extended zones. |
| **Option Renko** | ~7.5% (Dynamic) | **Trailing Exit**: Tracks option premium to lock in decay or exit on reversals. |

---

## 2. Entry Logic (The "Dip")

The strategy only enters when the **Macro Trend** and **Short-term Momentum** align.

### Bullish Entry (Sell PE)
1.  **Mega Trend**: Must be Green (Bullish, 60-pt bricks).
2.  **RSI**: Must be between `50` and `80`.
3.  **Signal Renko**: Must show a streak of **3 Green Bricks** from a "Waiting" state.
4.  **Pyramiding**: If in a Bullish trend, if Signal Renko turns Red (Pullback) and then forms **2 Green Bricks** (Resumption), add another lot.

### Bearish Entry (Sell CE)
1.  **Mega Trend**: Must be Red (Bearish, 60-pt bricks).
2.  **RSI**: Must be between `20` and `50`.
3.  **Signal Renko**: Must show a streak of **3 Red Bricks**.
4.  **Pyramiding**: If Signal Renko turns Green (Pullback) and then forms **2 Red Bricks** (Resumption), add another lot.

---

## 3. Exit Logic

The strategy uses multiple exit layers to protect capital and lock in profits.

### A. Structural Reversal (Mega Exit)
If the **Mega Renko (60 pts)** flips color against your position (e.g., Green to Red for a Bullish trade), the strategy triggers an **Immediate Emergency Exit**.

### B. Trailing Stop-Loss (Premium Reversal)
Since this is an option selling strategy, we want the premium to decrease (decay).
1.  The bot monitors the **Option Premium LTP**.
2.  It creates a dynamic Renko chart for the option starting at the entry price.
3.  **Trailing**: As the premium hits new lows, the Renko "ceiling" trails lower.
4.  **Trigger**: If the premium rises and forms **3 Green Bricks** (approx. 22.5% rise from the low), it triggers a trailing stop-loss exit.

### C. Hard Stop Loss (Hybrid Protection)
In the Hybrid model, the bot polls the LTP every second.
- **SL Trigger**: If the Nifty Price or Option Premium hits a predefined hard breach floor (set in config), the bot exits instantly via Market order.

---

## 4. Operational Flow (Hybrid Model)

1.  **Sync**: On startup, the bot fetches the last 100 1-minute candles to reconstruct the "Official" Renko state.
2.  **Trend Monitoring**: Every 60 seconds, it syncs with the official exchange candle (High/Low) to update the trend bricks.
3.  **Trade Protection**: Every 1 second, it checks the LTP for immediate SL/Target hits.

---

## 5. Configuration (Example)
```yaml
mega_brick_size: 60
nifty_brick_size: 5
trend_streak: 3
max_pyramid_lots: 3
option_brick_pct: 0.075
rsi_pivot: 50
```
