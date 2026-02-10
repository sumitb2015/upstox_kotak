# ORB Break-Retest Strategy - Rules & Examples

Complete rule-based documentation for the Opening Range Breakout strategy with break-and-retest confirmation.

---

## Core Philosophy

**The Edge**: Most traders lose money on breakouts because they chase momentum. This strategy waits for the market to prove the breakout is real by retesting the level with strong confirmation.

**Key Insight**: Real breakouts retest. Fake breakouts don't.

---

## Strategy Rules

### 1. Opening Range (OR) Detection

**Time**: 09:15 - 09:20 (First 5-minute candle)

**Calculation**:
```
OR High = High of 09:15-09:20 candle
OR Low = Low of 09:15-09:20 candle
OR Range = OR High - OR Low
```

**Validation**:
- ✅ OR Range >= 20 points (minimum)
- ✅ OR Range <= 150 points (maximum)
- ❌ Skip trading if outside these bounds

**Why**:
- Narrow range (<20) = Consolidation day, low probability
- Wide range (>150) = Excessive volatility, unpredictable

---

### 2. Breakout Detection

**Timeframe**: 5-minute chart

**Bullish Breakout**:
```
IF 5-min candle CLOSE > OR High
THEN Breakout Direction = LONG
```

**Bearish Breakout**:
```
IF 5-min candle CLOSE < OR Low
THEN Breakout Direction = SHORT
```

**Critical Rules**:
- ✅ Candle CLOSE must be outside OR (not just wick)
- ❌ Do NOT enter on breakout candle
- ✅ Wait for retest

**Why Close vs Wick**:
- Wick-only breakouts are often fake (stop hunts)
- Close outside OR shows commitment

---

### 3. Retest Confirmation

**Timeframe**: 1-minute chart

**Bullish Retest** (After upside breakout):
```
1. Price pulls back to OR High (±5 points tolerance)
2. 1-min candle shows strong bullish confirmation:
   - Bullish close (Close > Open)
   - Large body (>60% of candle range)
   - Small lower wick (<30% of range)
3. Entry triggered
```

**Bearish Retest** (After downside breakout):
```
1. Price rallies back to OR Low (±5 points tolerance)
2. 1-min candle shows strong bearish confirmation:
   - Bearish close (Close < Open)
   - Large body (>60% of candle range)
   - Small upper wick (<30% of range)
3. Entry triggered
```

**Timeout**: 30 minutes
- If no retest within 30 min of breakout, skip trade

**Why Retest**:
- Proves breakout is real
- Provides better entry price
- Reduces risk (tighter stop loss)

---

### 4. Entry Rules

**Long Entry**:
```
Entry Price = Close of confirmation candle
Stop Loss = OR Low - 10 points
Risk = Entry - Stop Loss
Target = Entry + (Risk × 2)
```

**Short Entry**:
```
Entry Price = Close of confirmation candle
Stop Loss = OR High + 10 points
Risk = Stop Loss - Entry
Target = Entry - (Risk × 2)
```

**Position Sizing**:
- Fixed lot size (configurable)
- One trade per direction per day

---

### 5. Exit Rules

**Stop Loss**:
- Long: Price <= Stop Loss
- Short: Price >= Stop Loss

**Target**:
- Long: Price >= Target (2R minimum)
- Short: Price <= Target (2R minimum)

**Time Exit**:
- Close position at 10:45 AM (end of trading window)

**Invalidation**:
- No retest within 30 minutes
- Price breaks opposite side of OR

---

## Trade Examples

### Example 1: Successful Long Trade

```
09:15-09:20: OR formed
  High: 25,600
  Low: 25,550
  Range: 50 points ✅ (Valid)

09:25: Breakout
  5-min close: 25,615 (> 25,600) ✅
  Direction: LONG
  Wait for retest...

09:32: Retest
  1-min candle:
    Open: 25,598
    High: 25,608
    Low: 25,595
    Close: 25,605
  
  Analysis:
    - Price near OR High (25,600) ✅
    - Bullish candle (Close > Open) ✅
    - Body = 7, Range = 13, Body% = 54% ❌ (< 60%)
  
  Result: NO ENTRY (weak candle)

09:35: Second Retest
  1-min candle:
    Open: 25,597
    High: 25,610
    Low: 25,596
    Close: 25,608
  
  Analysis:
    - Price near OR High ✅
    - Bullish candle ✅
    - Body = 11, Range = 14, Body% = 79% ✅
    - Lower wick = 1, Wick% = 7% ✅
  
  Result: ENTRY TRIGGERED ✅

Entry: 25,608
Stop Loss: 25,550 - 10 = 25,540
Risk: 68 points
Target: 25,608 + (68 × 2) = 25,744

Outcome: Target hit at 10:15 AM
P&L: +136 points (2R)
```

---

### Example 2: Failed Short Trade (Stopped Out)

```
09:15-09:20: OR formed
  High: 25,620
  Low: 25,580
  Range: 40 points ✅

09:30: Breakout
  5-min close: 25,570 (< 25,580) ✅
  Direction: SHORT
  Wait for retest...

09:38: Retest
  1-min candle:
    Open: 25,585
    High: 25,587
    Low: 25,575
    Close: 25,576
  
  Analysis:
    - Price near OR Low (25,580) ✅
    - Bearish candle ✅
    - Body = 9, Range = 12, Body% = 75% ✅
    - Upper wick = 2, Wick% = 17% ✅
  
  Result: ENTRY TRIGGERED ✅

Entry: 25,576
Stop Loss: 25,620 + 10 = 25,630
Risk: 54 points
Target: 25,576 - (54 × 2) = 25,468

09:55: Stop Loss Hit
  Price rallied to 25,635
  
Outcome: Stopped out
P&L: -54 points (-1R)
```

---

### Example 3: No Trade (Narrow OR)

```
09:15-09:20: OR formed
  High: 25,595
  Low: 25,580
  Range: 15 points ❌ (< 20 minimum)

Result: SKIP TRADING (consolidation day)
```

---

### Example 4: No Trade (No Retest)

```
09:15-09:20: OR formed
  High: 25,610
  Low: 25,560
  Range: 50 points ✅

09:25: Breakout
  5-min close: 25,625 (> 25,610) ✅
  Direction: LONG
  Wait for retest...

10:00: Timeout
  35 minutes elapsed, no retest
  
Result: NO TRADE (retest timeout)
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Entering on Breakout
```
Wrong: Buy when price breaks OR High
Right: Wait for retest and confirmation
```

### ❌ Mistake 2: Accepting Weak Candles
```
Wrong: Enter on any candle near retest level
Right: Require strong body (>60%) and small wick
```

### ❌ Mistake 3: Trading Narrow Ranges
```
Wrong: Trade all ORs
Right: Skip if range < 20 points
```

### ❌ Mistake 4: Ignoring Timeout
```
Wrong: Wait indefinitely for retest
Right: Cancel after 30 minutes
```

---

## Risk:Reward Analysis

**Why 2R Minimum**:
- Win rate: ~50-60% (realistic for retest strategy)
- With 2R: Break-even at 33% win rate
- Provides cushion for losses

**Retest Advantage**:
- Better entry price (closer to support/resistance)
- Tighter stop loss (below/above OR)
- Higher R:R compared to breakout entry

**Example Comparison**:

| Entry Type | Entry | Stop Loss | Risk | Target | R:R |
|------------|-------|-----------|------|--------|-----|
| Breakout | 25,615 | 25,540 | 75 | 25,690 | 1:1 |
| Retest | 25,605 | 25,540 | 65 | 25,735 | 1:2 |

**Benefit**: 13% less risk, 60% more reward!

---

## Performance Expectations

**Win Rate**: 50-60%
**Average R:R**: 1:2
**Max Trades/Day**: 1-2
**Best Days**: Trending days with clear direction
**Worst Days**: Choppy, range-bound days

---

## Quick Reference Checklist

Before entering a trade, verify:

- [ ] OR range is 20-150 points
- [ ] 5-min candle CLOSED outside OR
- [ ] Retest occurred within 30 minutes
- [ ] 1-min confirmation candle is strong:
  - [ ] Body > 60% of range
  - [ ] Opposite wick < 30%
- [ ] Stop loss is beyond OR
- [ ] Target is at least 2R
- [ ] Current time < 10:45 AM

If ALL boxes checked: ✅ ENTER TRADE
If ANY box unchecked: ❌ SKIP TRADE
