# 📟 Agent Console Output Standards

This file defines the **MANDATORY** standard for console output across all strategies in the `algo/upstox` codebase.
Consistency in output allows for easier monitoring and debugging.

## 🎨 Visual Style Guide

- **Timestamps**: Always `[HH:MM:SS]`
- **Separators**: Use 60 dashes `"-" * 60` or equals `"=" * 60` for major sections.
- **Emojis**: Use specific emojis for specific event types.
- **Indentation**: Use 2 or 4 spaces to align detailed info under headers.

## 📦 Event Templates

### 1. Strategy Startup
```text
============================================================
🚀 [STRATEGY NAME] - LIVE
============================================================
⚙️  Config:   [Interval]min candles | [Parameters]
📊 Threshold: [Value] points
🎯 Targets:   [Profit]% Profit | [SL]x SL
============================================================
```

### 2. Status Ticker (Every Cycle)
Keep this **concise** (1-2 lines max).
```text
⏰ [HH:MM:SS] | NIFTY: 23500.50 | EMA9: 23510 | EMA20: 23490 | Diff: +20.0 (INCREASING)
```

### 3. Position Status
```text
💼 POS: BULL_PUT_SPREAD | P&L: +₹1,500.00 (+12.5%) | Time: 45m | TSL: ₹1,000
```

### 4. Entry Signal (Boxed)
```text
------------------------------------------------------------
🎯 ENTRY SIGNAL DETECTED
------------------------------------------------------------
Direction: 🟢 BULL PUT SPREAD
Reason:    Price(23500) > EMA9(23480) > EMA20(23450)
Momentum:  INCREASING (Strong)
Strike:    23400 PE (Short) | 23250 PE (Hedge)
------------------------------------------------------------
```

### 5. Execution Success
```text
✅ EXECUTION COMPLETE
------------------------------------------------------------
IDs:       Short: 240101000567 | Long: 240101000568
Avg Price: Short: ₹150.50 | Long: ₹20.50
Credit:    ₹130.00 (Net)
------------------------------------------------------------
```

### 6. Adjustments / TSL Updates (Boxed)
```text
------------------------------------------------------------
🔒 TRAILING STOP UPDATE
------------------------------------------------------------
Trigger:   Profit reached 40% (Current: 42%)
Action:    Locking 20% Profit
New TSL:   ₹2,500.00
------------------------------------------------------------
```

### 7. Exit Signal (Boxed)
```text
------------------------------------------------------------
🚨 EXIT SIGNAL DETECTED
------------------------------------------------------------
Type:      ✅ PROFIT TARGET HIT
Reason:    55% >= 50% Target
P&L:       +₹5,000.00
------------------------------------------------------------
```

## 🛠️ Implementation Helper (Python)

```python
def print_box(title, content_lines, emoji="ℹ️"):
    print("-" * 60)
    print(f"{emoji} {title}")
    print("-" * 60)
    for line in content_lines:
        print(f"   {line}")
    print("-" * 60)
```
