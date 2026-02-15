import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import argparse
from datetime import datetime, time
import upstox_client
from upstox_client.rest import ApiException

# Add project root
sys.path.append(os.path.abspath("c:/algo/upstox"))

from lib.api.market_data import get_ltp, download_nse_market_data
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy

def format_oi(x, pos):
    """Formatter for Y-axis to show commas."""
    return f'{int(x):,}'

def resolve_instrument(access_token, symbol, strike, opt_type, expiry_type, specific_expiry=None):
    """Resolve the Upstox instrument key for the given option parameters."""
    print(f"🔍 Resolving instrument: {symbol} {strike} {opt_type} ({expiry_type})...")
    
    # 1. Get Expiry
    if specific_expiry:
        expiry = specific_expiry
    else:
        expiry = get_expiry_for_strategy(access_token, expiry_type, symbol)
    
    if not expiry:
        print(f"❌ Could not resolve expiry for {symbol}")
        return None, None

    # 2. Download NSE market data for mapping
    nse_data = download_nse_market_data()
    
    # 3. Resolve Key
    instrument_key = get_option_instrument_key(symbol, strike, opt_type, nse_data, expiry)
    
    if not instrument_key:
        print(f"❌ Could not resolve instrument key for {symbol} {strike} {opt_type} {expiry}")
        return None, None
    
    return instrument_key, expiry

def fetch_oi_data(api_instance, instrument_key):
    """Fetch 1-minute intraday candles and extract timestamps and OI."""
    try:
        # api_version="2.0" is critical for non-zero OI on options
        api_response = api_instance.get_intra_day_candle_data(instrument_key, "1minute", "2.0")
        
        if api_response.status == 'success' and api_response.data.candles:
            candles = api_response.data.candles
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            # Convert to IST and make naive for matplotlib alignment
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
            return df[['timestamp', 'oi']]
        return pd.DataFrame()
    except ApiException as e:
        print(f"❌ API Error fetching OI: {e}")
        return pd.DataFrame()

def animate(i, api_instance, instruments, ax, lines, title_base):
    """Animation function for matplotlib."""
    for (strike, opt_type), data in instruments.items():
        instrument_key = data['key']
        line = lines[(strike, opt_type)]
        df = fetch_oi_data(api_instance, instrument_key)
        if not df.empty:
            df = df.sort_values('timestamp')
            line.set_data(df['timestamp'], df['oi'])
            
            # Update label in legend to show latest OI
            latest_oi = df['oi'].iloc[-1]
            line.set_label(f"{strike} {opt_type} | OI: {latest_oi:,}")
            
    # Relim and autoscale Y but keep X fixed to market hours
    ax.relim()
    ax.autoscale_view(scalex=False, scaley=True)
    ax.legend(loc='upper left', fontsize='small', ncol=2)
    
    ax.set_title(title_base)
    return list(lines.values())

def main():
    parser = argparse.ArgumentParser(description="Real-time OI Plotter for Upstox Options")
    parser.add_argument("--symbol", default="NIFTY", help="Underlying symbol (e.g., NIFTY, BANKNIFTY)")
    parser.add_argument("--strike", help="Strike price(s), comma-separated. If omitted, ATM CE/PE will be plotted.")
    parser.add_argument("--type", choices=["CE", "PE", "BOTH"], default="BOTH", help="Option type (CE, PE, or BOTH)")
    parser.add_argument("--expiry_type", choices=["current_week", "next_week", "monthly"], default="current_week", help="Expiry type")
    parser.add_argument("--expiry", help="Specific expiry date in YYYY-MM-DD format")
    
    args = parser.parse_args()

    # Help the user if no arguments are provided
    if len(sys.argv) == 1:
        print("\n📥 Interactive Mode: Please provide inputs (Press Enter for defaults)")
        args.symbol = input("   Enter Symbol (e.g. NIFTY, BANKNIFTY) [NIFTY]: ").strip().upper() or "NIFTY"
        try:
            strike_in = input(f"   Enter Strike(s) (comma-separated, Leave blank for ATM): ").strip()
            args.strike = strike_in if strike_in else None
        except ValueError:
            args.strike = None
        args.type = input("   Enter Type (CE/PE/BOTH) [BOTH]: ").strip().upper() or "BOTH"
        args.expiry = input("   Enter Expiry (YYYY-MM-DD) [Current]: ").strip() or None
        print("-" * 40)

    # 1. Get Access Token
    token_path = "c:/algo/upstox/lib/core/accessToken.txt"
    if not os.path.exists(token_path):
        print("❌ Access token file not found.")
        return
    with open(token_path, "r") as f:
        access_token = f.read().strip()

    # 2. Determine Strikes
    strikes = []
    if args.strike:
        strikes = [int(s.strip()) for s in args.strike.split(",")]
    else:
        print(f"📊 Strike not provided. Fetching ATM for {args.symbol}...")
        INDEX_MAP = {
            "NIFTY": "Nifty 50",
            "BANKNIFTY": "Nifty Bank",
            "FINNIFTY": "Nifty Fin Service"
        }
        symbol_name = INDEX_MAP.get(args.symbol.upper(), args.symbol)
        full_symbol = f"NSE_INDEX|{symbol_name}"
        spot = get_ltp(access_token, full_symbol)
        if spot:
            step = 100 if args.symbol.upper() == "BANKNIFTY" else 50
            atm = round(spot / step) * step
            strikes = [atm]
            print(f"🎯 Spot: {spot} | Resolved ATM: {atm}")
        else:
            print(f"❌ Could not fetch spot price for {full_symbol} to determine ATM.")
            return

    # 3. Resolve Instrument Keys
    types_to_plot = ["CE", "PE"] if args.type == "BOTH" else [args.type]
    instruments = {}
    for strike in strikes:
        for opt_type in types_to_plot:
            key, exp = resolve_instrument(access_token, args.symbol, strike, opt_type, args.expiry_type, args.expiry)
            if key:
                instruments[(strike, opt_type)] = {'key': key, 'expiry': exp}
            else:
                print(f"⚠️ Skipping {strike} {opt_type}")

    if not instruments:
        print("❌ No valid instruments resolved.")
        return

    # Use first valid expiry for title
    expiry = next(iter(instruments.values()))['expiry']
    print(f"🚀 Starting Real-time OI Plotter for {args.symbol} ({expiry})")
    print(f"💡 Tip: Provide multiple strikes (e.g. 25000,25100) or use --type BOTH")

    # 4. Setup Plot
    try:
        fig, ax = plt.subplots(figsize=(12, 7))
        lines = {}
        for (strike, opt_type) in instruments.keys():
            color = 'tab:green' if opt_type == 'CE' else 'tab:red'
            line, = ax.plot([], [], label=f'{strike} {opt_type}', linewidth=2, color=color if args.type == 'BOTH' and len(strikes) == 1 else None)
            lines[(strike, opt_type)] = line
        
        ax.set_xlabel("Time")
        ax.set_ylabel("Open Interest")
        ax.grid(True, linestyle='--', alpha=0.6)
        
        # Format X-axis for human readable time (9:15 AM - 3:30 PM)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%I:%M %p'))
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Set market hours limits (9:15 AM to 3:30 PM)
        today = datetime.now().date()
        mkt_start = datetime.combine(today, time(9, 15))
        mkt_end = datetime.combine(today, time(15, 30))
        ax.set_xlim(mkt_start, mkt_end)
        
        # Format Y-axis with commas
        ax.yaxis.set_major_formatter(FuncFormatter(format_oi))
        
        title_base = f"OI Trend: {args.symbol} ({expiry})"
        
        # 5. Initialize API
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        api_instance = upstox_client.HistoryApi(upstox_client.ApiClient(configuration))

        # Initial data fetch to populate the plot immediately
        animate(0, api_instance, instruments, ax, lines, title_base)

        # 6. Run Animation
        ani = animation.FuncAnimation(
            fig, animate, fargs=(api_instance, instruments, ax, lines, title_base),
            interval=60000, # Refresh every 60 seconds
            cache_frame_data=False
        )

        plt.tight_layout()
        plt.show()
    except Exception as e:
        print(f"❌ Plotting Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
