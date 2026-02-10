# Inside Candle Strategy Rules

## 1. Overview
**Type**: Directional (Trend Following Breakout)
**Timeframe**: 5 Minutes
**Instrument**: NIFTY Options
**Entry Type**: Option Selling (Short CE or Short PE)

## 2. Pattern Logic (Inside Bar Cluster)
The strategy relies on the **Inside Bar** pattern, which indicates consolidation before a breakout. It supports **Multiple Inside Candles** (Mother + Baby 1 + Baby 2...).

- **Mother Candle**: The candle that initiates the pattern (engulfs the first baby).
- **Baby Candles**: Subsequent candles that stay strictly within the Mother Candle's High-Low range.
- **Condition**:
    - Baby High < Mother High
    - Baby Low > Mother Low
- **Persistence**: The Mother Candle remains the reference for reference levels until the price breaks out of its range. Valid for multiple subsequent inside bars.

## 3. Entry Rules
Once an Inside Candle is confirmed (candle closed):
1.  **Monitor Breakout**: Watch the Spot Price (NIFTY 50 Index).
2.  **Bullish Breakout**: Spot Price crosses ABOVE **Mother Candle High**.
    - **Action**: SELL PE (Put Option).
    - **Strike**: ATM - 100.
3.  **Bearish Breakout**: Spot Price crosses BELOW **Mother Candle Low**.
    - **Action**: SELL CE (Call Option).
    - **Strike**: ATM + 100.

## 4. Risk Management

### Stop Loss (Spot Based)
- The initial Stop Loss is based on the **Spot Price**.
- **For Short PE (Bullish Trade)**: Spot SL = Mother Candle Low.
- **For Short CE (Bearish Trade)**: Spot SL = Mother Candle High.
- **Exit Action**: If Spot Price hits the SL level, close the option position immediately.

### Trailing Stop Loss (Tiered & Dynamic)
We use a **Tiered Trailing Stop** to secure profits as the trade moves in our favor.

1.  **Initial Phase**: Standard **20% Trail** on Option Premium (from Lowest Price).
2.  **Tier 1 (Breakeven)**: If Profit > **10%**, TSL moves to **Entry Price** (Risk Free).
3.  **Tier 2 (Locking)**: If Profit > **20%**, TSL tightens to **10% Trail**.
4.  **Tier 3 (Aggressive)**: If Profit > **40%**, TSL tightens to **5% Trail**.

## 5. Execution Details
- **Entry Window**: 9:20 AM to 3:00 PM.
- **Exit Time**: 3:15 PM (Intraday Square-off).
- **Order Type**: Market Orders for entry and exit.
- **Product Type**: MIS (Intraday).

## 6. Example Scenario (Multi-Baby Logic)

### Bullish Breakout Example
1.  **Mother Candle (09:15 - 09:20)**
    *   **High: 24,150** | Low: 24,050
    *   *State*: Established as Master Mother. Pattern Active.

2.  **Baby Candle 1 (09:20 - 09:25)**
    *   High: 24,140 | Low: 24,060
    *   *Result*: Inside Mother Range. Pattern continues.

3.  **Baby Candle 2 (09:25 - 09:30)**
    *   High: 24,130 | Low: 24,080
    *   *Result*: Still Inside Mother Range. Pattern continues.

4.  **Breakout Candle (09:32)**
    *   Spot Price hits **24,151** (New High > Mother High 24,150).
    *   **ACTION**: Bullish Breakout Confirmed.
    *   **TRADE**: SELL PE (Strike = 24,050 PE).
    *   **STOP LOSS**: Spot SL set to Mother Low (24,050).

### Bearish Breakout Example
*   If Spot Price had broken **Below 24,050** (Mother Low) instead:
    *   **Action**: SELL CE (Strike = 24,250 CE).
    *   **Spot SL**: Mother High (24,150).
