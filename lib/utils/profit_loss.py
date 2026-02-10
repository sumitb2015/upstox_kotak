import requests
from datetime import datetime, timedelta


def get_current_financial_year():
    """
    Get the current financial year in the format expected by Upstox API.
    
    Returns:
        str: Financial year in YYYY format (e.g., "2425" for 2024-25)
    """
    now = datetime.now()
    current_year = now.year
    
    # Financial year starts from April 1st
    if now.month >= 4:
        # Current year to next year
        fy_start = current_year
        fy_end = current_year + 1
    else:
        # Previous year to current year
        fy_start = current_year - 1
        fy_end = current_year
    
    # Format as YYYY (last 2 digits of start and end year)
    financial_year = f"{str(fy_start)[-2:]}{str(fy_end)[-2:]}"
    return financial_year


def get_valid_date_range_for_financial_year(financial_year, days=30):
    """
    Get a valid date range that falls within the specified financial year.
    
    Args:
        financial_year (str): Financial year in YYYY format (e.g., "2425")
        days (int): Number of days to look back
    
    Returns:
        tuple: (from_date, to_date) in DD-MM-YYYY format
    """
    # Parse financial year
    fy_start_str = "20" + financial_year[:2]  # e.g., "2425" -> "2024"
    fy_end_str = "20" + financial_year[2:]    # e.g., "2425" -> "2025"
    
    fy_start_year = int(fy_start_str)
    fy_end_year = int(fy_end_str)
    
    # Financial year starts from April 1st
    fy_start_date = datetime(fy_start_year, 4, 1)
    fy_end_date = datetime(fy_end_year, 3, 31)
    
    # Get current date
    now = datetime.now()
    
    # Ensure we don't go beyond the financial year
    end_date = min(now, fy_end_date)
    start_date = max(end_date - timedelta(days=days), fy_start_date)
    
    # Format dates
    from_date = start_date.strftime('%d-%m-%Y')
    to_date = end_date.strftime('%d-%m-%Y')
    
    return from_date, to_date


def get_profit_loss_report(access_token, from_date, to_date, segment="FO", financial_year="2324", page_number=1, page_size=10):
    """
    Get profit/loss report for futures and options segment.
    
    Args:
        access_token (str): The access token obtained from Token API
        from_date (str): Start date in DD-MM-YYYY format (e.g., '05-11-2023')
        to_date (str): End date in DD-MM-YYYY format (e.g., '19-12-2023')
        segment (str): Trading segment - 'FO' for Futures & Options, 'EQ' for Equity, 'CD' for Currency Derivatives
        financial_year (str): Financial year in YYYY format (e.g., '2324' for 2023-24)
        page_number (int): Page number for pagination
        page_size (int): Number of records per page
    
    Returns:
        dict: Profit/loss report data
    """
    url = 'https://api.upstox.com/v2/trade/profit-loss/data'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {
        'from_date': from_date,
        'to_date': to_date,
        'segment': segment,
        'financial_year': financial_year,
        'page_number': str(page_number),
        'page_size': str(page_size)
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error getting profit/loss report: {e}")
        return None


def format_profit_loss_report(pl_data):
    """
    Format and display profit/loss report data in a readable format.
    
    Args:
        pl_data (dict): Profit/loss data from get_profit_loss_report
    
    Returns:
        dict: Formatted profit/loss data for computation
    """
    if not pl_data or pl_data.get('status') != 'success':
        print("No profit/loss data available or request failed")
        return None
    
    print("\n" + "="*80)
    print("PROFIT/LOSS REPORT")
    print("="*80)
    
    data = pl_data.get('data', [])
    metadata = pl_data.get('metadata', {})
    
    if not data:
        print("No trades found in the specified date range")
        return None
    
    formatted_data = []
    total_profit_loss = 0
    total_buy_amount = 0
    total_sell_amount = 0
    
    print(f"\nFound {len(data)} trades:")
    print("-" * 80)
    
    for i, trade in enumerate(data, 1):
        # Extract trade data
        trade_info = {
            'trade_number': i,
            'quantity': trade.get('quantity', 0),
            'isin': trade.get('isin', 'N/A'),
            'scrip_name': trade.get('scrip_name', 'N/A'),
            'trade_type': trade.get('trade_type', 'N/A'),
            'buy_date': trade.get('buy_date', 'N/A'),
            'buy_average': trade.get('buy_average', 0),
            'sell_date': trade.get('sell_date', 'N/A'),
            'sell_average': trade.get('sell_average', 0),
            'buy_amount': trade.get('buy_amount', 0),
            'sell_amount': trade.get('sell_amount', 0)
        }
        
        # Calculate profit/loss for this trade
        profit_loss = trade_info['sell_amount'] - trade_info['buy_amount']
        trade_info['profit_loss'] = profit_loss
        
        formatted_data.append(trade_info)
        
        # Update totals
        total_buy_amount += trade_info['buy_amount']
        total_sell_amount += trade_info['sell_amount']
        total_profit_loss += profit_loss
        
        # Display trade details
        print(f"\nTrade #{i}: {trade_info['scrip_name']} ({trade_info['trade_type']})")
        print(f"  ISIN: {trade_info['isin']}")
        print(f"  Quantity: {trade_info['quantity']:,}")
        print(f"  Buy Date: {trade_info['buy_date']} | Buy Price: ₹{trade_info['buy_average']:.2f}")
        print(f"  Sell Date: {trade_info['sell_date']} | Sell Price: ₹{trade_info['sell_average']:.2f}")
        print(f"  Buy Amount: ₹{trade_info['buy_amount']:,.2f}")
        print(f"  Sell Amount: ₹{trade_info['sell_amount']:,.2f}")
        
        # Profit/Loss with color coding
        if profit_loss > 0:
            print(f"  Profit: +₹{profit_loss:,.2f} ✅")
        elif profit_loss < 0:
            print(f"  Loss: -₹{abs(profit_loss):,.2f} ❌")
        else:
            print(f"  Break-even: ₹{profit_loss:,.2f} ➖")
    
    # Display summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total Trades: {len(data)}")
    print(f"Total Buy Amount: ₹{total_buy_amount:,.2f}")
    print(f"Total Sell Amount: ₹{total_sell_amount:,.2f}")
    
    if total_profit_loss > 0:
        print(f"Total Profit: +₹{total_profit_loss:,.2f} ✅")
    elif total_profit_loss < 0:
        print(f"Total Loss: -₹{abs(total_profit_loss):,.2f} ❌")
    else:
        print(f"Total P&L: ₹{total_profit_loss:,.2f} ➖")
    
    # Display pagination info
    if metadata and 'page' in metadata:
        page_info = metadata['page']
        print(f"\nPage: {page_info.get('page_number', 1)} of {page_info.get('page_size', 10)} records per page")
    
    print("="*80)
    
    return {
        'trades': formatted_data,
        'summary': {
            'total_trades': len(data),
            'total_buy_amount': total_buy_amount,
            'total_sell_amount': total_sell_amount,
            'total_profit_loss': total_profit_loss
        },
        'metadata': metadata
    }


def get_recent_profit_loss(access_token, days=30, segment="FO", financial_year=None):
    """
    Get profit/loss report for the last N days.
    
    Args:
        access_token (str): The access token obtained from Token API
        days (int): Number of days to look back
        segment (str): Trading segment
        financial_year (str): Financial year (e.g., "2425" for 2024-25). If None, uses current FY.
    
    Returns:
        dict: Recent profit/loss data
    """
    # Use current financial year if not specified
    if financial_year is None:
        financial_year = get_current_financial_year()
    
    # Get valid date range for the financial year
    from_date, to_date = get_valid_date_range_for_financial_year(financial_year, days)
    
    print(f"Getting profit/loss for last {days} days ({from_date} to {to_date}) in FY {financial_year}")
    
    return get_profit_loss_report(access_token, from_date, to_date, segment, financial_year)


def analyze_profit_loss_trends(formatted_data):
    """
    Analyze profit/loss trends from formatted data.
    
    Args:
        formatted_data (dict): Formatted profit/loss data
    
    Returns:
        dict: Analysis results
    """
    if not formatted_data or 'trades' not in formatted_data:
        return None
    
    trades = formatted_data['trades']
    
    # Analyze by trade type
    trade_types = {}
    for trade in trades:
        trade_type = trade['trade_type']
        if trade_type not in trade_types:
            trade_types[trade_type] = {
                'count': 0,
                'total_pnl': 0,
                'trades': []
            }
        
        trade_types[trade_type]['count'] += 1
        trade_types[trade_type]['total_pnl'] += trade['profit_loss']
        trade_types[trade_type]['trades'].append(trade)
    
    # Analyze by scrip
    scrips = {}
    for trade in trades:
        scrip = trade['scrip_name']
        if scrip not in scrips:
            scrips[scrip] = {
                'count': 0,
                'total_pnl': 0,
                'trades': []
            }
        
        scrips[scrip]['count'] += 1
        scrips[scrip]['total_pnl'] += trade['profit_loss']
        scrips[scrip]['trades'].append(trade)
    
    # Find best and worst performers
    best_trade = max(trades, key=lambda x: x['profit_loss'])
    worst_trade = min(trades, key=lambda x: x['profit_loss'])
    
    analysis = {
        'trade_types': trade_types,
        'scrips': scrips,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'total_trades': len(trades)
    }
    
    return analysis


# Example usage
if __name__ == "__main__":
    # Read access token from file
    try:
        with open('lib/core/accessToken.txt', 'r') as file:
            access_token = file.read().strip()
    except FileNotFoundError:
        print("Error: accessToken.txt file not found")
        exit(1)
    
    # Example: Get profit/loss for specific date range
    current_fy = get_current_financial_year()
    from_date, to_date = get_valid_date_range_for_financial_year(current_fy, days=30)
    
    print(f"Getting Profit/Loss Report for FY {current_fy}...")
    pl_data = get_profit_loss_report(
        access_token=access_token,
        from_date=from_date,
        to_date=to_date,
        segment="FO",
        financial_year=current_fy,
        page_number=1,
        page_size=10
    )
    
    if pl_data:
        print("Raw API Response:")
        print(pl_data)
        
        # Format and display
        formatted_data = format_profit_loss_report(pl_data)
        
        # Analyze trends
        if formatted_data:
            print("\n" + "="*50)
            print("PROFIT/LOSS ANALYSIS")
            print("="*50)
            
            analysis = analyze_profit_loss_trends(formatted_data)
            if analysis:
                print(f"\nBest Trade: {analysis['best_trade']['scrip_name']} - ₹{analysis['best_trade']['profit_loss']:,.2f}")
                print(f"Worst Trade: {analysis['worst_trade']['scrip_name']} - ₹{analysis['worst_trade']['profit_loss']:,.2f}")
                
                print(f"\nTrade Types Analysis:")
                for trade_type, data in analysis['trade_types'].items():
                    print(f"  {trade_type}: {data['count']} trades, P&L: ₹{data['total_pnl']:,.2f}")
    else:
        print("Failed to get profit/loss data")
    
    # Example: Get recent profit/loss
    print("\n" + "="*50)
    print("RECENT PROFIT/LOSS (Last 30 days)")
    print("="*50)
    
    recent_pl = get_recent_profit_loss(access_token, days=30, segment="FO")
    if recent_pl:
        recent_formatted = format_profit_loss_report(recent_pl)
    else:
        print("Failed to get recent profit/loss data")
