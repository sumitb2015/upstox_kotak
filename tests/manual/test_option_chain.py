from lib.core.authentication import check_existing_token
from lib.api.option_chain import (
    get_option_chain_dataframe, 
    filter_option_chain,
    print_option_chain_summary,
    get_atm_strike_from_chain,
    get_nearest_expiry
)


def main():
    print("🚀 Option Chain Data Fetcher Test\n")
    
    # Get access token
    try:
        if check_existing_token():
            with open("lib/core/accessToken.txt", "r") as file:
                access_token = file.read().strip()
        else:
            print("❌ No access token found. Please run main.py first.")
            return
    except Exception as e:
        print("❌ Authentication failed: {e}")
        return
    
    # Get nearest available expiry using Upstox API
    print("📡 Fetching available expiries from Upstox API...")
    expiry_date = get_nearest_expiry(access_token, "NSE_INDEX|Nifty 50")
    
    if not expiry_date:
        print("❌ Could not determine nearest expiry")
        return
    
    print(f"✅ Found nearest expiry: {expiry_date}\n")
    
    # Fetch option chain
    print("⏳ Fetching option chain from Upstox API...")
    df = get_option_chain_dataframe(
        access_token=access_token,
        instrument_key="NSE_INDEX|Nifty 50",
        expiry_date=expiry_date
    )
    
    if df is None or df.empty:
        print("❌ Failed to fetch option chain")
        return
    
    print(f"✅ Fetched {len(df)} strikes\n")
    
    # Display summary
    print_option_chain_summary(df, num_strikes=10)
    
    # Show some analysis examples
    print("\n" + "="*100)
    print("📊 ANALYSIS EXAMPLES")
    print("="*100)
    
    atm = get_atm_strike_from_chain(df)
    print(f"\n1. ATM Strike: {atm}")
    
    # High OI strikes
    print("\n2. Top 5 Strikes by Call OI:")
    top_ce_oi = df.nlargest(5, 'ce_oi')[['strike_price', 'ce_oi', 'ce_ltp', 'ce_delta']]
    print(top_ce_oi.to_string(index=False))
    
    print("\n3. Top 5 Strikes by Put OI:")
    top_pe_oi = df.nlargest(5, 'pe_oi')[['strike_price', 'pe_oi', 'pe_ltp', 'pe_delta']]
    print(top_pe_oi.to_string(index=False))
    
    # Filter examples
    print("\n4. Deep OTM Puts (Delta < 0.1):")
    otm_puts = filter_option_chain(df, option_type='PE', delta_max=0.1)
    if not otm_puts.empty:
        print(otm_puts[['strike_price', 'pe_ltp', 'pe_oi', 'pe_delta']].head().to_string(index=False))
    
    # Save to CSV
    csv_file = f"option_chain_{expiry_date}.csv"
    df.to_csv(csv_file, index=False)
    print(f"\n💾 Saved to: {csv_file}")
    
    print("\n" + "="*100)
    print("✅ Test Complete!")
    print("="*100)


if __name__ == "__main__":
    main()
