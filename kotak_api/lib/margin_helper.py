"""
Margin Helper: Standardized functions for fund retrieval and margin calculation in Kotak Neo.
"""

import logging

logger = logging.getLogger(__name__)

def get_available_funds(client, deployment_pct=100.0):
    """
    Fetch live available funds from Kotak Neo and scale by deployment percentage.
    
    Args:
        client: Authenticated NeoAPI client.
        deployment_pct: Percentage of available funds allowed for deployment.
        
    Returns:
        tuple: (tradeable_funds, total_funds)
    """
    try:
        limits = client.limits()
        if limits and isinstance(limits, dict) and 'Net' in limits:
            # Clean and parse the 'Net' field (available margin)
            net_str = str(limits['Net']).replace(',', '')
            total_funds = float(net_str)
            tradeable_funds = total_funds * (deployment_pct / 100.0)
            
            logger.info(f"[CORE] Funds: Total ₹{total_funds:,.2f} | Tradeable ({deployment_pct}%) ₹{tradeable_funds:,.2f}")
            return tradeable_funds, total_funds
        else:
            logger.warning(f"[CORE] Could not parse Net limits from Neo API: {limits}")
    except Exception as e:
        logger.error(f"[CORE] Error fetching funds from Kotak Neo: {e}")
        
    return 0.0, 0.0


def check_margin_required(client, token, qty, transaction_type="S", product="NRML", exchange="nse_fo"):
    """
    Calculate exact margin needed for a specific instrument and quantity.
    
    Args:
        client: Authenticated NeoAPI client.
        token: Instrument token.
        qty: Order quantity.
        transaction_type: "B" (Buy) or "S" (Sell).
        product: Product type ("NRML", "MIS", etc.).
        exchange: Exchange segment ("nse_fo", "nse_cm").
        
    Returns:
        float: Total margin required.
    """
    try:
        resp = client.margin_required(
            exchange_segment=exchange,
            price="0", # Market order
            order_type="MKT",
            product=product,
            quantity=str(qty),
            instrument_token=str(token),
            transaction_type=transaction_type
        )
        
        if resp and 'data' in resp and 'total' in resp['data']:
            margin = float(resp['data']['total'])
            logger.info(f"[CORE] Margin Required for {token} (Qty {qty}, {transaction_type}): ₹{margin:,.2f}")
            return margin
        else:
            logger.warning(f"[CORE] Margin API response missing total: {resp}")
    except Exception as e:
        logger.error(f"[CORE] Margin API Error for token {token}: {e}")
    
    # Fallback estimation for Nifty Options Selling (approx 1.25L per lot as of early 2026)
    # 25 is Nifty lot size
    lots = abs(qty) // 25
    if lots == 0 and abs(qty) > 0: lots = 1 # Minimum 1 lot estimation
    
    fallback = lots * 125000.0
    logger.warning(f"[CORE] Using fallback margin estimation: ₹{fallback:,.2f}")
    return fallback



def check_straddle_margin(client, ce_token, ce_qty, pe_token, pe_qty, product="NRML"):
    """
    Calculate margin needed for a straddle (CE + PE short).
    Initially sums individual margins, but can be improved with margin benefit logic.
    """
    ce_margin = check_margin_required(client, ce_token, ce_qty, "S", product)
    pe_margin = check_margin_required(client, pe_token, pe_qty, "S", product)
    
    total = ce_margin + pe_margin
    logger.info(f"[CORE] Combined Straddle Margin (Heuristic Sum): ₹{total:,.2f}")
    return total

def is_sufficient_margin(client, token, qty, transaction_type="S", deployment_pct=100.0, product="NRML"):
    """
    Check if tradeable funds are sufficient for the required margin.
    
    Args:
        client: Authenticated NeoAPI client.
        token: Instrument token.
        qty: Order quantity.
        transaction_type: "B" or "S".
        deployment_pct: Max percentage of total funds to use.
        product: "NRML" or "MIS".
        
    Returns:
        bool: True if sufficient, False otherwise.
    """
    tradeable, total = get_available_funds(client, deployment_pct)
    required = check_margin_required(client, token, qty, transaction_type, product)
    
    if tradeable >= required:
        logger.info(f"[CORE] ✅ Margin Check Passed: Needed ₹{required:,.2f} | Tradeable ₹{tradeable:,.2f}")
        return True
    
    logger.warning(f"[CORE] ❌ Insufficient Margin: Needed ₹{required:,.2f} | Tradeable ₹{tradeable:,.2f} (Shortfall: ₹{required-tradeable:,.2f})")
    return False
