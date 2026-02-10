# Dynamic Straddle Skew - Strategy Rules

## 1. Strategy Overview
- **Goal**: Capitalize on directional bias and premium decay by scaling into winning ATM options.
- **Instrument**: NIFTY Index Options.
- **Execution**: Short Straddle based.

## 2. Core Logic

### Phase 1: Neutral Entry (09:20)
- Sell **1 Lot ATM CE** and **1 Lot ATM PE**.
- This creates a neutral delta position to start the day.

### Phase 2: Skew Detection (Bias Identification)
- The strategy monitors the premium difference between CE and PE.
- **Skew Trigger**: If `LTP_Winner < LTP_Loser * (1 - 0.15)`.
- A 15% difference indicates the market is moving decisively in one direction.
- **Action**: Identify the side with lower premium as the **Winning Side**.

### Phase 3: Dynamic Pyramiding (Winning Side Expansion)
- Once a winning side is identified, the strategy adds **1 lot** to that side.
- **Continuous Scaling**: Adding another lot for every **7% further decay** in the winning leg's premium.
- **Limit**: Max **4 lots** on the winning side (Initial + 3 pyramid lots).

### Phase 4: Defensive Reduction (Trend Reversal)
- To protect gains, the strategy tracks the `Lowest Price` of the winning leg.
- **Reduction Trigger**: If the winning premium rises **10% from its low**.
- **Action**: Buy back (close) **1 lot** of the winning side.
- This allows the strategy to "breathe" and reduce exposure if the trend stalls or reverses.

## 3. Exit Rules
- **Time-based**: Square off all positions at **15:15**.
- **Risk management**: Emergency hard SL at 60% of entry premium for individual legs.

## 4. Key Parameters
| Parameter | Value | Description |
| :--- | :--- | :--- |
| Entry Time | 09:20 | Start of the strategy |
| Skew Threshold | 15% | Difference between CE/PE to trigger bias |
| Pyramid Decay | 7% | Further decay needed to add more lots |
| Reduction Buffer | 10% | Recovery from low to reduce position |
| Max Lots | 4 | Max lots on the winning side |
