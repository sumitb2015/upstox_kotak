# Clean Output Mode - Final Configuration

## Target Output (Normal Mode)

### Startup (One-time)
```
Starting Short Straddle Strategy until market close (3:15 PM)
📍 Current ATM strike for strategy: 25650
🔴 OI: BEARISH FOR SELLERS (Score:35 PCR:0.94)
🚀 Starting 3-Strategy System: Straddle | Strangle | Safe OTM
Strategy will run until market close: 15:15:00
```

### During Operation (Every 15 seconds)
```
[14:03:33] 🟢 P&L:₹0/₹3000 | STG:1 | NIFTY:₹25665.6
[14:03:50] 🟢 P&L:₹0/₹3900 | STG:1 | NIFTY:₹25670.2
[14:04:09] 🟢 P&L:₹0/₹3900 | STG:1 | NIFTY:₹25665.6
```

### Critical Events Only
```
✅ Order FILLED: NIFTY2612025700CE @ ₹120.10
❌ Order REJECTED: Insufficient funds
⚠️ ALERT: Approaching max loss limit!
🎯 Profit target achieved!
```

---

## What Should Be HIDDEN in Normal Mode

### ❌ Remove These:
- `🔍 [CALL-xxxxx] Starting check_straddle_width...`
- `Found CE 25650: NSE_FO|47611...`
- `Subscribed to 2 instruments in ltpc mode.`
- `Invalid prices for strike 25650: CE=None, PE=None`
- `No option chain data found.`
- `⚠️ Failed to get current prices for strangle...`
- `DEBUG [Market Raw]: {...}`
- `DEBUG [Portfolio Raw]: {...}`
- All cache age messages
- All OI analysis details (unless critical)

### ✅ Keep These:
- Single-line P&L status
- Order confirmations/rejections
- Critical alerts (max loss, profit target)
- Strategy start/stop messages
- Strangle position summary (compact)

---

## Changes Needed

### 1. Hide "Found CE/PE" Messages
**File**: Wherever instrument keys are being looked up
**Change**: Wrap in `if self.verbose:`

### 2. Hide "Subscribed to X instruments" 
**File**: `strategies/straddle_strategy.py` - `_subscribe_to_instruments()`
**Status**: Already wrapped in `if self.verbose:` ✅

### 3. Hide "Invalid prices" Messages
**File**: `strategies/straddle_strategy.py` - `check_straddle_width()`
**Change**: Wrap in `if self.verbose:`

### 4. Hide "No option chain data found"
**File**: Wherever option chain is fetched
**Change**: Wrap in `if self.verbose:`

### 5. Hide Strangle Price Failures
**File**: `strategies/straddle_strategy.py` - `manage_strangle_positions()`
**Status**: Already removed ✅

---

## Implementation Status

| Item | Status |
|------|--------|
| Debug output removed | ✅ Done |
| Cache age logging removed | ✅ Done |
| Strangle failure messages removed | ✅ Done |
| Position display single-line | ✅ Done |
| OI analysis single-line | ✅ Done |
| WebSocket debug mode | ✅ Toggleable |

---

## Remaining Verbose Output Sources

Need to find and wrap in `if self.verbose:`:
1. `🔍 [CALL-xxxxx]` messages
2. `Found CE/PE` messages
3. `Invalid prices` messages
4. `No option chain data` messages

These are likely in:
- `check_straddle_width()`
- `get_option_instrument_keys()`
- Option chain fetching methods

---

**Next Step**: Search for these specific print statements and wrap them in verbose checks.
