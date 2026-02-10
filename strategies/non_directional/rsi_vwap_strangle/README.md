# RSI VWAP Strangle Strategy

## Strategy Logic

A non-directional strategy that sells a strangle based on premium targeting, RSI consolidation, and value pricing.

### 1. Strike Selection
- **Target Premium**: 50.
- Find CE and PE strikes closest to this premium.

### 2. Entry Conditions
- **Timeframe**: 5-minute candles for RSI, Intraday for VWAP.
- **RSI Check**: 14-period RSI on 5-min chart must be between 40 and 60.
- **Value Check**: Combined Premium (CE+PE) < Combined VWAP (CE+PE).
    - `(LTP_CE + LTP_PE) < (VWAP_CE + VWAP_PE)`

### 3. Position Management
- **Stop Loss**: 20% initial Stop Loss per leg.
    - **SL Hardening**: Automatically locks SL to entry price once a leg reaches 15% profit.
    - **Trailing SL (TSL)**: Continuously trails price with a 20% buffer (shrinks to 10% during pyramiding).
- **Re-entry Logic**:
    - If a leg hits SL (Naked state), the strategy monitors for a reversal.
    - **Trigger**: Re-enter if price returns to the **Mid-point** of the Entry and SL Exit price. 
    - This ensures faster hedging compared to waiting for the original entry price.
- **Pyramiding (Trending Market)**:
    - Active only when ONE leg is open (Naked position).
    - **Trigger**: Every 10% increase in profit relative to the previous addition.
    - **Action**: Add 1 lot (Max 3 pyramiding entries).
    - **Step-Locking**: Upon each addition, the SL is "laddered" (locked) to the previous profitable step.
    - **Dynamic TSL**: TSL buffer tightens from 20% to **10%** once pyramiding is active.
    - **Pyramid Reduction**: If a Stop Loss hits while pyramided, the strategy exits **only the extra lots** and reverts to the original 1-lot position. This allows the trade to persist with a standard 20% SL buffer.

### Aggressive Pyramid Protection Example
The following table illustrates how the Stop Loss tightens as risk increases (CE leg sold at 100):

| Stage | Qty (Lots) | LTP | SL Calculation | **Active SL Price** | Protective Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Naked Start** | 1 | **100** | Initial TSL (20%) | **120.0** | Normal Entry |
| **2. Pyramid 1** | 2 | **90** | **Step-Lock**: Locked at 100 | **100.0** | **SL at Break-even!** |
| **3. Drop Continues**| 2 | **85** | **Switch to 10% TSL**: 85 + 10% | **93.5** | Locking Profit |
| **4. Pyramid 2** | 3 | **81** | **Step-Lock**: Locked at 90 | **89.1** | **TSL (81+10%) is tighter** |
| **5. Deep Trend** | 3 | **70** | **Tight TSL (10%)** | **77.0** | Safe 10-point cushion |

- **Target Exit**:
    - 50% of the collected premium of the active leg.
- **Fresh Entry Search**:
    - If both legs are exited (Double SL or Target), the strategy resets and begins searching for a fresh RSI/VWAP signal for a new strangle.
- **Dynamic Re-entry Recovery**:
    - To prevent whipsaws in low-premium environments, the required price recovery % scales based on Days to Expiry (DTE):

| DTE | Days Left | Recovery % Required | Rationale |
| :--- | :--- | :--- | :--- |
| **0** | Expiry Day | **20%** | Max Gamma risk, tiny premiums. Strong filter needed. |
| **1** | Wednesday | **15%** | Low premiums. Moderate filter. |
| **2** | Tuesday | **10%** | Standard decay phase. |
| **3+** | Mon/Fri | **5%** | Higher premiums. Standard filter. |

## Configuration
See [config.py](file:///c:/algo/upstox/strategies/non_directional/rsi_vwap_strangle/config.py) for tunable parameters.
