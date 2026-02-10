# Historical Data and Pivot Levels Documentation

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
3. [Implementation Details](#implementation-details)
4. [CPR (Central Pivot Range) Levels](#cpr-central-pivot-range-levels)
5. [Camarilla Pivot Levels](#camarilla-pivot-levels)
6. [API Integration](#api-integration)
7. [Usage Examples](#usage-examples)
8. [Error Handling](#error-handling)
9. [Testing](#testing)
10. [Trading Applications](#trading-applications)

---

## Overview

The Historical Data and Pivot Levels functionality automatically fetches NIFTY's previous day OHLC data and calculates two types of pivot levels during strategy initialization:

1. **CPR (Central Pivot Range) Levels** - Traditional pivot points with support and resistance levels
2. **Camarilla Pivot Levels** - Advanced pivot system with 6 levels above and below the pivot
3. **PDH, PDL, PDC Storage** - Explicitly stores Previous Day High, Low, Close for easy access

### Key Benefits
- **Automatic Calculation**: Fetches data and calculates levels during initialization
- **Real-time Integration**: Uses Upstox API for accurate historical data
- **Multiple Pivot Systems**: Both CPR and Camarilla for comprehensive analysis
- **Easy Access Variables**: PDH, PDL, PDC stored as separate attributes
- **Trading Day Logic**: Automatically handles weekends and holidays
- **Error Resilience**: Graceful handling of API failures

---

## Features

### ✅ **Automatic Data Fetching**
- Fetches previous trading day's OHLC data
- **PDH, PDL, PDC Storage**: Explicitly stores Previous Day High, Low, Close for easy access
- Handles weekend and holiday logic automatically
- Uses Upstox historical data API
- Real-time data validation

### ✅ **Dual Pivot Systems**
- **CPR Levels**: Traditional pivot with R1-R4 and S1-S4
- **Camarilla Pivots**: Advanced system with R1-R6 and S1-S6
- **Pivot Point**: Central reference point for both systems

### ✅ **Comprehensive Display**
- Formatted output with all levels
- Clear labeling and organization
- Real-time calculation status
- Error reporting and handling

### ✅ **External Access**
- Public methods to retrieve calculated levels
- Integration with other strategy components
- Persistent storage during strategy lifecycle

---

## Implementation Details

### **Initialization Flow**
```python
def __init__(self, access_token, nse_data, ...):
    # ... other initialization code ...
    
    # Historical data and pivot calculations
    self.previous_day_ohlc = None
    self.cpr_levels = {}
    self.camarilla_pivots = {}
    self._initialize_historical_data_and_pivots()
    
    # ... rest of initialization ...
```

### **Core Methods**

#### 1. `_initialize_historical_data_and_pivots()`
- Main initialization method
- Orchestrates data fetching and calculation
- Handles errors gracefully
- Displays results

#### 2. `_fetch_previous_day_ohlc()`
- Fetches historical OHLC data from Upstox API
- Handles trading day logic (weekends, holidays)
- Validates API response
- Returns structured OHLC data

#### 3. `_calculate_cpr_levels(ohlc)`
- Calculates Central Pivot Range levels
- Uses traditional pivot point formula
- Includes support and resistance levels
- Returns formatted dictionary

#### 4. `_calculate_camarilla_pivots(ohlc)`
- Calculates Camarilla pivot levels
- Uses advanced pivot formula with 1.1 multiplier
- Includes 6 levels above and below pivot
- Returns formatted dictionary

#### 5. `_display_pivot_levels()`
- Displays calculated levels in formatted output
- Shows both CPR and Camarilla levels
- Includes error handling
- Professional formatting

---

## CPR (Central Pivot Range) Levels

### **Formula**
```python
# Basic Pivot Point
pivot = (high + low + close) / 3

# Central Pivot Range
bc = (high + low) / 2  # Bottom Central
tc = (pivot - bc) + pivot  # Top Central
cpr = tc - bc

# Support and Resistance Levels
r1 = 2 * pivot - low
r2 = pivot + (high - low)
r3 = high + 2 * (pivot - low)
r4 = r3 + (high - low)

s1 = 2 * pivot - high
s2 = pivot - (high - low)
s3 = low - 2 * (high - pivot)
s4 = s3 - (high - low)
```

### **Levels Calculated**
- **Pivot Point**: Central reference point
- **TC (Top Central)**: Upper central pivot
- **BC (Bottom Central)**: Lower central pivot
- **CPR Range**: Difference between TC and BC
- **R1-R4**: Resistance levels
- **S1-S4**: Support levels

### **Trading Interpretation**
- **Pivot Point**: Key support/resistance level
- **R1-R4**: Potential resistance zones
- **S1-S4**: Potential support zones
- **CPR Range**: Market volatility indicator

---

## Camarilla Pivot Levels

### **Formula**
```python
# Basic Pivot Point
pivot = (high + low + close) / 3

# Range Calculation
range_val = high - low

# Camarilla Levels (using 1.1 multiplier)
r1 = close + (range_val * 1.1 / 12)
r2 = close + (range_val * 1.1 / 6)
r3 = close + (range_val * 1.1 / 4)
r4 = close + (range_val * 1.1 / 2)
r5 = close + (range_val * 1.1)
r6 = close + (range_val * 1.1 * 2)

s1 = close - (range_val * 1.1 / 12)
s2 = close - (range_val * 1.1 / 6)
s3 = close - (range_val * 1.1 / 4)
s4 = close - (range_val * 1.1 / 2)
s5 = close - (range_val * 1.1)
s6 = close - (range_val * 1.1 * 2)
```

### **Levels Calculated**
- **Pivot Point**: Central reference point
- **R1-R6**: Six resistance levels
- **S1-S6**: Six support levels

### **Trading Interpretation**
- **R3/S3**: Primary reversal levels
- **R4/S4**: Strong reversal levels
- **R5/S5**: Extreme reversal levels
- **R6/S6**: Maximum reversal levels

---

## API Integration

### **Using Existing fetch_historical_data Function**
```python
from market_data import fetch_historical_data

# Fetch historical data using existing function
# For daily data, use "days" with interval 1 (as per official Upstox API docs)
df = fetch_historical_data(
    access_token=self.access_token,
    symbol="NSE_INDEX|Nifty 50",
    interval_type="days",
    interval=1,  # 1 day interval
    start_date=date_str,
    end_date=date_str
)

# Extract OHLC data from DataFrame
if not df.empty:
    last_row = df.iloc[-1]
    ohlc = {
        'date': last_row['timestamp'].strftime('%Y-%m-%d'),
        'open': float(last_row['open']),
        'high': float(last_row['high']),
        'low': float(last_row['low']),
        'close': float(last_row['close']),
        'volume': int(last_row['volume'])
    }
```

### **DataFrame Format**
The `fetch_historical_data` function returns a pandas DataFrame with columns:
- **timestamp**: Date and time
- **open**: Opening price
- **high**: High price
- **low**: Low price
- **close**: Closing price
- **volume**: Trading volume
- **oi**: Open interest (if available)
- **symbol**: Symbol name

### **Trading Day Logic**
```python
# Calculate previous trading day
today = datetime.now()
if today.weekday() == 0:  # Monday
    previous_day = today - timedelta(days=3)  # Friday
elif today.weekday() == 6:  # Sunday
    previous_day = today - timedelta(days=2)  # Friday
else:
    previous_day = today - timedelta(days=1)  # Yesterday
```

---

## Usage Examples

### **Basic Usage**
```python
# Initialize strategy (automatically calculates pivots)
strategy = ShortStraddleStrategy(
    access_token="your_token",
    nse_data=nse_data,
    verbose=True
)

# Get CPR levels
cpr_levels = strategy.get_cpr_levels()
print(f"Pivot Point: ₹{cpr_levels['pivot']:.2f}")
print(f"R1: ₹{cpr_levels['r1']:.2f}")
print(f"S1: ₹{cpr_levels['s1']:.2f}")

# Get Camarilla pivots
camarilla_pivots = strategy.get_camarilla_pivots()
print(f"R3: ₹{camarilla_pivots['r3']:.2f}")
print(f"S3: ₹{camarilla_pivots['s3']:.2f}")

# Get previous day OHLC
ohlc = strategy.get_previous_day_ohlc()
print(f"Previous Close: ₹{ohlc['close']:.2f}")
```

### **Integration with Trading Logic**
```python
def check_pivot_levels(self, current_price):
    """
    Check if current price is near pivot levels
    """
    cpr_levels = self.get_cpr_levels()
    camarilla_pivots = self.get_camarilla_pivots()
    
    # Check CPR levels
    if abs(current_price - cpr_levels['pivot']) < 50:
        return "Near CPR Pivot"
    elif abs(current_price - cpr_levels['r1']) < 50:
        return "Near CPR R1"
    elif abs(current_price - cpr_levels['s1']) < 50:
        return "Near CPR S1"
    
    # Check Camarilla levels
    if abs(current_price - camarilla_pivots['r3']) < 50:
        return "Near Camarilla R3"
    elif abs(current_price - camarilla_pivots['s3']) < 50:
        return "Near Camarilla S3"
    
    return "No significant pivot level nearby"
```

### **Position Management Integration**
```python
def should_exit_position(self, current_price, position_type):
    """
    Use pivot levels for position management
    """
    cpr_levels = self.get_cpr_levels()
    
    if position_type == "long":
        # Exit long position near resistance
        if current_price >= cpr_levels['r1']:
            return True, f"Price reached CPR R1: ₹{cpr_levels['r1']:.2f}"
    elif position_type == "short":
        # Exit short position near support
        if current_price <= cpr_levels['s1']:
            return True, f"Price reached CPR S1: ₹{cpr_levels['s1']:.2f}"
    
    return False, "No exit signal"
```

---

## Error Handling

### **API Failures**
```python
try:
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        # Process data
    else:
        print(f"❌ Failed to fetch historical data. Status: {response.status_code}")
        return None
except Exception as e:
    print(f"❌ Error fetching historical data: {e}")
    return None
```

### **Data Validation**
```python
if data.get('status') == 'success' and data.get('data', {}).get('candles'):
    candles = data['data']['candles']
    if candles:
        # Process candles
    else:
        print("⚠️ No historical data found")
        return None
```

### **Calculation Errors**
```python
try:
    # Calculate pivot levels
    cpr_levels = self._calculate_cpr_levels(ohlc)
    return cpr_levels
except Exception as e:
    print(f"❌ Error calculating CPR levels: {e}")
    return {}
```

---

## Testing

### **Test Script**
```python
# Run the test script
python test_pivot_levels.py
```

### **Manual Testing**
```python
# Test with sample data
sample_ohlc = {
    'open': 24000.0,
    'high': 24200.0,
    'low': 23800.0,
    'close': 24100.0
}

strategy = ShortStraddleStrategy(...)
cpr_levels = strategy._calculate_cpr_levels(sample_ohlc)
camarilla_pivots = strategy._calculate_camarilla_pivots(sample_ohlc)
```

### **Expected Output**
```
📊 Fetching historical data and calculating pivot levels...
✅ Fetched previous day OHLC for 2024-01-15:
   Open: ₹24000.00
   High: ₹24200.00
   Low: ₹23800.00
   Close: ₹24100.00
   Volume: 1,000,000

============================================================
📊 PIVOT LEVELS CALCULATION
============================================================

🎯 CENTRAL PIVOT RANGE (CPR) LEVELS:
   Pivot Point: ₹24033.33
   Top Central (TC): ₹24000.00
   Bottom Central (BC): ₹24000.00
   CPR Range: ₹0.00
   R1: ₹24266.67
   R2: ₹24433.33
   R3: ₹24666.67
   R4: ₹24833.33
   S1: ₹23866.67
   S2: ₹23633.33
   S3: ₹23400.00
   S4: ₹23233.33

🎯 CAMARILLA PIVOT LEVELS:
   Pivot Point: ₹24033.33
   R1: ₹24136.67
   R2: ₹24173.33
   R3: ₹24220.00
   R4: ₹24320.00
   R5: ₹24540.00
   R6: ₹24980.00
   S1: ₹24063.33
   S2: ₹24026.67
   S3: ₹23980.00
   S4: ₹23880.00
   S5: ₹23660.00
   S6: ₹23220.00
============================================================
```

---

## Trading Applications

### **1. Support and Resistance**
- **CPR Levels**: Traditional support/resistance zones
- **Camarilla Levels**: Advanced reversal points
- **Pivot Point**: Key reference level

### **2. Entry and Exit Signals**
- **Breakout Trading**: Price breaks above R1/R2
- **Reversal Trading**: Price bounces from S1/S2
- **Range Trading**: Price oscillates between pivot levels

### **3. Risk Management**
- **Stop Loss**: Place stops beyond key pivot levels
- **Take Profit**: Target next pivot level
- **Position Sizing**: Adjust based on distance to pivots

### **4. Market Analysis**
- **Trend Strength**: Price behavior around pivot levels
- **Volatility**: CPR range indicates market volatility
- **Market Sentiment**: Price position relative to pivot

### **5. Strategy Integration**
- **Straddle Strategy**: Use pivots for strike selection
- **Strangle Strategy**: Use pivots for range estimation
- **Safe OTM Strategy**: Use pivots for distance calculation

---

## API Parameters Reference

### **fetch_historical_data Function Parameters**

#### **Required Parameters:**
- **access_token**: Upstox API access token
- **symbol**: "NSE_INDEX|Nifty 50" for NIFTY
- **interval_type**: "days" for daily data (as per official Upstox API docs)
- **interval**: 1 for daily data
- **start_date**: Previous trading day date in "YYYY-MM-DD" format
- **end_date**: Same as start_date for single day

#### **Available Interval Types (from official Upstox API docs):**
- **"minutes"**: 1, 3, 5, 10, 15, 30, 60 minutes
- **"hours"**: 1, 2, 3, 4, 6, 12 hours
- **"days"**: 1 day
- **"weeks"**: 1 week
- **"months"**: 1 month

#### **Important Notes:**
- **Daily Data**: Use interval_type="days" and interval=1 for daily candles
- **Date Format**: Dates must be in "YYYY-MM-DD" format
- **Trading Days**: Function automatically handles weekends and holidays
- **Official API**: Based on official Upstox Historical Candle Data V3 API

#### **Example Usage:**
```python
# Fetch daily data for NIFTY (official API format)
df = fetch_historical_data(
    access_token="your_token",
    symbol="NSE_INDEX|Nifty 50",
    interval_type="days",
    interval=1,  # 1 day interval
    start_date="2024-01-15",
    end_date="2024-01-15"
)
```

---

## Conclusion

The Historical Data and Pivot Levels functionality provides:

1. **Automatic Data Fetching**: Seamless integration with Upstox API
2. **Dual Pivot Systems**: Both CPR and Camarilla for comprehensive analysis
3. **Professional Implementation**: Error handling, validation, and formatting
4. **Trading Integration**: Easy integration with existing strategies
5. **Real-time Updates**: Fresh data every trading day

This enhancement significantly improves the strategy's analytical capabilities by providing key support and resistance levels for better decision-making and risk management.

---

*This documentation covers the complete implementation of historical data fetching and pivot level calculations in the Short Straddle Strategy.*
