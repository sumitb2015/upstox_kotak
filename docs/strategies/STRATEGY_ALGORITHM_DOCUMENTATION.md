# Short Straddle Strategy - Complete Algorithm Documentation

## Table of Contents
1. [Strategy Overview](#strategy-overview)
2. [Core Algorithm Flow](#core-algorithm-flow)
3. [Market Monitoring System](#market-monitoring-system)
4. [Trade Decision Factors](#trade-decision-factors)
5. [Position Scaling Logic](#position-scaling-logic)
6. [Open Interest (OI) Integration](#open-interest-oi-integration)
7. [Risk Management Framework](#risk-management-framework)
8. [Margin Management System](#margin-management-system)
9. [Order Management & Execution](#order-management--execution)
10. [Performance Monitoring](#performance-monitoring)
11. [Configuration Parameters](#configuration-parameters)
12. [Multi-Strategy Framework](#multi-strategy-framework)
    - [12.1 Short Straddle Strategy](#121-short-straddle-strategy)
    - [12.2 Safe OTM Options Strategy](#122-safe-otm-options-strategy)
    - [12.3 OI-Guided Strangle Strategy](#123-oi-guided-strangle-strategy)

---

## Strategy Overview

### What is a Short Straddle?
A short straddle is an options strategy where we simultaneously sell a Call Option (CE) and a Put Option (PE) at the same strike price (ATM - At The Money). This strategy profits when the underlying asset (NIFTY) remains within a specific range and doesn't move significantly in either direction.

### Strategy Objectives
- **Primary Goal**: Generate consistent profits from time decay (theta) and volatility contraction
- **Target**: ₹3,000 profit per straddle position
- **Risk Management**: Maximum loss limit of ₹3,000 per position
- **Time Frame**: Intraday trading (9:15 AM to 3:15 PM)

### Key Assumptions
- NIFTY will remain range-bound during the trading session
- Time decay will work in favor of the strategy
- Volatility will contract from opening levels

---

## Core Algorithm Flow

### 1. Initialization Phase
```
1. Load access token and NSE market data
2. Initialize strategy parameters
3. Check available funds and margin
4. Set up OI analysis components (if enabled)
5. Validate market conditions
6. Start monitoring loop
```

### 2. Main Monitoring Loop (Every 15 seconds)
```
WHILE (current_time < 3:15 PM) AND (strategy_active):
    1. Get current NIFTY spot price
    2. Calculate ATM strike
    3. Check market conditions
    4. Analyze OI data (if enabled)
    5. Evaluate existing positions
    6. Make trading decisions
    7. Execute orders if needed
    8. Update position tracking
    9. Sleep for 15 seconds
```

### 3. Position Entry Logic
```
IF (no_active_positions) AND (market_conditions_favorable):
    1. Calculate ATM strike
    2. Get CE and PE instrument keys
    3. Check margin availability
    4. Validate trade parameters
    5. Place short straddle orders
    6. Track position details
```

### 4. Position Management Logic
```
IF (active_positions_exist):
    1. Get current option prices
    2. Calculate profit/loss for each position
    3. Check ratio thresholds
    4. Evaluate scaling opportunities
    5. Execute position adjustments
    6. Monitor risk limits
```

---

## Market Monitoring System

### 1. Real-Time Price Monitoring
- **NIFTY Spot Price**: Fetched every 15 seconds using LTP API
- **Option Prices**: CE and PE prices for active positions
- **Price Validation**: Ensures data quality and handles API failures

### 2. Market Condition Assessment
```python
def validate_market_conditions():
    - Check if market is open (9:15 AM - 3:15 PM)
    - Verify NIFTY spot price availability
    - Calculate ATM strike price
    - Validate option instrument keys
    - Check initial CE/PE price ratio
    - Ensure ratio is above threshold (0.6)
```

### 3. Time-Based Monitoring
- **Market Hours**: 9:15 AM to 3:15 PM
- **Check Interval**: 15 seconds (configurable)
- **Expiry Day Mode**: Special handling for expiry days
- **Time Decay Tracking**: Monitors theta impact on positions

### 4. API Rate Limiting
- **Request Counter**: Tracks API calls per minute
- **Rate Limit**: 200 requests per minute
- **Backoff Strategy**: Automatic delays when limits approached

---

## Trade Decision Factors

### 1. Primary Entry Criteria
```python
def should_enter_straddle():
    return (
        no_active_positions AND
        market_is_open AND
        nifty_spot_available AND
        atm_strike_calculated AND
        instrument_keys_valid AND
        initial_ratio > 0.8 AND
        sufficient_margin_available
    )
```

### 2. Ratio-Based Decision Making
- **Initial Ratio**: min(CE_price, PE_price) / max(CE_price, PE_price)
- **Threshold**: 0.8 (80% ratio required for entry)
- **Dynamic Adjustment**: Expiry day mode uses lower thresholds

### 3. Market Volatility Assessment
- **Straddle Width**: (CE_price + PE_price) / NIFTY_spot
- **Width Threshold**: 0.25 (25% of spot price)
- **Volatility Filter**: Ensures adequate premium collection

### 4. Time-Based Factors
- **Market Timing**: Avoids first 30 minutes and last 30 minutes
- **Time Decay**: Favors positions with higher theta
- **Expiry Day**: Special handling for monthly expiry

### 5. OI-Based Decisions (When Enabled)
- **OI Sentiment**: Bullish/Bearish/Neutral analysis
- **OI Concentration**: High OI strikes preferred
- **OI Changes**: Significant OI movements influence decisions

---

## Position Scaling Logic

### 1. Scaling Triggers
```python
def should_scale_position():
    return (
        existing_position_profitable AND
        ratio_above_threshold AND
        sufficient_margin AND
        max_positions_not_reached AND
        market_conditions_stable
    )
```

### 2. Scaling Criteria
- **Profit Threshold**: Position must be in profit
- **Ratio Requirement**: Current ratio > 0.8
- **Margin Check**: Sufficient funds for additional position
- **Position Limit**: Maximum 3 positions (configurable)
- **Time Window**: Avoid scaling in last hour

### 3. Scaling Execution
```python
def execute_scaling():
    1. Calculate new ATM strike
    2. Get new instrument keys
    3. Validate margin requirements
    4. Place additional straddle
    5. Update position tracking
    6. Adjust profit targets
```

### 4. Position Management
- **Individual Tracking**: Each position monitored separately
- **Profit Targets**: ₹3,000 per position
- **Loss Limits**: ₹3,000 maximum loss per position
- **Collective Management**: Overall portfolio limits

---

## Open Interest (OI) Integration

### 1. OI Analysis Components
```python
# OI Analyzer - Analyzes OI changes and sentiment
self.oi_analyzer = OIAnalyzer(
    access_token, 
    "NSE_INDEX|Nifty 50",
    min_oi_threshold=5.0,      # 5% minimum OI change
    significant_oi_threshold=10.0  # 10% significant change
)

# OI Monitor - Real-time OI monitoring
self.oi_monitor = OIMonitor(access_token, "NSE_INDEX|Nifty 50")

# Cumulative OI Analyzer - Historical OI analysis
self.cumulative_oi_analyzer = CumulativeOIAnalyzer(access_token, "NSE_INDEX|Nifty 50")

# OI Strangle Analyzer - Strangle-specific OI analysis
self.oi_strangle_analyzer = OIStrangleAnalyzer(access_token, "NSE_INDEX|Nifty 50")
```

### 2. OI-Based Decision Making
```python
def analyze_oi_sentiment():
    oi_data = self.oi_analyzer.get_oi_sentiment_analysis()
    
    if oi_data['sentiment'] == 'bullish':
        # Increase targets for sellers (more premium)
        return self.risk_adjustment_factors['oi_bullish_multiplier']
    elif oi_data['sentiment'] == 'bearish':
        # Decrease targets for sellers (less premium)
        return self.risk_adjustment_factors['oi_bearish_multiplier']
    else:
        return 1.0  # Neutral
```

### 3. OI Monitoring Integration
- **Real-time Updates**: OI data fetched every monitoring cycle
- **Sentiment Analysis**: Bullish/Bearish/Neutral classification
- **Strike Selection**: OI concentration influences strike selection
- **Risk Adjustment**: OI sentiment modifies risk parameters

### 4. OI-Based Risk Adjustment
```python
risk_adjustment_factors = {
    'oi_bullish_multiplier': 1.5,  # Increase targets when OI bullish
    'oi_bearish_multiplier': 0.7,  # Decrease targets when OI bearish
    'volatility_multiplier': 1.2,  # Adjust for high volatility
    'time_decay_multiplier': 1.3,  # Increase targets with time decay
    'profit_momentum_multiplier': 1.4  # Increase targets in profit
}
```

---

## Risk Management Framework

### 1. Position-Level Risk Management
```python
def check_position_risk(position):
    current_pnl = calculate_position_pnl(position)
    
    if current_pnl >= profit_target:
        return "PROFIT_TARGET_REACHED"
    elif current_pnl <= -max_loss_limit:
        return "STOP_LOSS_TRIGGERED"
    elif ratio < ratio_threshold:
        return "RATIO_THRESHOLD_BREACHED"
    else:
        return "POSITION_HEALTHY"
```

### 2. Portfolio-Level Risk Management
- **Maximum Positions**: 3 straddles maximum
- **Total Exposure**: Monitored across all positions
- **Margin Utilization**: Real-time margin tracking
- **Drawdown Limits**: Maximum portfolio loss limits

### 3. Dynamic Risk Adjustment
```python
def adjust_risk_parameters():
    if expiry_day_mode:
        ratio_threshold = 0.5  # More lenient on expiry
        profit_target *= 1.2   # Higher targets
    else:
        ratio_threshold = 0.6  # Standard threshold
        profit_target = 3000   # Standard target
```

### 4. Emergency Exit Conditions
- **Market Close**: Automatic exit at 3:15 PM
- **System Errors**: Graceful handling of API failures
- **Margin Shortfall**: Immediate position closure
- **Extreme Volatility**: Emergency stop conditions

---

## Margin Management System

### 1. Pre-Trade Margin Validation
```python
def validate_trade_margin(ce_key, pe_key, quantity):
    1. Calculate required margin for straddle
    2. Check available funds in account
    3. Verify margin utilization percentage
    4. Return validation result with details
```

### 2. Real-Time Margin Monitoring
- **Available Funds**: Fetched before each trade
- **Margin Requirements**: Calculated for each position
- **Utilization Tracking**: Monitors margin usage percentage
- **Shortfall Alerts**: Warns when funds insufficient

### 3. Margin Calculation Process
```python
def calculate_straddle_margin():
    instruments = [
        {"instrument_key": ce_key, "quantity": 75, "transaction_type": "SELL", "product": "D"},
        {"instrument_key": pe_key, "quantity": 75, "transaction_type": "SELL", "product": "D"}
    ]
    
    margin_data = get_margin_details(access_token, instruments)
    return margin_data['data']['final_margin']
```

### 4. Margin-Based Trade Decisions
- **Entry Validation**: No trade without sufficient margin
- **Scaling Validation**: Additional positions require margin check
- **Emergency Exits**: Margin shortfall triggers position closure

---

## Order Management & Execution

### 1. Order Placement Process
```python
def place_short_straddle(strike):
    1. Get CE and PE instrument keys
    2. Validate margin availability
    3. Place SELL order for CE (Market order)
    4. Place SELL order for PE (Market order)
    5. Track order IDs and status
    6. Update position tracking
```

### 2. Order Types and Parameters
- **Order Type**: MARKET (for immediate execution)
- **Product**: MIS (Margin Intraday Square-off)
- **Validity**: DAY
- **Quantity**: 75 (NIFTY lot size)
- **Transaction**: SELL (for short straddle)

### 3. Order Status Monitoring
- **Order Confirmation**: Verify successful placement
- **Fill Status**: Monitor partial/full fills
- **Error Handling**: Retry logic for failed orders
- **Position Tracking**: Link orders to positions

### 4. Position Exit Logic
```python
def exit_position(position):
    1. Get current CE and PE prices
    2. Place BUY orders to close positions
    3. Calculate final P&L
    4. Update position status
    5. Record trade history
```

---

## Performance Monitoring

### 1. Real-Time P&L Tracking
```python
def calculate_position_pnl(position):
    ce_current_price = get_current_price(position['ce_instrument_key'])
    pe_current_price = get_current_price(position['pe_instrument_key'])
    
    ce_pnl = (position['ce_entry_price'] - ce_current_price) * quantity
    pe_pnl = (position['pe_entry_price'] - pe_current_price) * quantity
    
    return ce_pnl + pe_pnl
```

### 2. Performance Metrics
- **Individual Position P&L**: Real-time tracking
- **Portfolio P&L**: Aggregate across all positions
- **Win Rate**: Percentage of profitable trades
- **Average Profit**: Mean profit per successful trade
- **Maximum Drawdown**: Largest peak-to-trough decline

### 3. Trade History Tracking
```python
trade_history = {
    'entry_time': datetime,
    'strike_price': int,
    'ce_entry_price': float,
    'pe_entry_price': float,
    'exit_time': datetime,
    'ce_exit_price': float,
    'pe_exit_price': float,
    'total_pnl': float,
    'exit_reason': str
}
```

### 4. Performance Analysis
- **Daily Performance**: End-of-day summary
- **Weekly Trends**: Performance patterns
- **Risk Metrics**: Sharpe ratio, maximum drawdown
- **Strategy Effectiveness**: Success rate analysis

---

## Configuration Parameters

### 1. Core Strategy Parameters
```python
strategy_config = {
    'underlying_symbol': 'NIFTY',
    'lot_size': 1,
    'profit_target': 3000,
    'max_loss_limit': 3000,
    'ratio_threshold': 0.6,
    'straddle_width_threshold': 0.25,
    'max_deviation_points': 200,
    'check_interval_seconds': 15
}
```

### 2. Risk Management Parameters
```python
risk_config = {
    'max_positions': 3,
    'expiry_day_mode': True,
    'enable_oi_analysis': True,
    'min_funds_threshold': 10000,
    'margin_utilization_limit': 80
}
```

### 3. OI Analysis Parameters
```python
oi_config = {
    'min_oi_threshold': 5.0,
    'significant_oi_threshold': 10.0,
    'oi_bullish_multiplier': 1.5,
    'oi_bearish_multiplier': 0.7,
    'volatility_multiplier': 1.2
}
```

### 4. Market Timing Parameters
```python
timing_config = {
    'market_open_time': '09:15',
    'market_close_time': '15:15',
    'avoid_first_minutes': 30,
    'avoid_last_minutes': 30,
    'scaling_cutoff_time': '14:15'
}
```

---

## Algorithm Flow Diagram

```
START
  │
  ▼
Initialize Strategy
  │
  ▼
Check Available Funds
  │
  ▼
Start Monitoring Loop
  │
  ▼
Get NIFTY Spot Price
  │
  ▼
Calculate ATM Strike
  │
  ▼
Check Market Conditions
  │
  ▼
Analyze OI Data (if enabled)
  │
  ▼
┌─────────────────────────────────┐
│     Decision Making Logic       │
│                                 │
│  No Positions? ──► Enter Trade  │
│       │                         │
│       ▼                         │
│  Has Positions? ──► Manage      │
│       │                         │
│       ▼                         │
│  Check Scaling? ──► Scale Up    │
│       │                         │
│       ▼                         │
│  Check Exit? ──► Close Position │
└─────────────────────────────────┘
  │
  ▼
Execute Orders (if needed)
  │
  ▼
Update Position Tracking
  │
  ▼
Sleep 15 seconds
  │
  ▼
Market Close? ──► YES ──► END
  │
  ▼
  NO
  │
  ▼
Continue Loop
```

---

## Key Success Factors

### 1. Market Conditions
- **Range-bound Markets**: Strategy performs best in sideways markets
- **Moderate Volatility**: High volatility increases risk
- **Time Decay**: Benefits from theta decay throughout the day

### 2. Risk Management
- **Strict Stop Losses**: Prevents large losses
- **Position Sizing**: Appropriate lot sizes
- **Margin Management**: Ensures sufficient funds

### 3. Timing
- **Market Hours**: Optimal execution during active hours
- **Entry Timing**: Avoids volatile opening/closing periods
- **Exit Timing**: Timely position closure

### 4. Monitoring
- **Real-time Tracking**: Continuous position monitoring
- **Alert Systems**: Immediate notification of issues
- **Performance Analysis**: Regular strategy evaluation

---

## Conclusion

The Short Straddle Strategy is a sophisticated algorithmic trading system that combines:
- **Technical Analysis**: Price and ratio-based decisions
- **Fundamental Analysis**: OI and market sentiment
- **Risk Management**: Comprehensive margin and position management
- **Automation**: Fully automated execution and monitoring

The strategy's success depends on proper configuration, effective risk management, and favorable market conditions. Regular monitoring and adjustment of parameters are essential for optimal performance.

---

## Multi-Strategy Framework

The trading system implements three distinct strategies that can operate simultaneously, each with its own logic, risk parameters, and market conditions. The strategies are designed to complement each other and maximize opportunities across different market scenarios.

### Strategy Selection Logic
```python
def select_strategy():
    if expiry_day_mode:
        # On expiry day, prioritize safe OTM opportunities
        if safe_otm_opportunities_exist():
            return "safe_otm"
    
    if oi_analysis_enabled:
        # Use OI analysis for strangle opportunities
        if strangle_opportunities_exist():
            return "strangle"
    
    # Default to straddle strategy
    return "straddle"
```

---

## 12.1 Short Straddle Strategy

### Overview
The **Short Straddle** is the primary strategy that sells both a Call Option (CE) and Put Option (PE) at the same strike price (ATM). This strategy profits when NIFTY remains range-bound and doesn't move significantly in either direction.

### Core Logic
```python
def short_straddle_logic():
    # Entry Conditions
    if (no_active_positions AND 
        market_conditions_favorable AND
        initial_ratio > 0.8 AND
        sufficient_margin_available):
        
        # Place short straddle
        place_short_straddle(atm_strike)
    
    # Management Logic
    if active_positions_exist:
        for position in positions:
            current_ratio = min(ce_price, pe_price) / max(ce_price, pe_price)
            
            if current_ratio < 0.5:
                # Square off losing side
                square_off_losing_side(position)
            elif position_profit >= profit_target:
                # Exit profitable position
                exit_position(position)
```

### Key Parameters
- **Profit Target**: ₹3,000 per position
- **Loss Limit**: ₹3,000 per position
- **Ratio Threshold**: 0.8 (80% entry), 0.5 (50% exit)
- **Max Positions**: 3 straddles
- **Lot Size**: 75 (NIFTY lot size)

### Entry Criteria
1. **Market Conditions**: Market must be open and stable
2. **ATM Strike**: Calculate current ATM strike from NIFTY spot
3. **Initial Ratio**: min(CE_price, PE_price) / max(CE_price, PE_price) > 0.8
4. **Margin Check**: Sufficient funds available
5. **No Active Positions**: Start with clean slate

### Position Management
1. **Ratio Monitoring**: Continuous monitoring of CE/PE price ratio
2. **Losing Side Management**: Square off the losing option when ratio < 0.6
3. **Profit Taking**: Exit when profit target reached
4. **Scaling**: Add positions when profitable and conditions favorable

### Risk Management
- **Stop Loss**: Maximum ₹3,000 loss per position
- **Position Limits**: Maximum 3 concurrent positions
- **Margin Monitoring**: Real-time margin utilization tracking
- **Time-based Exits**: Automatic exit at market close

---

## 12.2 Safe OTM Options Strategy

### Overview
The **Safe OTM Options** strategy is designed specifically for all NIFTY expiry days (weekly on Tuesdays and monthly on last Thursday) to capture "easy money" opportunities by selling Out-of-The-Money (OTM) options that are likely to expire worthless.

**⚠️ Important**: This strategy is **completely disabled** on non-expiry days. It only activates on NIFTY expiry days (Tuesdays for weekly, last Thursday for monthly).

### Strategy Activation Logic
```python
def _is_nifty_expiry_day():
    """
    Check if today is a NIFTY expiry day (weekly or monthly)
    """
    today = datetime.now()
    
    # NIFTY weekly options expire on Tuesdays, monthly on last Thursday
    if today.weekday() == 1:  # Tuesday is 1 (weekly expiry)
        return True
    elif today.weekday() == 3:  # Thursday is 3 (monthly expiry)
        # Check if it's the last Thursday of the month
        return today.date() == last_thursday.date()
    else:
        return False  # Not an expiry day - strategy DISABLED
```

### Core Logic
```python
def safe_otm_logic():
    # Only active on NIFTY expiry days (weekly on Tuesdays, monthly on last Thursday)
    if not is_nifty_expiry_day():
        return  # Strategy completely disabled on non-expiry days
    
    # Analyze OTM opportunities
    opportunities = analyze_safe_otm_opportunities()
    
    for opportunity in opportunities:
        if (opportunity['selling_score'] >= 70 AND
            distance_from_atm_within_range AND
            premium_within_range AND
            oi_change_significant):
            
            # Place safe OTM position
            place_safe_otm_position(opportunity)
```

### Key Parameters
- **Activation**: Only on NIFTY expiry days (weekly on Tuesdays, monthly on last Thursday)
- **Max Positions**: 5 OTM positions
- **Min Distance**: 2 strikes from ATM
- **Max Distance**: 5 strikes from ATM
- **Premium Range**: ₹5 - ₹50
- **Min Selling Score**: 70%

### Entry Criteria
1. **Expiry Day**: Must be a NIFTY expiry day (weekly on Tuesdays, monthly on last Thursday)
2. **Distance from ATM**: 2-5 strikes away from current ATM
3. **Premium Range**: ₹5 - ₹50 per option
4. **OI Change**: Significant OI movement (>5%)
5. **Selling Score**: Minimum 70% confidence score

### Selling Score Calculation
```python
def _calculate_otm_selling_score(strike, ltp, oi, prev_oi, oi_change, option_type, spot_price):
    score = 50  # Base score
    
    # Factor 1: Distance from ATM (farther = better for selling)
    if option_type == 'call':
        distance_points = strike - spot_price
    else:  # put
        distance_points = spot_price - strike
    
    distance_strikes = distance_points / 50
    if distance_strikes >= 3:  # 3+ strikes away
        score += 20
    elif distance_strikes >= 2:  # 2+ strikes away
        score += 10
    
    # Factor 2: OI Analysis
    if option_type == 'call':
        if oi_change < -10:  # OI unwinding (good for call sellers)
            score += 15
        elif oi_change > 10:  # OI building (bad for call sellers)
            score -= 10
    else:  # put
        if oi_change < -10:  # OI unwinding (good for put sellers)
            score += 15
        elif oi_change > 10:  # OI building (bad for put sellers)
            score -= 10
    
    # Factor 3: Premium level (lower premium = better for selling)
    if ltp <= 10:
        score += 15
    elif ltp <= 15:
        score += 10
    elif ltp <= 20:
        score += 5
    elif ltp > 25:
        score -= 10
    
    # Factor 4: Time decay advantage (NIFTY expiry day)
    if self._is_nifty_expiry_day():
        score += 10  # Bonus for NIFTY expiry day
    
    # Factor 5: Risk-reward ratio
    risk_reward = self._calculate_risk_reward_ratio(ltp, strike, spot_price, option_type)
    if risk_reward >= 3:  # 1:3 risk-reward
        score += 10
    elif risk_reward >= 2:  # 1:2 risk-reward
        score += 5
    
    return max(0, min(100, score))  # Clamp between 0-100
```

### Scoring Factors Breakdown

#### **Factor 1: Distance from ATM (0-20 points)**
- **3+ strikes away**: +20 points (optimal for selling)
- **2+ strikes away**: +10 points (good for selling)
- **<2 strikes away**: 0 points (too close to ATM)

#### **Factor 2: OI Analysis (0-15 points)**
- **OI Unwinding (<-10%)**: +15 points (favorable for sellers)
- **OI Building (>10%)**: -10 points (unfavorable for sellers)
- **Neutral OI (-10% to 10%)**: 0 points

#### **Factor 3: Premium Level (0-15 points)**
- **≤₹10**: +15 points (excellent for selling)
- **₹11-₹15**: +10 points (good for selling)
- **₹16-₹20**: +5 points (acceptable for selling)
- **>₹25**: -10 points (too expensive for selling)

#### **Factor 4: Time Decay Advantage (0-10 points)**
- **NIFTY Expiry Day**: +10 points (time decay bonus)
- **Non-Expiry Day**: Strategy is DISABLED (no trading)

#### **Factor 5: Risk-Reward Ratio (0-10 points)**
- **≥3:1 ratio**: +10 points (excellent risk-reward)
- **≥2:1 ratio**: +5 points (good risk-reward)
- **<2:1 ratio**: 0 points (poor risk-reward)

#### **Total Score Range: 0-100**
- **≥70**: Excellent selling opportunity
- **60-69**: Good selling opportunity
- **50-59**: Neutral opportunity
- **<50**: Poor selling opportunity

### Position Management
1. **Individual Tracking**: Each OTM position tracked separately
2. **Profit Targets**: ₹500-₹1,500 per position
3. **Time Decay**: Hold until expiry or profit target
4. **Risk Control**: Maximum 5 positions simultaneously

### Risk Management
- **Expiry Day Only**: Strategy only active on NIFTY expiry days (weekly on Tuesdays, monthly on last Thursday)
- **Position Limits**: Maximum 5 OTM positions
- **Premium Limits**: Strict premium range controls
- **Distance Limits**: OTM distance constraints

---

## 12.3 OI-Guided Strangle Strategy

### Overview
The **OI-Guided Strangle** strategy uses Open Interest analysis to identify optimal strike combinations for strangle positions. It sells a Call Option and Put Option at different strikes based on OI concentration and sentiment.

### Core Logic
```python
def oi_strangle_logic():
    if not oi_analysis_enabled:
        return
    
    # Get OI analysis
    strangle_analysis = get_strangle_analysis()
    
    if strangle_analysis['recommendation'] in ['strong_strangle', 'strangle']:
        # Place OI-guided strangle
        place_oi_guided_strangle(strangle_analysis)
    
    # Manage existing strangle positions
    manage_strangle_positions()
```

### Key Parameters
- **OI Analysis**: Enabled by default
- **Min OI Threshold**: 5% change
- **Significant OI**: 10% change
- **Max Positions**: 2 strangles
- **Confidence Levels**: 50%, 70%, 90%

### Entry Criteria
1. **OI Analysis**: Comprehensive OI analysis available
2. **Recommendation**: Strong/Good strangle recommendation
3. **Confidence**: Minimum 50% confidence
4. **No Active Strangles**: Maximum 2 concurrent strangles
5. **Margin Available**: Sufficient funds for strangle

### OI Analysis Framework
```python
def analyze_strangle_opportunities():
    # Get option chain with OI data
    option_chain = get_option_chain_atm()
    
    # Analyze CE options
    ce_analysis = analyze_call_options(option_chain)
    
    # Analyze PE options  
    pe_analysis = analyze_put_options(option_chain)
    
    # Find optimal strangle combinations
    strangle_combinations = find_strangle_combinations(ce_analysis, pe_analysis)
    
    # Rank by OI strength and premium
    ranked_strangles = rank_strangles(strangle_combinations)
    
    return {
        'recommendation': get_recommendation(ranked_strangles),
        'strangle_analysis': ranked_strangles,
        'confidence': calculate_confidence(ranked_strangles)
    }
```

### Strangle Selection Criteria
1. **OI Concentration**: High OI at selected strikes
2. **OI Changes**: Significant OI movements
3. **Premium Collection**: Adequate premium for risk
4. **Strike Distance**: Optimal distance between CE and PE
5. **Market Sentiment**: OI sentiment alignment

### Position Management
1. **OI Monitoring**: Continuous OI change tracking
2. **Dynamic Adjustment**: Adjust positions based on OI shifts
3. **Profit Targets**: ₹2,000-₹4,000 per strangle
4. **Risk Management**: Individual position limits

### Risk Management
- **OI-Based Exits**: Exit when OI conditions change
- **Position Limits**: Maximum 2 strangles
- **Confidence Thresholds**: Minimum confidence levels
- **Market Sentiment**: Exit on sentiment reversal

---

## Strategy Integration and Coordination

### Multi-Strategy Execution
```python
def execute_multi_strategy():
    # Check each strategy in priority order
    strategies = [
        ('safe_otm', check_safe_otm_opportunities),
        ('strangle', check_continuous_strangle_entry),
        ('straddle', check_straddle_opportunities)
    ]
    
    for strategy_name, check_function in strategies:
        if check_function():
            execute_strategy(strategy_name)
            break  # Execute only one strategy per cycle
```

### Strategy Priority
1. **Safe OTM** (NIFTY expiry days - weekly on Tuesdays, monthly on last Thursday)
2. **OI-Guided Strangle** (When OI analysis available)
3. **Short Straddle** (Default strategy)

### Resource Allocation
- **Margin Management**: Shared across all strategies
- **Position Limits**: Individual limits per strategy
- **Risk Budget**: Allocated across strategies
- **Monitoring**: Unified monitoring system

### Performance Tracking
```python
strategy_performance = {
    'straddle': {
        'positions': 0,
        'total_pnl': 0,
        'win_rate': 0,
        'avg_profit': 0
    },
    'safe_otm': {
        'positions': 0,
        'total_pnl': 0,
        'win_rate': 0,
        'avg_profit': 0
    },
    'strangle': {
        'positions': 0,
        'total_pnl': 0,
        'win_rate': 0,
        'avg_profit': 0
    }
}
```

---

## Strategy Selection Algorithm

### Decision Tree
```
Market Open?
├── Yes
│   ├── Expiry Day?
│   │   ├── Yes → Check Safe OTM Opportunities
│   │   │   ├── Good Opportunities? → Execute Safe OTM
│   │   │   └── No → Check Strangle Opportunities
│   │   └── No → Check Strangle Opportunities
│   │       ├── Good OI Analysis? → Execute Strangle
│   │       └── No → Check Straddle Opportunities
│   │           ├── Favorable Conditions? → Execute Straddle
│   │           └── No → Wait for Next Cycle
│   └── No → Wait for Market Open
└── No → Wait for Market Open
```

### Market Condition Adaptation
- **Range-bound Markets**: Favor Straddle strategy
- **High Volatility**: Favor Strangle strategy
- **NIFTY Expiry Days**: Prioritize Safe OTM strategy (weekly on Tuesdays, monthly on last Thursday)
- **OI Concentration**: Favor OI-guided strategies

---

## Configuration for Multi-Strategy

### Strategy-Specific Parameters
```python
strategy_config = {
    'straddle': {
        'enabled': True,
        'max_positions': 3,
        'profit_target': 3000,
        'ratio_threshold': 0.6
    },
    'safe_otm': {
        'enabled': True,
        'max_positions': 5,
        'expiry_day_only': True,  # Applies to NIFTY expiries (weekly on Tuesdays, monthly on last Thursday)
        'min_selling_score': 70
    },
    'strangle': {
        'enabled': True,
        'max_positions': 2,
        'oi_analysis_required': True,
        'min_confidence': 50
    }
}
```

### Global Parameters
```python
global_config = {
    'max_total_positions': 8,
    'margin_utilization_limit': 80,
    'strategy_priority': ['safe_otm', 'strangle', 'straddle'],
    'execution_mode': 'sequential'  # or 'parallel'
}
```

---

*This documentation provides a complete overview of all three strategies implemented in the trading system. Each strategy has its own logic, risk parameters, and market conditions, but they work together as a unified multi-strategy framework to maximize trading opportunities across different market scenarios.*
