# Delta-Neutral Option Selling Strategy - Implementation Plan

## Strategy Overview

**Type**: Delta-Neutral Short Straddle/Strangle with Dynamic Hedging  
**Objective**: Maximize premium collection while maintaining delta neutrality through automatic adjustments  
**Key Metrics**: Portfolio Delta, Gamma, Theta decay, P&L

---

## Strategy Concept

### Delta-Neutral Positioning
A delta-neutral portfolio has **net delta ≈ 0**, meaning it's not significantly affected by small price movements. This is achieved by:

1. **Initial Entry**: Sell ATM straddle (CE + PE with deltas ≈ +0.5 and -0.5)
2. **Monitor Delta**: Calculate total portfolio delta continuously
3. **Hedge When Needed**: Add/remove positions to bring delta back to neutral range

### What is Delta?
- **Call Delta**: +0.5 means for every ₹1 increase in underlying, option gains ₹0.50
- **Put Delta**: -0.5 means for every ₹1 increase in underlying, option loses ₹0.50
- **Portfolio Delta**: Sum of all position deltas × lot size

**Example**:
```
Sold 1 lot CE (delta +0.50) × 65 qty = +32.5 delta
Sold 1 lot PE (delta -0.50) × 65 qty = -32.5 delta
Portfolio Delta = +32.5 - 32.5 = 0 (perfectly neutral)
```

---

## Strategy Parameters

### Entry Criteria
- **Position Type**: Short Straddle (sell ATM CE + ATM PE)
- **Lot Size**: 1 lot (65 qty for NIFTY)
- **Entry Trigger**: VIX > 12 (higher volatility = higher premiums)
- **Target Delta**: 0 ± 10 (portfolio delta between -10 and +10)

### Hedging Triggers
- **Delta Breach**: Portfolio delta > 15 or < -15
- **Hedging Action**:
  - If delta > +15: Sell additional PE or buy back some CE
  - If delta < -15: Sell additional CE or buy back some PE

### Exit Criteria
- **Profit Target**: 50% of collected premium
- **Stop Loss**: -2× collected premium
- **Time Exit**: Close all at 3:15 PM
- **Max Delta Breach**: Portfolio delta > 50 (emergency exit)

---

## Proposed Changes

### [NEW] [delta_neutral_strategy.py](file:///c:/algo/upstox/strategies/delta_neutral_strategy.py)

New strategy file implementing delta-neutral logic.

#### Key Components

**1. Portfolio Delta Calculation**
```python
def calculate_portfolio_delta(self):
    """Calculate net portfolio delta"""
    total_delta = 0
    for position in self.active_positions:
        greeks = get_greeks(self.option_chain_df, position['strike'], position['type'])
        position_delta = greeks['delta'] * position['quantity'] * position['direction']
        total_delta += position_delta
    return total_delta
```

**2. Hedging Logic**
```python
def check_and_hedge(self):
    """Check delta and hedge if needed"""
    portfolio_delta = self.calculate_portfolio_delta()
    
    if portfolio_delta > self.delta_threshold:
        # Too bullish - need to add negative delta
        self.hedge_with_put()
    elif portfolio_delta < -self.delta_threshold:
        # Too bearish - need to add positive delta
        self.hedge_with_call()
```

**3. Position Management**
```python
class Position:
    def __init__(self, strike, type, quantity, entry_price, direction):
        self.strike = strike
        self.type = type  # "CE" or "PE"
        self.quantity = quantity
        self.entry_price = entry_price
        self.direction = direction  # +1 for buy, -1 for sell
        self.current_delta = 0
        self.current_price = 0
```

**4. Risk Monitoring**
```python
def monitor_risk(self):
    """Monitor portfolio Greeks and P&L"""
    portfolio_delta = self.calculate_portfolio_delta()
    portfolio_gamma = self.calculate_portfolio_gamma()
    portfolio_theta = self.calculate_portfolio_theta()
    
    return {
        'delta': portfolio_delta,
        'gamma': portfolio_gamma,
        'theta': portfolio_theta,
        'pnl': self.calculate_pnl()
    }
```

---

## Implementation Strategy

### Phase 1: Core Structure
1. Create `DeltaNeutralStrategy` class
2. Add position tracking with Greeks
3. Implement portfolio delta calculation
4. Add option chain integration

### Phase 2: Hedging Logic
1. Define hedging triggers (delta thresholds)
2. Implement hedging actions (add CE/PE)
3. Add position adjustment logic
4. Implement emergency exit conditions

### Phase 3: Risk Management
1. Add portfolio Greek monitoring
2. Implement P&L tracking
3. Add stop-loss and profit-target logic
4. Implement time-based exits

### Phase 4: Display & Logging
1. Add real-time portfolio status display
2. Show current Greeks and delta
3. Log all hedging actions
4. Display P&L and target progress

---

## Hedging Examples

### Scenario 1: Market Moves Up
```
Initial: Sold CE (Δ=+0.5) + PE (Δ=-0.5) → Portfolio Δ = 0
NIFTY ↑ 100 points
New: CE (Δ=+0.6) + PE (Δ=-0.3) → Portfolio Δ = +19.5

Action: Sell 1 more PE lot (Δ=-0.3) → Portfolio Δ = -0

Result: Back to neutral
```

### Scenario 2: Market Moves Down
```
Initial: Sold CE (Δ=+0.5) + PE (Δ=-0.5) → Portfolio Δ = 0
NIFTY ↓ 100 points
New: CE (Δ=+0.3) + PE (Δ=-0.6) → Portfolio Δ = -19.5

Action: Sell 1 more CE lot (Δ=+0.3) → Portfolio Δ = 0

Result: Back to neutral
```

---

## Verification Plan

### Test Cases
1. **Delta Calculation**: Verify portfolio delta matches expected values
2. **Hedging Triggers**: Test that hedging activates at correct thresholds
3. **Position Tracking**: Ensure all positions tracked with correct Greeks
4. **P&L Accuracy**: Validate P&L calculations against actual prices

### Manual Verification
- Review hedging decisions during backtesting
- Check that delta stays within target range
- Verify premium collection and P&L progression

---

## Key Benefits

1. ✅ **Market Neutral**: Profits from time decay, not direction
2. ✅ **Automatic Hedging**: No manual intervention needed
3. ✅ **Risk Controlled**: Delta limits prevent directional risk
4. ✅ **Premium Collection**: Maximizes theta decay revenue
5. ✅ **Greek-Based**: Uses real-time Greeks for decisions
