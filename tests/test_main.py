"""
Main execution file for Upstox Algorithmic Trading System
"""

import time
import sys
import os

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.authentication import check_existing_token, perform_authentication, save_access_token
from lib.api.market_data import (
    download_nse_market_data, 
    get_market_holidays, 
    get_filtered_option_chain,
    get_option_chain_atm,
    fetch_historical_data
)
from lib.api.order_management import (
    get_order_book, get_order_summary, place_order, 
    cancel_order, cancel_multiple_orders, cancel_all_orders,
    get_trades_for_day, get_trades_summary, get_trades_by_symbol, get_trades_by_exchange
)
from lib.utils.brokerage_calculator import get_brokerage_details
from lib.api.market_quotes import get_full_market_quote, format_market_quote, extract_market_quote_data, get_ltp_quote, get_multiple_ltp_quotes, format_ltp_quote, get_ohlc_quote, get_multiple_ohlc_quotes, format_ohlc_quote, get_option_greek, get_multiple_option_greeks, format_option_greek
from lib.utils.instrument_utils import get_nifty_option_instrument_keys, get_instrument_key
from lib.utils.profit_loss import get_profit_loss_report, format_profit_loss_report, get_recent_profit_loss, analyze_profit_loss_trends, get_current_financial_year, get_valid_date_range_for_financial_year
from strategies.non_directional.legacy_straddle.live import run_short_straddle_strategy

def main():
    """Main function to handle authentication and market data operations"""
    # Check for existing token
    if check_existing_token():
        print("Using existing access token for market operations...")
    else:
        # Perform authentication
        try:
            access_token = perform_authentication()
            save_access_token(access_token)
            print("Authentication completed successfully!")
        except Exception as e:
            print(f"Authentication failed: {e}")
            raise
    
    # Download NSE market data once at initialization
    print("\n" + "="*50)
    print("Initializing NSE market data...")
    nse_data = download_nse_market_data()
    if nse_data is None:
        print("Failed to download NSE data. Exiting...")
        return
    
    print(f"NSE data loaded successfully with {len(nse_data)} instruments")
    
    # Example: Get instrument key for NIFTY 25300
    print("\n" + "="*50)
    instrument_key = get_instrument_key("NIFTY", 25300, nse_data)
    if instrument_key:
        print(f"Retrieved instrument key: {instrument_key}")
    
    # Load access token for API calls
    try:
        with open("lib/core/accessToken.txt", "r") as file:
            access_token = file.read().strip()
        
        # Get option chain data
        print("\n" + "="*50)
        print("Fetching option chain data...")
        
        # Example: Get filtered option chain for NIFTY
        option_chain = get_filtered_option_chain(
            access_token, 
            "NSE_INDEX|Nifty 50", 
            "2025-09-23",  # You can change this date
            strikes_above=5, 
            strikes_below=5
        )
        
        if not option_chain.empty:
            print(f"Option chain loaded with {len(option_chain)} options")
            print("\nFirst few rows:")
            print(option_chain.head())
        else:
            print("No option chain data available")
        
        # Example: Get ATM option chain
        print("\n" + "="*50)
        print("Fetching ATM option chain...")
        atm_option_chain = get_option_chain_atm(
            access_token,
            "NSE_INDEX|Nifty 50",
            "2025-09-23",  # You can change this date
            strikes_above=5,
            strikes_below=5
        )
        
        if not atm_option_chain.empty:
            print(f"ATM option chain loaded with {len(atm_option_chain)} options")
            print("\nFirst few rows:")
            print(atm_option_chain.head(20))
        else:
            print("No ATM option chain data available")
        
        # Fetch historical data
        print("\n" + "="*50)
        print("Fetching historical data...")
        
        # Example: Fetch 5-minute NIFTY data for a specific date
        historical_data = fetch_historical_data(
            access_token,
            "NSE_INDEX|Nifty 50",
            "minutes",
            5,
            "2025-09-19",  # You can change this date
            "2025-09-19"   # You can change this date
        )
        
        if not historical_data.empty:
            print(f"Historical data loaded with {len(historical_data)} candles")
            print("\nFirst few rows:")
            print(historical_data.head(10))
            print(f"\nData range: {historical_data['timestamp'].min()} to {historical_data['timestamp'].max()}")
        else:
            print("No historical data available")
        
        # Fetch order book
        print("\n" + "="*50)
        print("Fetching order book...")
        
        # Get full order book
        order_book = get_order_book(access_token)
        if not order_book.empty:
            print(f"Order book loaded with {len(order_book)} orders")
            print("\nOrder book summary:")
            print(f"Total orders: {len(order_book)}")
            print(f"Status distribution:")
            print(order_book['status'].value_counts())
            
            # Show recent orders
            if 'order_timestamp' in order_book.columns:
                recent_orders = order_book.nlargest(5, 'order_timestamp')
                print("\nMost recent orders:")
                for _, order in recent_orders.iterrows():
                    print(f"Order ID: {order['order_id']}, Symbol: {order['trading_symbol']}, "
                          f"Type: {order['transaction_type']}, Status: {order['status']}, "
                          f"Qty: {order['quantity']}, Price: {order['price']}")
        else:
            print("No orders found in order book")
        
        # Get order summary
        print("\n" + "="*50)
        print("Fetching order summary...")
        order_summary = get_order_summary(access_token)
        if not order_summary.empty:
            print(f"Order summary loaded with {len(order_summary)} orders")
            print("\nOrder summary (first 10 rows):")
            print(order_summary.head(10))
        else:
            print("No order summary available")
        
        # Get trades for the day
        print("\n" + "="*50)
        print("Fetching trades for the day...")
        trades = get_trades_for_day(access_token)
        if not trades.empty:
            print(f"Trades loaded with {len(trades)} executed trades")
            print("\nTrades data (first 10 rows):")
            print(trades.head(10))
            
            # Show trade statistics
            print(f"\nTrade Statistics:")
            print(f"Total trades: {len(trades)}")
            print(f"Buy trades: {len(trades[trades['transaction_type'] == 'BUY'])}")
            print(f"Sell trades: {len(trades[trades['transaction_type'] == 'SELL'])}")
            print(f"Symbols traded: {trades['trading_symbol'].nunique()}")
            print(f"Exchanges: {trades['exchange'].unique().tolist()}")
        else:
            print("No trades found for today")
        
        # Get trades summary
        print("\n" + "="*50)
        print("Generating trades summary...")
        trades_summary = get_trades_summary(access_token)
        if trades_summary['total_trades'] > 0:
            print(f"Trades Summary:")
            print(f"Total trades: {trades_summary['total_trades']}")
            print(f"Total quantity: {trades_summary['total_quantity']}")
            print(f"Total value: ₹{trades_summary['total_value']:,.2f}")
            print(f"Buy trades: {trades_summary['buy_trades']}")
            print(f"Sell trades: {trades_summary['sell_trades']}")
            print(f"Symbols traded: {trades_summary['symbols_traded']}")
            print(f"Exchanges: {trades_summary['exchanges']}")
            
            print("\nTrades by Symbol and Type:")
            print(trades_summary['summary_df'])
        else:
            print("No trades summary available")
        
        # Example: Get trades by specific symbol
        print("\n" + "="*50)
        print("Fetching trades by symbol example...")
        # This will only work if you have trades for this symbol
        symbol_trades = get_trades_by_symbol(access_token, "NIFTY")
        if not symbol_trades.empty:
            print(f"Found {len(symbol_trades)} trades for NIFTY")
            print(symbol_trades[['trading_symbol', 'transaction_type', 'quantity', 'average_price', 'exchange_timestamp']])
        else:
            print("No trades found for NIFTY symbol")
        
        # Example: Get trades by exchange
        print("\n" + "="*50)
        print("Fetching trades by exchange example...")
        nse_trades = get_trades_by_exchange(access_token, "NSE")
        if not nse_trades.empty:
            print(f"Found {len(nse_trades)} trades on NSE")
            print(nse_trades[['trading_symbol', 'transaction_type', 'quantity', 'average_price']].head())
        else:
            print("No NSE trades found")
        
        # Test brokerage calculator
        print("\n" + "="*50)
        print("Testing Brokerage Calculator...")
        
        # Example parameters for brokerage calculation
        instrument_token = instrument_key
        quantity = 10
        product = "D"
        transaction_type = "BUY"
        price = 1400
        
        # Get brokerage details
        brokerage_data = get_brokerage_details(
            access_token=access_token,
            instrument_token=instrument_token,
            quantity=quantity,
            product=product,
            transaction_type=transaction_type,
            price=price
        )
        
        if brokerage_data and brokerage_data.get('status') == 'success':
            print("Brokerage calculation successful!")
            charges = brokerage_data['data']['charges']
            print(f"Total Charges: ₹{charges['total']:.2f}")
            print(f"Brokerage: ₹{charges['brokerage']:.2f}")
            print(f"GST: ₹{charges['taxes']['gst']:.2f}")
            print(f"STT: ₹{charges['taxes']['stt']:.2f}")
            print(f"Stamp Duty: ₹{charges['taxes']['stamp_duty']:.2f}")
            print(f"Transaction Charges: ₹{charges['other_charges']['transaction']:.2f}")
            if 'dp_plan' in charges and charges['dp_plan'] is not None:
                print(f"DP Plan: {charges['dp_plan']['name']}")
                print(f"Min Expense: ₹{charges['dp_plan']['min_expense']:.2f}")
            else:
                print("DP Plan: Not available")
        else:
            print("Brokerage calculation failed or returned error")
            if brokerage_data:
                print(f"Response: {brokerage_data}")
        
        # Test full market quotes
        print("\n" + "="*50)
        print("Testing Full Market Quotes...")
        
        # Example symbol for market quote
        quote_symbol = "NSE_FO|47762"  # You can change this to any valid symbol
        
        # Get full market quote
        quote_data = get_full_market_quote(access_token, quote_symbol)
        
        if quote_data:
            print("Market quote data retrieved successfully!")
            # Format and display the quote data
            formatted_data = format_market_quote(quote_data)
            
            # Example: Use the data for computation
            if formatted_data:
                print("\n" + "="*50)
                print("COMPUTATION EXAMPLES")
                print("="*50)
                
                for symbol_key, data in formatted_data.items():
                    # Example calculations
                    last_price = data['last_price']
                    volume = data['volume']
                    oi = data['oi']
                    
                    print(f"\nComputations for {data['symbol']}:")
                    print(f"  Price-Volume Ratio: {volume/last_price if last_price > 0 else 0:.2f}")
                    print(f"  OI Change: {data['oi_day_high'] - data['oi_day_low']:,}")
                    
                    # Market depth analysis
                    if data['depth'] and data['depth']['buy'] and data['depth']['sell']:
                        best_buy = data['depth']['buy'][0]['price']
                        best_sell = data['depth']['sell'][0]['price']
                        spread = best_sell - best_buy
                        spread_percentage = (spread / last_price) * 100 if last_price > 0 else 0
                        
                        print(f"  Bid-Ask Spread: ₹{spread:.2f} ({spread_percentage:.2f}%)")
                        print(f"  Best Bid: ₹{best_buy:.2f}")
                        print(f"  Best Ask: ₹{best_sell:.2f}")
                    
                    # OHLC analysis
                    if data['ohlc']:
                        ohlc = data['ohlc']
                        daily_range = ohlc['high'] - ohlc['low']
                        range_percentage = (daily_range / ohlc['open']) * 100 if ohlc['open'] > 0 else 0
                        
                        print(f"  Daily Range: ₹{daily_range:.2f} ({range_percentage:.2f}%)")
                        print(f"  Close vs Open: {((ohlc['close'] - ohlc['open']) / ohlc['open']) * 100 if ohlc['open'] > 0 else 0:.2f}%")
        else:
            print("Failed to get market quote data")
        
        # Test LTP quotes
        print("\n" + "="*50)
        print("Testing LTP (Last Traded Price) Quotes...")
        
        # Example instrument key for LTP
        ltp_instrument = "NSE_EQ|INE848E01016"  # You can change this to any valid instrument key
        
        # Get single LTP quote
        ltp_data = get_ltp_quote(access_token, ltp_instrument)
        
        if ltp_data:
            print("LTP data retrieved successfully!")
            # Format and display the LTP data
            formatted_ltp = format_ltp_quote(ltp_data)
            
            # Example computation with LTP data
            if formatted_ltp:
                print("\nLTP Computation Examples:")
                for key, data in formatted_ltp.items():
                    price = data['last_price']
                    volume = data['volume']
                    ltq = data['ltq']
                    cp = data['cp']
                    
                    print(f"  {key}: ₹{price:.2f}")
                    print(f"    Volume: {volume:,}")
                    print(f"    Last Traded Qty: {ltq:,}")
                    print(f"    Change: {cp:.2f}%")
                    
                    # Example calculations
                    if volume > 0:
                        avg_trade_size = volume / ltq if ltq > 0 else 0
                        print(f"    Avg Trade Size: {avg_trade_size:.2f}")
                    
                    # Example: You can use this data for calculations
                    # portfolio_value = price * quantity
                    # price_change = current_price - previous_price
                    # volume_weighted_price = (price * volume) / total_volume
        else:
            print("Failed to get LTP data")
        
        # Test multiple LTP quotes
        print("\n" + "="*50)
        print("Testing Multiple LTP Quotes...")
        
        # Example multiple instruments
        multiple_instruments = [
            "NSE_EQ|INE848E01016",  # Example stock 1
            "NSE_EQ|INE002A01018",  # Example stock 2
            "NSE_EQ|INE467B01029"   # Example stock 3
        ]
        
        multiple_ltp = get_multiple_ltp_quotes(access_token, multiple_instruments)
        
        if multiple_ltp:
            print("Multiple LTP data retrieved successfully!")
            # Format and display multiple LTP data
            formatted_multiple_ltp = format_ltp_quote(multiple_ltp)
            
            # Example: Portfolio value calculation
            if formatted_multiple_ltp:
                print("\nPortfolio Value Example:")
                total_value = 0
                total_volume = 0
                total_change = 0
                count = 0
                
                for key, data in formatted_multiple_ltp.items():
                    price = data['last_price']
                    volume = data['volume']
                    cp = data['cp']
                    
                    # Assuming 10 shares of each stock
                    quantity = 10
                    value = price * quantity
                    total_value += value
                    total_volume += volume
                    total_change += cp
                    count += 1
                    
                    print(f"  {key}: ₹{price:.2f} × {quantity} = ₹{value:.2f}")
                    print(f"    Volume: {volume:,}, Change: {cp:.2f}%")
                
                avg_change = total_change / count if count > 0 else 0
                print(f"  Total Portfolio Value: ₹{total_value:.2f}")
                print(f"  Total Volume: {total_volume:,}")
                print(f"  Average Change: {avg_change:.2f}%")
        else:
            print("Failed to get multiple LTP data")
        
        # Test OHLC quotes
        print("\n" + "="*50)
        print("Testing OHLC (Open, High, Low, Close) Quotes...")
        
        # Example instrument key for OHLC
        ohlc_instrument = "NSE_EQ|INE669E01016"  # You can change this to any valid instrument key
        
        # Get single OHLC quote
        ohlc_data = get_ohlc_quote(access_token, ohlc_instrument, "1d")
        
        if ohlc_data:
            print("OHLC data retrieved successfully!")
            # Format and display the OHLC data
            formatted_ohlc = format_ohlc_quote(ohlc_data)
            
            # Example computation with OHLC data
            if formatted_ohlc:
                print("\nOHLC Computation Examples:")
                for key, data in formatted_ohlc.items():
                    print(f"\n{key}:")
                    
                    # Previous OHLC calculations
                    if data['prev_ohlc']:
                        prev = data['prev_ohlc']
                        prev_range = prev.get('high', 0) - prev.get('low', 0)
                        prev_change = ((prev.get('close', 0) - prev.get('open', 0)) / prev.get('open', 1)) * 100
                        print(f"  Previous Day Range: ₹{prev_range:.2f}")
                        print(f"  Previous Day Change: {prev_change:.2f}%")
                        print(f"  Previous Volume: {prev.get('volume', 0):,}")
                    
                    # Live OHLC calculations
                    if data['live_ohlc']:
                        live = data['live_ohlc']
                        live_range = live.get('high', 0) - live.get('low', 0)
                        live_change = ((live.get('close', 0) - live.get('open', 0)) / live.get('open', 1)) * 100
                        print(f"  Live Range: ₹{live_range:.2f}")
                        print(f"  Live Change: {live_change:.2f}%")
                        print(f"  Live Volume: {live.get('volume', 0):,}")
                        
                        # Technical analysis examples
                        if live.get('high', 0) > 0 and live.get('low', 0) > 0:
                            body_size = abs(live.get('close', 0) - live.get('open', 0))
                            total_range = live.get('high', 0) - live.get('low', 0)
                            body_ratio = (body_size / total_range) * 100 if total_range > 0 else 0
                            print(f"  Body Size Ratio: {body_ratio:.2f}%")
        else:
            print("Failed to get OHLC data")
        
        # Test multiple OHLC quotes
        print("\n" + "="*50)
        print("Testing Multiple OHLC Quotes...")
        
        # Example multiple instruments for OHLC
        multiple_ohlc_instruments = [
            "NSE_EQ|INE669E01016",  # Example stock 1
            "NSE_EQ|INE848E01016"   # Example stock 2
        ]
        
        multiple_ohlc = get_multiple_ohlc_quotes(access_token, multiple_ohlc_instruments, "1d")
        
        if multiple_ohlc:
            print("Multiple OHLC data retrieved successfully!")
            # Format and display multiple OHLC data
            formatted_multiple_ohlc = format_ohlc_quote(multiple_ohlc)
            
            # Example: Portfolio OHLC analysis
            if formatted_multiple_ohlc:
                print("\nPortfolio OHLC Analysis:")
                total_prev_volume = 0
                total_live_volume = 0
                count = 0
                
                for key, data in formatted_multiple_ohlc.items():
                    print(f"\n{key}:")
                    
                    if data['prev_ohlc']:
                        prev_vol = data['prev_ohlc'].get('volume', 0)
                        total_prev_volume += prev_vol
                        print(f"  Previous Volume: {prev_vol:,}")
                    
                    if data['live_ohlc']:
                        live_vol = data['live_ohlc'].get('volume', 0)
                        total_live_volume += live_vol
                        print(f"  Live Volume: {live_vol:,}")
                    
                    count += 1
                
                print(f"\nPortfolio Summary:")
                print(f"  Total Previous Volume: {total_prev_volume:,}")
                print(f"  Total Live Volume: {total_live_volume:,}")
                print(f"  Volume Change: {((total_live_volume - total_prev_volume) / total_prev_volume * 100) if total_prev_volume > 0 else 0:.2f}%")
        else:
            print("Failed to get multiple OHLC data")
        
        # Test Option Greek fields
        print("\n" + "="*50)
        print("Testing Option Greek Fields...")
        
        # Get NIFTY CE instrument keys for 24900 and 25000 strikes
        print("Fetching NIFTY CE instrument keys...")
        nifty_ce_keys = get_nifty_option_instrument_keys(nse_data, [24900, 25000], "CE")
        
        if not nifty_ce_keys:
            print("Failed to get NIFTY CE instrument keys. Using fallback...")
            greek_instrument = "NSE_FO|43885"  # Fallback instrument key
        else:
            # Use the first available instrument key
            greek_instrument = list(nifty_ce_keys.values())[0]
            print(f"Using NIFTY CE instrument key: {greek_instrument}")
        
        # Get single Option Greek
        greek_data = get_option_greek(access_token, greek_instrument)
        
        if greek_data:
            print("Option Greek data retrieved successfully!")
            # Format and display the Option Greek data
            formatted_greek = format_option_greek(greek_data)
            
            # Example computation with Option Greek data
            if formatted_greek:
                print("\nOption Greek Computation Examples:")
                for key, data in formatted_greek.items():
                    print(f"\n{key}:")
                    
                    # Risk analysis
                    delta = data['delta']
                    gamma = data['gamma']
                    theta = data['theta']
                    vega = data['vega']
                    iv = data['iv']
                    
                    print(f"  Risk Analysis:")
                    print(f"    Delta Risk: {abs(delta):.4f} (Price sensitivity)")
                    print(f"    Gamma Risk: {gamma:.4f} (Delta change rate)")
                    print(f"    Theta Decay: {theta:.4f} (Time decay per day)")
                    print(f"    Vega Risk: {vega:.4f} (Volatility sensitivity)")
                    
                    # Option strategy analysis
                    if abs(delta) > 0.7:
                        print(f"    Strategy: High Delta - Directional play")
                    elif abs(delta) < 0.3:
                        print(f"    Strategy: Low Delta - Volatility play")
                    else:
                        print(f"    Strategy: Medium Delta - Balanced play")
                    
                    # Time decay analysis
                    if theta < -50:
                        print(f"    Time Decay: High - Consider short-term strategies")
                    elif theta > -10:
                        print(f"    Time Decay: Low - Suitable for longer-term holds")
                    else:
                        print(f"    Time Decay: Moderate")
                    
                    # Volatility analysis
                    if iv > 0.3:
                        print(f"    Volatility: High IV - Consider selling strategies")
                    elif iv < 0.15:
                        print(f"    Volatility: Low IV - Consider buying strategies")
                    else:
                        print(f"    Volatility: Moderate IV")
                    
                    # Advanced calculations
                    # Delta-adjusted position size
                    delta_exposure = abs(delta) * data['last_price']
                    print(f"    Delta Exposure: ₹{delta_exposure:.2f}")
                    
                    # Theta burn per day
                    theta_burn = theta * data['last_price']
                    print(f"    Theta Burn: ₹{theta_burn:.2f} per day")
        else:
            print("Failed to get Option Greek data")
        
        # Test multiple Option Greeks
        print("\n" + "="*50)
        print("Testing Multiple Option Greeks...")
        
        # Use the fetched NIFTY CE instrument keys
        if nifty_ce_keys:
            multiple_greek_instruments = list(nifty_ce_keys.values())
            print(f"Using NIFTY CE instrument keys: {multiple_greek_instruments}")
        else:
            # Fallback to example instrument keys
            multiple_greek_instruments = [
                "NSE_FO|43885",  # Example option 1
                "NSE_FO|43886"   # Example option 2
            ]
            print("Using fallback instrument keys")
        
        multiple_greeks = get_multiple_option_greeks(access_token, multiple_greek_instruments)
        
        if multiple_greeks:
            print("Multiple Option Greek data retrieved successfully!")
            # Format and display multiple Option Greek data
            formatted_multiple_greeks = format_option_greek(multiple_greeks)
            
            # Example: Portfolio Greek analysis
            if formatted_multiple_greeks:
                print("\nPortfolio Greek Analysis:")
                total_delta = 0
                total_gamma = 0
                total_theta = 0
                total_vega = 0
                total_iv = 0
                count = 0
                
                for key, data in formatted_multiple_greeks.items():
                    print(f"\n{key}:")
                    print(f"  Delta: {data['delta']:.4f}")
                    print(f"  Gamma: {data['gamma']:.4f}")
                    print(f"  Theta: {data['theta']:.4f}")
                    print(f"  Vega: {data['vega']:.4f}")
                    print(f"  IV: {data['iv']:.4f}")
                    
                    total_delta += data['delta']
                    total_gamma += data['gamma']
                    total_theta += data['theta']
                    total_vega += data['vega']
                    total_iv += data['iv']
                    count += 1
                
                avg_iv = total_iv / count if count > 0 else 0
                
                print(f"\nPortfolio Summary:")
                print(f"  Total Delta: {total_delta:.4f}")
                print(f"  Total Gamma: {total_gamma:.4f}")
                print(f"  Total Theta: {total_theta:.4f}")
                print(f"  Total Vega: {total_vega:.4f}")
                print(f"  Average IV: {avg_iv:.4f} ({avg_iv*100:.2f}%)")
                
                # Portfolio risk assessment
                if abs(total_delta) > 1:
                    print(f"  Risk: High directional exposure")
                elif abs(total_delta) < 0.5:
                    print(f"  Risk: Low directional exposure")
                else:
                    print(f"  Risk: Moderate directional exposure")
                
                # Portfolio strategy recommendation
                if total_theta < -100:
                    print(f"  Strategy: High time decay - Consider short-term strategies")
                elif total_theta > -20:
                    print(f"  Strategy: Low time decay - Suitable for longer-term holds")
                else:
                    print(f"  Strategy: Moderate time decay")
        else:
            print("Failed to get multiple Option Greek data")
        
        # Test Profit/Loss Report
        print("\n" + "="*50)
        print("Testing Profit/Loss Report...")
        
        # Get current financial year
        current_fy = get_current_financial_year()
        print(f"Current Financial Year: {current_fy}")
        
        # Get profit/loss for the last 30 days
        print("Getting recent profit/loss data (last 30 days)...")
        recent_pl = get_recent_profit_loss(access_token, days=30, segment="FO")
        
        if recent_pl:
            print("Recent profit/loss data retrieved successfully!")
            # Format and display the profit/loss data
            formatted_pl = format_profit_loss_report(recent_pl)
            
            # Analyze profit/loss trends
            if formatted_pl:
                print("\nProfit/Loss Analysis:")
                analysis = analyze_profit_loss_trends(formatted_pl)
                
                if analysis:
                    print(f"  Best Trade: {analysis['best_trade']['scrip_name']} - ₹{analysis['best_trade']['profit_loss']:,.2f}")
                    print(f"  Worst Trade: {analysis['worst_trade']['scrip_name']} - ₹{analysis['worst_trade']['profit_loss']:,.2f}")
                    
                    print(f"\n  Trade Types Analysis:")
                    for trade_type, data in analysis['trade_types'].items():
                        print(f"    {trade_type}: {data['count']} trades, P&L: ₹{data['total_pnl']:,.2f}")
                    
                    print(f"\n  Top Performing Scrips:")
                    sorted_scrips = sorted(analysis['scrips'].items(), key=lambda x: x[1]['total_pnl'], reverse=True)
                    for scrip, data in sorted_scrips[:3]:  # Top 3
                        print(f"    {scrip}: {data['count']} trades, P&L: ₹{data['total_pnl']:,.2f}")
        else:
            print("Failed to get recent profit/loss data")
        
        # Test specific date range profit/loss
        print("\n" + "="*50)
        print("Testing Specific Date Range Profit/Loss...")
        
        # Get profit/loss for a specific date range (example: last 3 months)
        # Use the current financial year and get valid date range
        from_date, to_date = get_valid_date_range_for_financial_year(current_fy, days=90)
        
        print(f"Getting profit/loss for date range: {from_date} to {to_date} in FY {current_fy}")
        
        specific_pl = get_profit_loss_report(
            access_token=access_token,
            from_date=from_date,
            to_date=to_date,
            segment="FO",
            financial_year=current_fy,
            page_number=1,
            page_size=20
        )
        
        if specific_pl:
            print("Specific date range profit/loss data retrieved successfully!")
            # Format and display
            formatted_specific_pl = format_profit_loss_report(specific_pl)
            
            # Show summary statistics
            if formatted_specific_pl and formatted_specific_pl['summary']:
                summary = formatted_specific_pl['summary']
                print(f"\nSummary Statistics:")
                print(f"  Total Trades: {summary['total_trades']}")
                print(f"  Total Buy Amount: ₹{summary['total_buy_amount']:,.2f}")
                print(f"  Total Sell Amount: ₹{summary['total_sell_amount']:,.2f}")
                print(f"  Net P&L: ₹{summary['total_profit_loss']:,.2f}")
                
                # Calculate return percentage
                if summary['total_buy_amount'] > 0:
                    return_pct = (summary['total_profit_loss'] / summary['total_buy_amount']) * 100
                    print(f"  Return Percentage: {return_pct:.2f}%")
        else:
            print("Failed to get specific date range profit/loss data")
        
        # Example: Order management demo (commented out for safety)
        print("\n" + "="*50)
        print("Order Management Demo (commented out for safety)")
        print("Uncomment the code below to place and manage actual orders")
        
        # # Example: Place a market buy order
        # sample_order = place_order(
        #     access_token=access_token,
        #     instrument_token=instrument_key,  # Example instrument token
        #     quantity=75,  # Small quantity for testing
        #     transaction_type="BUY",
        #     order_type="MARKET",
        #     product="D",
        #     validity="DAY",
        #     tag="test_order"
        # )
        # 
        # if sample_order:
        #     print("Sample order placed successfully!")
        #     order_id = sample_order.get("data", {}).get("order_ids", [None])[0]
        #     
        #     # Example: Cancel the order after a short delay
        #     if order_id:
        #         print(f"Order ID: {order_id}")
        #         print("Waiting 5 seconds before cancelling...")
        #         time.sleep(5)
        #         
        #         # Cancel the order
        #         cancel_result = cancel_order(access_token, order_id)
        #         if cancel_result:
        #             print("Order cancelled successfully!")
        #         else:
        #             print("Order cancellation failed!")
        # else:
        #     print("Sample order placement failed!")
        
        # # Example: Cancel all open orders
        # print("\nCancelling all open orders...")
        # cancel_results = cancel_all_orders(access_token)
        # print(f"Cancelled {len([r for r in cancel_results if r])} orders")
        
        # # Example: Cancel orders by specific status
        # print("\nCancelling trigger_pending orders...")
        # trigger_cancel_results = cancel_all_orders(access_token, "trigger_pending")
        # print(f"Cancelled {len([r for r in trigger_cancel_results if r])} trigger_pending orders")
        
        # Test Short Straddle Strategy
        print("\n" + "="*50)
        print("Testing Short Straddle Strategy...")
        print("WARNING: This will place real orders. Uncomment to run.")
        
        # Uncomment the following lines to run the actual strategy
        # print("Starting Short Straddle Strategy...")
        # run_short_straddle_strategy(access_token, nse_data)
        
        # For demo purposes, just show the strategy parameters
        print("Strategy Parameters:")
        print("  - Underlying: NIFTY")
        print("  - Strategy: Short Straddle")
        print("  - Initial Strike: ATM (25300)")
        print("  - Lot Size: 1 lot (75 qty)")
        print("  - Profit Target: ₹3000")
        print("  - Ratio Threshold: 0.6")
        print("  - Management: Square off losing side when ratio < 0.6")
        print("  - Move: 1 strike away from losing side")
        print("\nTo run the actual strategy, uncomment the run_short_straddle_strategy() call above.")
            
    except FileNotFoundError:
        print("Access token file not found. Cannot fetch API data.")
    
    # Get market holidays
    print("\n" + "="*50)
    holidays = get_market_holidays()
    if holidays is not None:
        print(f"Found {len(holidays)} market holidays")
    
    print("\n" + "="*50)
    print("All operations completed successfully!")

if __name__ == "__main__":
    main()
