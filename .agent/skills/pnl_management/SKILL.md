---
name: PnL Management Skill
description: Robust logic for calculating Global PnL from Kotak Neo API, handling missing fields and LTP fetching nuances.
---

# PnL Management Skill

## 1. Context
The Kotak Neo API's `positions()` endpoint often returns data missing critical PnL fields (`realizedPnl`, `unrealizedPnl`). Additionally, fetching LTPs for open positions can be tricky due to response format variations (List vs Dict) and key naming (`ltp` vs `last_price`).

This skill provides a standardized, robust method to calculate the **Global PnL** of the account by manually computing it from trade data and live market prices.

## 2. Core Formula
The most reliable way to calculate PnL is:

$$ \text{PnL} = (\text{Total Sell Amount} - \text{Total Buy Amount}) + (\text{Net Quantity} \times \text{Current LTP}) $$

- **Total Sell Amount**: Sum of `sellAmt` and `cfSellAmt`
- **Total Buy Amount**: Sum of `buyAmt` and `cfBuyAmt`
- **Net Quantity**: `(flBuyQty + cfBuyQty) - (flSellQty + cfSellQty)`

## 3. Implementation Guide

### A. Dependencies
Ensure you have `kotak_api` accessible.

### B. Robust PnL Calculator Function

Use this reusable function in your strategies:

```python
import logging
logger = logging.getLogger("PnLManager")

def calculate_global_pnl(broker_client):
    """
    Calculates Global PnL manually from positions.
    Returns: (total_pnl, open_positions_list, is_valid)
    """
    try:
        positions_resp = broker_client.positions()
        
        if not positions_resp or not isinstance(positions_resp, dict):
            return 0.0, [], False

        data = positions_resp.get('data', [])
        if not data:
            return 0.0, [], True
        
        total_pnl = 0.0
        open_positions = []
        open_tokens = []
        
        # 1. Identify Open Positions & Collect Tokens
        for pos in data:
            # Calculate Net Qty
            fl_buy = float(pos.get('flBuyQty', 0))
            fl_sell = float(pos.get('flSellQty', 0))
            cf_buy = float(pos.get('cfBuyQty', 0))
            cf_sell = float(pos.get('cfSellQty', 0))
            
            net_qty = int((fl_buy + cf_buy) - (fl_sell + cf_sell))
            pos['netQty'] = net_qty
            
            if net_qty != 0:
                open_positions.append(pos)
                open_tokens.append({
                    "instrument_token": pos.get('tok'),
                    "exchange_segment": pos.get('exSeg', 'nse_fo')
                })
        
        # 2. Batch Fetch LTPs
        ltp_map = {}
        if open_tokens:
            try:
                # Accessing client directly for raw quotes
                quotes = broker_client.client.quotes(instrument_tokens=open_tokens, quote_type="ltp")
                
                # Handle List vs Dict response
                q_data = []
                if isinstance(quotes, list):
                    q_data = quotes
                elif isinstance(quotes, dict) and 'message' in quotes:
                    q_data = quotes['message']
                    
                for q in q_data:
                    tk = str(q.get('instrument_token', ''))
                    # Handle 'ltp' vs 'last_price'
                    lp = float(q.get('ltp', q.get('last_price', 0)))
                    ex_tk = str(q.get('exchange_token', ''))
                    
                    if tk: ltp_map[tk] = lp
                    if ex_tk: ltp_map[ex_tk] = lp
                    
            except Exception as e:
                logger.error(f"Failed to fetch LTPs: {e}")
                
        # 3. Calculate Final PnL
        is_valid = True
        for pos in data:
            buy_amt = float(pos.get('buyAmt', 0)) + float(pos.get('cfBuyAmt', 0))
            sell_amt = float(pos.get('sellAmt', 0)) + float(pos.get('cfSellAmt', 0))
            net_qty = pos['netQty']
            
            current_val = 0.0
            if net_qty != 0:
                tok = str(pos.get('tok'))
                ltp = ltp_map.get(tok, 0.0)
                
                if ltp == 0:
                    logger.warning(f"LTP 0 for {pos.get('trdSym')}. PnL potentially invalid.")
                    is_valid = False
                    
                current_val = net_qty * ltp
            
            pnl = (sell_amt - buy_amt) + current_val
            total_pnl += pnl
            
        return total_pnl, open_positions, is_valid

    except Exception as e:
        logger.error(f"PnL Calculation Error: {e}")
        return 0.0, [], False
```

## 4. Key Considerations
1.  **LTP = 0 Risk**: If the API fails to return a price, the logic will default LTP to 0. This causes massive artificial losses for Longs and gains for Shorts. **Always check `is_valid` flag.**
2.  **API Variations**: Kotak's `quotes` API sometimes returns a list and sometimes a dict. The code handles both.
3.  **Realized vs Unrealized**: This formula calculates the *Total* PnL (Realized + Unrealized) combined. It does not separate them.

## 5. Usage Example
```python
client = BrokerClient()
client.authenticate()

pnl, open_pos, valid = calculate_global_pnl(client)

if valid:
    print(f"Global PnL: {pnl}")
else:
    print("Data invalid, retrying...")
```
