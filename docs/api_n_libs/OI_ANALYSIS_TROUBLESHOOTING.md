# OI Analysis Troubleshooting Guide

## Issue: "No option chain data found" Error

### Problem Description
You're seeing "No option chain data found" errors when running the OI analysis. This indicates that the option chain API is not returning data.

### Root Causes
1. **Market Hours**: Option chain data might not be available outside market hours
2. **API Rate Limits**: Too many API calls causing rate limiting
3. **Invalid Parameters**: Wrong underlying key or expiry date format
4. **Network Issues**: Connectivity problems with Upstox API
5. **API Changes**: Upstox API might have changed or be temporarily unavailable

### Solutions

#### 1. Run Diagnostic Script
```bash
python debug_option_chain.py
```
This script will:
- Test different underlying key formats
- Test different expiry dates
- Check market hours
- Verify API connectivity
- Show detailed error messages

#### 2. Use Fallback Analysis
The system now automatically falls back to basic analysis when option chain API is not available:

```bash
python test_fallback_oi.py
```

#### 3. Check Market Hours
Option chain data is typically available during market hours (9:15 AM - 3:30 PM IST).

#### 4. Verify Access Token
Ensure your access token is valid and not expired:
```python
# Test basic API connectivity
from market_quotes import get_ltp_quote
quote = get_ltp_quote(access_token, "NSE_INDEX|Nifty 50")
```

#### 5. Test Different Underlying Keys
Try different formats:
- `"NSE_INDEX|Nifty 50"`
- `"NSE_INDEX|NIFTY 50"`
- `"NSE_INDEX|Nifty"`
- `"NSE_INDEX|NIFTY"`

#### 6. Test Different Expiry Dates
Option chain data might be available for different expiry dates:
- Current week Thursday
- Next week Thursday
- Monthly expiry

### Fallback Analysis Features

When option chain API is not available, the system provides:

#### Basic Market Sentiment
- NIFTY spot price analysis
- Simple trend calculation
- Market sentiment classification

#### Simplified Selling Recommendations
- Strike-based recommendations
- Risk level assessment
- Distance from ATM analysis
- Basic reasoning

#### Real-time Monitoring
- Price-based monitoring
- Trend analysis
- Risk assessment
- Alert system

### Usage Examples

#### With Fallback (Automatic)
```python
from oi_analysis import get_oi_sentiment_analysis

# This will automatically use fallback if option chain fails
sentiment = get_oi_sentiment_analysis(access_token)
```

#### Direct Fallback
```python
from oi_analysis_fallback import OIAnalysisFallback

fallback = OIAnalysisFallback(access_token)
recommendation = fallback.get_simplified_selling_recommendation(25300)
```

#### In Strategy
The strategy automatically handles fallback:
```python
# In straddle_strategy.py - this is already implemented
strategy = ShortStraddleStrategy(
    access_token=access_token,
    nse_data=nse_data,
    enable_oi_analysis=True  # Will use fallback if needed
)
```

### Expected Behavior

#### When Option Chain API Works
- Full OI analysis with detailed sentiment
- Real-time OI monitoring
- Advanced selling recommendations
- Detailed alerts and notifications

#### When Option Chain API Fails
- Basic market sentiment analysis
- Simplified selling recommendations
- Price-based monitoring
- Fallback alerts and notifications

### Monitoring and Alerts

The system provides different types of alerts:

#### Option Chain Alerts (When Available)
- OI change alerts (>20% change)
- Sentiment shift alerts
- Unusual activity alerts

#### Fallback Alerts (When Option Chain Unavailable)
- Price movement alerts
- Trend change alerts
- Risk level alerts

### Performance Considerations

#### API Rate Limits
- Option chain API: Limited calls per minute
- Fallback uses LTP API: More generous limits
- Strategy automatically reduces API calls when using fallback

#### Data Quality
- Option chain data: High quality, detailed
- Fallback data: Basic but reliable
- Both provide actionable insights for option selling

### Troubleshooting Steps

1. **Check Market Hours**
   ```python
   from datetime import datetime
   now = datetime.now()
   market_open = now.replace(hour=9, minute=15)
   market_close = now.replace(hour=15, minute=30)
   print(f"Market open: {market_open <= now <= market_close}")
   ```

2. **Test Basic API**
   ```python
   from market_quotes import get_ltp_quote
   quote = get_ltp_quote(access_token, "NSE_INDEX|Nifty 50")
   print(f"API working: {quote is not None}")
   ```

3. **Test Option Chain API**
   ```python
   from market_data import get_option_chain_atm
   df = get_option_chain_atm(access_token, "NSE_INDEX|Nifty 50", "2024-01-25")
   print(f"Option chain working: {not df.empty}")
   ```

4. **Use Fallback Analysis**
   ```python
   from oi_analysis_fallback import OIAnalysisFallback
   fallback = OIAnalysisFallback(access_token)
   result = fallback.get_fallback_monitoring_update()
   print(f"Fallback working: {'error' not in result}")
   ```

### Best Practices

1. **Always Enable OI Analysis**: The system handles fallback automatically
2. **Monitor Alerts**: Both main and fallback provide useful alerts
3. **Check Data Source**: Look for "data_source" field in results
4. **Use Recommendations**: Both systems provide selling recommendations
5. **Monitor Performance**: Fallback is faster but less detailed

### Support

If you continue to have issues:

1. Run the diagnostic script: `python debug_option_chain.py`
2. Test fallback functionality: `python test_fallback_oi.py`
3. Check Upstox API status
4. Verify your access token and permissions
5. Check network connectivity

The fallback system ensures your strategy continues to work even when the option chain API is unavailable, providing basic but useful OI analysis for option selling decisions.
