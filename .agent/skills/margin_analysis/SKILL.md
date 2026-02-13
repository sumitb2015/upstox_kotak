---
name: Margin Analysis Skill
description: Instructions for checking available funds and calculating required margin before taking positions.
---

# Margin Analysis Skill

This skill provides instructions and standardized patterns for performing margin analysis across Upstox and Kotak Neo APIs. Checking for sufficient funds before order placement is critical to avoid exchange rejection and maintain strategy stability.

## 🤖 1. Kotak Neo (Primary Execution)

Kotak Neo is the primary broker for execution. Use the following methods from the `neo_api_client` (via `BrokerClient`).

### Fetch Available Funds
Use `client.limits()` to get accounts balance.
```python
def get_available_funds(client, deployment_pct=100.0):
    """Fetch live available funds and scale by deployment percentage."""
    try:
        limits = client.limits()
        if limits and isinstance(limits, dict) and 'Net' in limits:
            # The 'Net' field contains the available margin
            total_funds = float(limits['Net'].replace(',', ''))
            tradeable_funds = total_funds * (deployment_pct / 100.0)
            return tradeable_funds, total_funds
    except Exception as e:
        logger.error(f"Error fetching funds: {e}")
    return 0.0, 0.0
```

### Calculate Required Margin
Use `client.margin_required()` to get exact margin for a specific order.
```python
def check_margin_required(client, token, qty, transaction_type="S", product="NRML"):
    """Calculate exact margin needed from API."""
    try:
        # Note: transaction_type is "B" or "S"
        # Exchange segment "nse_fo" for Futures/Options
        resp = client.margin_required(
            exchange_segment="nse_fo", 
            price="0", 
            order_type="MKT", 
            product=product,
            quantity=str(qty), 
            instrument_token=str(token), 
            transaction_type=transaction_type
        )
        if resp and 'data' in resp and 'total' in resp['data']:
            return float(resp['data']['total'])
    except Exception as e:
        logger.error(f"Margin API Error: {e}")
    
    # Fallback estimation for Nifty Short (approx 1.25L per lot)
    return (qty // 25) * 125000.0 

def check_straddle_margin(client, ce_token, ce_qty, pe_token, pe_qty):
    """Calculate combined margin for Straddle/Strangle (Sum of legs)."""
    # Note: Kotak API doesn't support multi-leg margin check in one call efficiently via this endpoint 
    # unless using basket, so we sum individual legs for safety (Conservative Estimate).
    # Real exchange margin might be lower due to hedge benefit, but we check conservatively.
    ce_margin = check_margin_required(client, ce_token, ce_qty, "S")
    pe_margin = check_margin_required(client, pe_token, pe_qty, "S")
    return ce_margin + pe_margin
```

## 🤖 2. Upstox (Reference/Analytical)

Some strategies use Upstox for margin estimation if Kotak is not available or for cross-checking.

### Funds and Margin
```python
from lib.utils.funds_margin import get_funds_and_margin

funds_data = get_funds_and_margin(access_token, segment="SEC")
available = funds_data['data']['equity']['available_margin']
```

### Margin Calculator
```python
from lib.utils.margin_calculator import get_margin_details

instruments = [{"instrument_key": key, "quantity": qty, "transaction_type": "SELL", "product": "D"}]
margin_data = get_margin_details(access_token, instruments)
required = margin_data['data']['final_margin']
```

## 🛠️ Combined Validation Logic

Always wrap margin checks in a validation method before placing orders.

```python
def validate_margin(client, token, qty, side, deployment_pct=100.0):
    available, total = get_available_funds(client, deployment_pct)
    required = check_margin_required(client, token, qty, side)
    
    if available >= required:
        logger.info(f"✅ Margin Check Passed: Required ₹{required:,.2f} | Available ₹{available:,.2f}")
        return True
    else:
        logger.warning(f"❌ Insufficient Margin: Required ₹{required:,.2f} | Available ₹{available:,.2f}")
        return False
```

## 🔒 Safety Standards
- **Wait for Authentication**: Ensure `BrokerClient` is authenticated before calling limits.
- **Handle API Failures**: Provide sensible fallbacks if the Margin API is down.
- **Capping**: Always respect the `DEPLOYMENT_PCT` configured in the strategy.
