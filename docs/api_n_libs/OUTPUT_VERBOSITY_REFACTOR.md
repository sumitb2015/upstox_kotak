# Output Verbosity Refactoring Plan

## Current Problem
The strategy outputs too much information in normal mode:
- Every OI analysis detail
- Every price check
- Every validation step
- Fills the console with hundreds of lines

## Target Behavior

### Normal Mode (verbose=False)
**Single-line updates only:**
```
[12:30:15] 🟢 P&L:₹1250/₹3000 | STR:1 STG:1 | NIFTY:₹25665.6
[12:30:30] 🟢 P&L:₹1320/₹3000 | STR:1 STG:1 | NIFTY:₹25670.2
[12:30:45] ⚠️ Ratio 0.55 below threshold - Managing position
[12:31:00] ✅ Order FILLED: NIFTY2612025700CE @ ₹120.50
```

### Debug Mode (verbose=True)
**Detailed logs:**
```
[12:30:15] 🔍 Checking straddle width for strike 25650
[12:30:15] 📊 CE Price: ₹146.30, PE Price: ₹108.00
[12:30:15] 📊 Width: 26.1% (threshold: 25.0%)
[12:30:15] 📊 NIFTY: ₹25665.6 (deviation: 15.6pts from ATM)
[12:30:15] ✅ Width check passed
[12:30:15] 🟢 P&L:₹1250/₹3000 | STR:1 STG:1 | NIFTY:₹25665.6
```

## Implementation Strategy

### 1. Add debug_print utility (DONE)
- Created `utils/debug_print.py`
- Provides `debug_print()`, `status_print()`, `position_status_line()`

### 2. Refactor print statements
Replace verbose prints with:
```python
# OLD:
print(f"🔍 Checking straddle width for strike {strike}")

# NEW:
debug_print(f"🔍 Checking straddle width for strike {strike}")
```

### 3. Consolidate position display
Replace multi-line position display with single-line:
```python
# OLD (5+ lines):
print(f"[{timestamp}] --- STRADDLE POSITION ---")
print(f"CE Strike: {ce_strike} @ ₹{ce_price:.2f}")
print(f"PE Strike: {pe_strike} @ ₹{pe_price:.2f}")
print(f"Combined P&L: ₹{pnl:.2f}")
print(f"Target: ₹{target:.2f}")

# NEW (1 line):
status_print(position_status_line({
    'straddle_count': 1,
    'total_pnl': pnl,
    'nifty_price': nifty_price,
    'target': target
}))
```

### 4. Categorize print statements

| Category | Normal Mode | Debug Mode |
|----------|-------------|------------|
| **Position Updates** | ✅ Single line | ✅ Detailed |
| **Order Execution** | ✅ Confirmed only | ✅ All steps |
| **OI Analysis** | ❌ Hidden | ✅ Full details |
| **Price Checks** | ❌ Hidden | ✅ All checks |
| **Validation Steps** | ❌ Hidden | ✅ All steps |
| **Errors/Warnings** | ✅ Always show | ✅ Always show |
| **Entry/Exit Signals** | ✅ Always show | ✅ With details |

## Files to Modify

1. **strategies/straddle_strategy.py**
   - Import `debug_print`, `status_print`
   - Replace ~200 print statements
   - Consolidate `display_current_positions()`

2. **api/streaming.py**
   - Move connection messages to debug
   - Keep only critical errors in normal mode

3. **main.py**
   - Clean startup messages
   - Single-line progress indicators

## Priority Sections

### P0 (Most Verbose)
1. `run_strategy()` - OI analysis startup (lines 4237-4330)
2. `display_current_positions()` - Position display (lines 1391-1530)
3. `check_straddle_width()` - Width validation (lines 1053-1130)

### P1 (Moderately Verbose)
4. `wait_for_valid_straddle_width()` - Entry waiting (lines 1324-1389)
5. `place_short_straddle()` - Order placement (lines 3465-3587)
6. `manage_positions()` - Position management (lines 3779-3923)

### P2 (Less Critical)
7. OI analysis methods
8. Strangle/OTM position methods

## Example Refactor

### Before (Verbose):
```python
def check_straddle_width(self, strike, dynamic_threshold=None):
    print(f"🔍 Starting check_straddle_width for strike {strike}")
    
    ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
    print(f"📊 CE Instrument: {ce_instrument_key}")
    
    ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
    print(f"📊 CE Price: ₹{ce_price:.2f}, PE Price: ₹{pe_price:.2f}")
    
    width_percentage = abs(ce_price - pe_price) / max(ce_price, pe_price)
    print(f"📊 Width: {width_percentage*100:.1f}%")
    
    return is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio
```

### After (Clean):
```python
def check_straddle_width(self, strike, dynamic_threshold=None):
    debug_print(f"🔍 Checking straddle width for strike {strike}")
    
    ce_instrument_key = self.get_option_instrument_keys(strike, "CE")
    debug_print(f"📊 CE Instrument: {ce_instrument_key}")
    
    ce_price, pe_price = self.get_current_prices(ce_instrument_key, pe_instrument_key)
    debug_print(f"📊 Prices - CE:₹{ce_price:.2f} PE:₹{pe_price:.2f}")
    
    width_percentage = abs(ce_price - pe_price) / max(ce_price, pe_price)
    debug_print(f"📊 Width: {width_percentage*100:.1f}% (threshold: {dynamic_threshold*100:.0f}%)")
    
    # Only show critical validation failures in normal mode
    if not is_valid:
        status_print(f"Width {width_percentage*100:.1f}% exceeds threshold {dynamic_threshold*100:.0f}%", "WARNING")
    
    return is_valid, ce_price, pe_price, width_percentage, nifty_price, nifty_deviation, ratio
```

## Testing Plan

1. Run with `Config.set_verbose(False)` - should see ~10 lines per minute
2. Run with `Config.set_verbose(True)` - should see all details
3. Verify critical alerts still show in both modes
4. Verify position updates are single-line in normal mode

## Rollout

**Phase 1**: Create utility module ✅ DONE
**Phase 2**: Refactor P0 sections (most verbose)
**Phase 3**: Refactor P1 sections
**Phase 4**: Refactor P2 sections
**Phase 5**: Test and validate

---

**Status**: Ready to implement Phase 2
**Estimated Lines to Change**: ~200-300 print statements
**Estimated Time**: 15-20 minutes
