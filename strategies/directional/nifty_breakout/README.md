# Nifty Breakout Strategy

## 📈 Strategy Overview
This is a directional strategy that trades breakouts of **Yesterday's High or Low**, confirmed by the **Supertrend** indicator.

- **Underlying**: Nifty 50 Index.
- **Instrument**: Options (Buying/Selling). *Configured for Selling (Credit Strategy).*
- **Direction**:
    - **Bullish**: Price > Prev Day High + Supertrend Positive. -> **SELL PE** (OTM).
    - **Bearish**: Price < Prev Day Low + Supertrend Negative. -> **SELL CE** (OTM).

## ⚙️ Configuration (`config.py`)
| Parameter | Value | Description |
| :--- | :--- | :--- |
| `SL_PCT` | **20%** | Stop Loss per leg. |
| `TARGET_PCT` | **20%** | Target Profit per leg. |
| `PYRAMID_PCT` | **5%** | Add accumulation every 5% profit. |
| `MAX_PYRAMID_COUNT`| **3** | Max number of accumulations. |
| `STRIKE_OFFSET` | **2** | Strikes OTM to select. |
| `EXIT_TIME` | **15:18** | Intraday Square-off. |

## 🧠 Logic Flow

```mermaid
graph TD
    A[Start Loop] --> B{Check Time < 15:18}
    B -- No --> Z[Exit / Square-off]
    B -- Yes --> C[Fetch Live Data]
    C --> D[Calculate Supertrend]
    
    D --> E{Entry Signal?}
    E -- Bullish --> F[Sell PE (2 Strikes OTM)]
    E -- Bearish --> G[Sell CE (2 Strikes OTM)]
    E -- None --> H[Manage Positions]
    
    H --> I{Check Conditions}
    I -- SL Hit --> J[Exit Position]
    I -- Target Hit --> K[Exit Position]
    I -- Profit > 5% --> L[Pyramid (Add Lots)]
    I -- Else --> A
```

## 🛠️ Components
- **`core.py`**: Contains the pure logic for Signal Generation and Strike Selection.
- **`live.py`**: Handles Data Fetching (History + Intraday), Order Execution (via Kotak), and Risk Management.

## ⚠️ Prerequisities
- **Upstox API**: For Market Data (Candles, LTP).
- **Kotak Neo API**: For Order Execution.
- **LTP Fetching**: Uses `lib.api.market_data.get_ltp` with Upstox Instrument Keys.
