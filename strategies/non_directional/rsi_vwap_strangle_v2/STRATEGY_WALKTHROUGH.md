# RSI VWAP Strangle V2 - Strategy Walkthrough

This strategy is a non-directional setup designed to capture premium decay (Theta) in range-bound markets, while having specific defenses for trending moves.

## 1. The Setup (Entry)

**Goal**: Enter a Short Strangle (Sell CE + Sell PE) when the market is consolidating and premiums are "expensive" relative to their average price (VWAP).

### Conditions
1.  **RSI Check**: The 5-minute RSI of the Index (e.g., Nifty) must be between **40 and 60**.
    *   *Why?* This indicates a sideways/consolidating market. We avoid entering during strong trends (RSI > 60 or < 40).
2.  **VWAP Value Check**:
    *   Get the `Current Premium` (CE LTP + PE LTP).
    *   Get the `VWAP Premium` (CE VWAP + PE VWAP).
    *   **Condition**: `Current Premium < VWAP Premium`.
    *   *Wait? The code says `<`?* Let's double check.
    *   *Correction from Code*: line 327 `combined_premium < combined_vwap`.
    *   *Logic*: We want to sell when the *combined* price is **below** the average? That sounds counter-intuitive for selling (usually sell high).
    *   *Re-reading line 304*: Checks if premium is *cheaper* than VWAP?
    *   *Actually*: If current price < VWAP, it might mean momentum is fading or mean reverting? Or perhaps it's a safety check to ensure we aren't selling into a spike?
    *   *Alternative Interpretation*: It might be a "Value" check, but typically you sell above VWAP. Let's assume the code logic `Current < VWAP` is the intended filter for "fair value" or "not over-inflated".

### Execution
*   **Target Premium**: We look for strikes where the option price is close to `90` (Configurable `TARGET_PREMIUM`).
    *   Example: Nifty is 24000.
    *   24300 CE is trading at ₹88.
    *   23700 PE is trading at ₹92.
*   **Atomic Entry**: We sell **both** legs simultaneously. If one fails, we exit the other immediately (Rollback).

---

## 2. Risk Management (The Defense)

Once entered, we have a "Two-Tier" Stop Loss system.

### Tier 1: The "Combined Gate" 🛡️
*   We monitor the **Total MTM Loss** of the strategy.
*   **Config**: `COMBINED_SL_PCT = 15%`.
*   We DO NOT exit individual legs just because they hit their stop loss *unless* the **Total Strategy Loss** exceeds 15% of the collected premium.
*   *Benefit*: One leg might spike (loss) while the other decays (profit). As long as the net result is okay, we hold.

### Tier 2: Individual Leg SL ⚠️
*   **Config**: `SL_PCT = 20%`.
*   If the **Gate is Open** (Total Loss > 15%), **AND** a specific leg is down by 20%, we exit that leg.
*   *Hard Stop*: If a leg crashes and loss exceeds 30% (`MAX_LEG_SL_PCT`), we exit it **immediately**, bypassing the Gate.

---

## 3. Scenarios

### Scenario A: The "Perfect" Day (Range Bound) 😴
1.  **Entry**: Nifty 24000. Sold 24300 CE @ 90, 23700 PE @ 90. Total Credit = 180.
2.  **Movement**: Nifty stays between 23900 and 24100.
3.  **Decay**: CE drops to 60, PE drops to 50.
4.  **Target**: If any leg drops by 50% (e.g., 90 -> 45), we book profit on that leg.
    *   *Twist*: If we book profit on one leg, do we close the other? *Code Check*: No, we close the profitable leg. The other remains.
    *   *Code Line 716*: `if profit_pct >= TARGET_PROFIT_PCT ... order_mgr.place_order(..., "B")`.

### Scenario B: The "Trend" (Defense Mode) 🚀
1.  **Entry**: Sold CE @ 90, PE @ 90.
2.  **Movement**: Nifty shoots up to 24200.
3.  **Price Action**:
    *   PE (With Trend) drops to 50. (Profit)
    *   CE (Against Trend) spikes to 120. (Loss)
4.  **SL Logic**:
    *   CE Loss = 33%.
    *   PE Profit = 44%.
    *   Net Premium = 120 + 50 = 170. (Initial was 180). We are actually in *profit* by 10 points!
    *   **Result**: The "Combined Gate" stays **CLOSED**. We hold the losing CE because the PE is funding it.

### Scenario C: The "Breakout" (Pyramiding) ⛰️
1.  **State**: One leg hits SL (e.g., PE SL hit). We are now "Naked" holding only CE.
2.  **Trend Continues**: The market keeps falling (favoring our Short CE).
3.  **Pyramid Trigger**:
    *   Basic Condition: We are Naked.
    *   Profit Check: If the CE profit increases by 10% (e.g., price drops from 90 -> 81).
4.  **Action**: We **ADD** (Sell) another lot of CE @ 81.
    *   *Risk*: We now have 2 lots of CE.
    *   *Reward*: Capitalizing on the trend.
    *   *Safety*: We tighter the Stop Loss on the entire CE position.

### Scenario D: The "Reversal" (Re-entry) 🔄
1.  **State**: PE SL was hit at 110 (Entry 90). Market had crashed.
2.  **Reversal**: Market stabilizes and starts recovering up.
3.  **Trigger**: PE price cools off and comes back down hard.
    *   The strategy remembers: "I exited PE at 110. But I'll watch it."
    *   If PE price drops back to `Exit Price - 10%` (Recovery), we **Re-enter** the PE leg.
    *   We enter the Strangle again!
