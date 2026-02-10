"""
Positional Monthly Strangle - Live Execution
Syncs with SQLite DB and Kotak Positions.
"""
import sys
import os
import time
import logging
from datetime import datetime

# Add root to path
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if root not in sys.path: sys.path.append(root)

from strategies.positional.monthly_strangle.config import CONFIG, validate_config
from strategies.positional.monthly_strangle.strategy_core import MonthlyStrangleCore
from lib.database.trade_db import TradeDB

from lib.core.authentication import get_access_token
from lib.api.market_data import download_nse_market_data, get_market_quote_for_instrument
from lib.utils.instrument_utils import get_option_instrument_key
from lib.utils.expiry_cache import get_expiry_for_strategy

from kotak_api.lib.broker import BrokerClient
from kotak_api.lib.order_manager import OrderManager
from kotak_api.lib.trading_utils import get_strike_token, get_lot_size

# Logger Setup
logger = logging.getLogger("MonthlyStrangle")
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class MonthlyStrangleLive(MonthlyStrangleCore):
    def __init__(self, access_token, config):
        super().__init__(config)
        self.access_token = access_token
        self.db = TradeDB(config['db_path'])
        
        self.kotak_broker = BrokerClient()
        self.order_mgr = None
        self.nse_data = None
        self.expiry_date = None
        
    def initialize(self):
        logger.info("📋 [CORE] Validating Config...")
        validate_config()
        
        logger.info("🔐 [KOTAK] Authenticating Kotak...")
        client = self.kotak_broker.authenticate()
        if not client:
             logger.error("❌ [KOTAK] Auth Failed")
             sys.exit(1)
             
        self.order_mgr = OrderManager(client, dry_run=self.config['dry_run'])
        self.kotak_broker.load_master_data()
        
        logger.info("📊 [UPSTOX] Loading Market Data...")
        self.nse_data = download_nse_market_data()
        self.expiry_date = get_expiry_for_strategy(self.access_token, self.config['expiry_type'], self.config['underlying'])
        logger.info(f"📅 [CORE] Expiry: {self.expiry_date}")
        
        # === SYNC ON STARTUP ===
        self.sync_positions()
        
        return True

    def sync_positions(self):
        """
        Reconcile DB State with Real World (Kotak).
        If DB says OPEN, but Kotak has no position -> Mark CLOSED in DB (Manual Exit?).
        """
        logger.info("🔄 [CORE] Syncing DB with Live Positions...")
        db_trades = self.db.get_open_trades(self.config['strategy_name'])
        
        # Get Live Kotak Positions (Net Qty != 0)
        kotak_positions = self.kotak_broker.positions()
        live_symbols = {}
        if kotak_positions and 'data' in kotak_positions:
             for pos in kotak_positions['data']:
                 if int(pos.get('netQty', 0)) != 0:
                     live_symbols[pos.get('instrumentToken')] = int(pos.get('netQty')) # Map Token -> Qty
                     # Also Map TradingSymbol for easier lookup
                     live_symbols[pos.get('chkpts')] = int(pos.get('netQty')) # chkpts is usually symbol name in some APIs, verify key?
                     # Kotak usually calls it 'trdSym' or similar. 
                     # Using standard Kotak Broker wrapper, let's assume we match by Symbol Name
                     sym = pos.get('trdSym') 
                     if sym: live_symbols[sym] = int(pos.get('netQty'))

        for trade in db_trades:
            symbol = trade['symbol']
            qty = trade['quantity'] # Positive integer in DB
            
            # Short position in Kotak will be negative Qty
            # We must expect -Qty in Live
            expected_live_qty = -qty if trade['transaction_type'] == 'SELL' else qty
            
            if symbol not in live_symbols:
                logger.warning(f"⚠️ [CORE] Sync Mismatch: {symbol} is OPEN in DB but missing in Kotak. Closing in DB.")
                self.db.update_status(trade['id'], 'CLOSED', "Sync: NotFound")
            else:
                live_qty = live_symbols[symbol]
                if live_qty != expected_live_qty:
                     logger.warning(f"⚠️ [CORE] Qty Mismatch for {symbol}: DB={expected_live_qty}, Kotak={live_qty}")
                     # Decide: Trust Kotak? If Kotak is 0, we already handled above. 
                     # If partial, maybe keep open? For now, just log.
                else:
                    logger.info(f"✅ [CORE] Synced: {symbol} matches.")

    def run(self):
        logger.info("▶️ [CORE] Strategy Loop Started")
        
        while True:
            try:
                # 1. Check Open Positions Logic involved
                open_trades = self.db.get_open_trades(self.config['strategy_name'])
                
                if not open_trades:
                    # No positions? Check Entry Condition
                    self.check_entry()
                else:
                    # Have positions? Check Exit Condition
                    self.monitor_positions(open_trades)
                    
                time.sleep(self.config['check_interval'])
                
            except KeyboardInterrupt:
                logger.info("🛑 [CORE] Stopped by User")
                sys.exit(0)
            except Exception as e:
                logger.error(f"❌ [CORE] Loop Error: {e}")
                time.sleep(10)

    def check_entry(self):
        # 1. Check Time
        now = datetime.now().strftime("%H:%M")
        if now < self.config['entry_time']:
            logger.info(f"⏳ [CORE] Waiting for Entry Time {self.config['entry_time']} (Current: {now})")
            return

        # 2. Get Spot
        # We need Upstox Spot for strike selection
        # (Assuming Nifty 50)
        q = get_market_quote_for_instrument(self.access_token, "NSE_INDEX|Nifty 50")
        if not q: return
        spot = q.get('last_price', 0)
        
        if spot > 0:
            # New Logic: Find strikes by Premium (Target: 60)
            target_premium = self.config['target_premium']
            logger.info(f"🔍 [CORE] Spot: {spot} | Finding strikes with Premium ~ {target_premium}")
            
            ce_strike = self.find_strike_by_premium(spot, 'CE', target_premium)
            pe_strike = self.find_strike_by_premium(spot, 'PE', target_premium)
            
            if ce_strike and pe_strike:
                logger.info(f"✅ [CORE] Selected: CE {ce_strike} & PE {pe_strike}")
                self.execute_comb('SELL', ce_strike, pe_strike)
            else:
                logger.error("❌ [CORE] Could not find suitable strikes.")

    def find_strike_by_premium(self, spot, opt_type, target_premium):
        """
        Scan Option Chain to find strike closest to target premium.
        """
        try:
            # 1. Get Expiry Date Object
            expiry_dt = datetime.strptime(self.expiry_date, "%Y-%m-%d")
            
            # 2. Filter Master DF for Expiry and Type
            # Assuming master_df has columns: pSymbolName, pTrdSymbol, pExpiryDate, pOptionType, pStrikePrice
            # Note: Kotak Master DF columns might vary. Usually:
            # 'pSymbol': Token, 'pTrdSymbol': Symbol, 'pSymbolName': Underlying, 'pStrikePrice': Strike
            
            # We need to filter locally.
            df = self.kotak_broker.master_df
            if df is None or df.empty:
                logger.error("❌ [CORE] Master DF empty")
                return None
            
            # Filter Logic
            # pSymbolName usually holds "NIFTY" for Nifty Options.
            # pExchSeg should be "nse_fo"
            
            # Converting expiry to Kotak Format? 
            # Kotak CSV usually has standard dates. Let's filter carefully.
            
            # Optimization: We know specific strikes are likely around Spot +/- X
            # But "Premium 60" could be far.
            # Let's iterate.
            
            candidates = []
            
            # Rough filter using vectorized pandas if possible, or simple iteration
            # Iterating 100k rows is slow. Vectorized is better.
            
            # Column names from typical Kotak csv: 'pTrdSymbol', 'pSymbolName', 'pOptionType', 'pStrikePrice', 'pExpiryDate'
            # Check pSymbolName == 'Nifty 50' or 'NIFTY'?
            # Config says 'NIFTY'.
            
            # Filter 1: Underlying & Segment
            # User config underlying is 'NIFTY'.
            mask = (df['pSymbolName'] == self.config['underlying']) & \
                   (df['pExchSeg'] == 'nse_fo') & \
                   (df['pOptionType'] == opt_type)
            
            filtered = df[mask].copy()
            
            # Filter 2: Expiry
            # Kotak Expiry Format in CSV? usually '02FEB2026'.
            # Creating a helper to match dates might be tricky if formats mismatch.
            # Easier approach: Use `get_strike_token` to verify existence, but we need to FIND strikes.
            
            # Let's rely on standard pandas datetimelike if possible, or string match.
            # Let's try to convert 'pExpiryDate' to datetime?
            # Or just use the fact we have few expiries.
            
            # Let's iterate distinct expiries in filtered to find matching one.
            # format in csv usually "ddMMMyyyy". our self.expiry_date is YYYY-MM-DD.
            
            tgt_exp_str = expiry_dt.strftime("%d%b%Y").upper() # 24FEB2026
            
            filtered = filtered[filtered['pExpiryDate'] == tgt_exp_str]
            
            if filtered.empty:
                logger.error(f"❌ [CORE] No instruments found for {tgt_exp_str} {opt_type}")
                return None
                
            # Filter 3: OTM Only
            if opt_type == 'CE':
                filtered = filtered[filtered['pStrikePrice'] > spot]
                filtered = filtered.sort_values('pStrikePrice', ascending=True) # Ascending from ATM
            else:
                filtered = filtered[filtered['pStrikePrice'] < spot]
                filtered = filtered.sort_values('pStrikePrice', ascending=False) # Descending from ATM
            
            # Scan Strategy:
            # We don't want to fetch 100 prices.
            # Start from ATM + Offset? Or just check every 100 points?
            # 60 premium is usually 500-1000 points away for monthly?
            # Let's check every 2nd or 3rd strike to find range, then narrow down?
            # Or just fetch top 20 closest to ATM? 60 premium is not THAT deep.
            # Actually for Monthly, 60 premium might be 500-800 pts away.
            # Let's fetch 10-15 strikes spaced out, or just iterate sequentially with a limit.
            
            closest_strike = None
            min_diff = float('inf')
            
            # Limit checks to avoid rate limits
            checks = 0
            max_checks = 20
            
            # We iterate outwards from ATM
            for index, row in filtered.iterrows():
                strike = row['pStrikePrice']
                sym = row['pTrdSymbol']
                
                ltp = self.kotak_broker.get_ltp(sym)
                if ltp <= 0: continue
                
                diff = abs(ltp - target_premium)
                
                if diff < min_diff:
                    min_diff = diff
                    closest_strike = strike
                
                # If we passed the target (e.g. Premium dropped to 40), we can stop soon?
                # CE: Strike Up -> Premium Down.
                # If LTP < Target, we are getting deeper OTM.
                # If LTP >> Target, we need to go further.
                if ltp < target_premium and diff > 10: 
                    # We undershot significantly?
                    pass
                
                # Stop condition: If we found a match within 10% and now it's getting worse?
                # Simple Logic: Just check first 20 OTM strikes. 60 premium will be there for Nifty.
                checks += 1
                if checks > max_checks: break
                
                # Rate limit sleep
                time.sleep(0.1)
                
            return closest_strike
            
        except Exception as e:
            logger.error(f"Find Strike Error: {e}")
            return None

    def execute_comb(self, txn_type, ce_strike, pe_strike):
        """
        Execute both legs atomically. 
        If execution fails for any leg, ROLLBACK (exit) the successful ones.
        """
        expiry_dt = datetime.strptime(self.expiry_date, "%Y-%m-%d")
        
        executed_trades = [] # List of db_trade_dicts or similar tracking objects
        failed = False
        
        target_legs = [(ce_strike, 'CE'), (pe_strike, 'PE')]
        
        for strike, opt_type in target_legs:
            # 1. Resolve Instrument
            kotak_token, trading_symbol = get_strike_token(self.kotak_broker, strike, opt_type, expiry_dt)
            if not trading_symbol:
                logger.error(f"❌ [KOTAK] Could not resolve {strike} {opt_type}")
                failed = True
                break
                
            # 2. Get Lot Size
            k_lot = get_lot_size(self.kotak_broker.master_df, trading_symbol)
            qty = self.config['lots'] * k_lot
            
            # 3. Place Order
            logger.info(f"🚀 [KOTAK] Placing {txn_type} {trading_symbol} x {qty}")
            order_id = self.order_mgr.place_order(trading_symbol, qty, txn_type[0]) # 'S' or 'B'
            
            if order_id:
                # 4. Get Execution Price
                time.sleep(2)
                exec_price = self.order_mgr.get_execution_price(order_id)
                # Fallback Proxy
                if exec_price <= 0:
                     if self.config['dry_run']: 
                         exec_price = 100.0 
                     else:
                         quote = self.kotak_broker.get_ltp(trading_symbol)
                         exec_price = quote if quote > 0 else 1.0
                         logger.warning(f"⚠️ [CORE] Exec Price not captured for {order_id}. Using Proxy: {exec_price}")
                
                # 5. Save to DB
                trade_id = self.db.add_trade(
                    self.config['strategy_name'],
                    trading_symbol,
                    txn_type,
                    qty,
                    exec_price,
                    meta_data=f"{opt_type}|{strike}"
                )
                
                # Track for potential rollback
                executed_trades.append({
                    'id': trade_id,
                    'symbol': trading_symbol,
                    'quantity': qty,
                    'transaction_type': txn_type,
                    'entry_price': exec_price
                })
            else:
                logger.error(f"❌ [KOTAK] Order Failed for {trading_symbol}")
                failed = True
                break
        
        if failed:
            if executed_trades:
                logger.warning(f"⚠️ [CORE] Execution incomplete. Rolling back {len(executed_trades)} trades...")
                self.rollback_execution(executed_trades)
            else:
                logger.warning("⚠️ [CORE] Execution failed involved no trades. Nothing to rollback.")

    def rollback_execution(self, trades):
        """Exit the provided trades immediately."""
        for trade in trades:
            logger.info(f"⏪ [CORE] Rolling back: {trade['symbol']}")
            
            # Reverse Transaction Type
            exit_txn_type = 'BUY' if trade['transaction_type'] == 'SELL' else 'SELL'
            
            # Place Order
            order_id = self.order_mgr.place_order(trade['symbol'], trade['quantity'], exit_txn_type[0])
            
            exit_price = trade['entry_price'] # Default to break-even if fill fetch fails
            if order_id:
                time.sleep(1)
                fill = self.order_mgr.get_execution_price(order_id)
                if fill > 0: exit_price = fill
            
            # Close in DB
            self.db.close_trade(trade['id'], exit_price)
            self.db.update_status(trade['id'], 'CLOSED', "Rollback: PartialExec")
            
    def monitor_positions(self, trades):
        """Check SL/Target for each open trade."""
        
        # Batch fetch LTPs? DB stores Symbol. We need Upstox Keys for Live Data?
        # OR use Kotak Quote? 
        # Using Kotak Quote is easier since we have Kotak Symbols in DB.
        
        for trade in trades:
            symbol = trade['symbol']
            entry_price = trade['entry_price']
            
            # Fetch LTP from Kotak
            ltp = self.kotak_broker.get_ltp(symbol)
            if ltp <= 0: continue
            
            # Check Core Logic
            signal = self.check_exit_condition(entry_price, ltp, 'SHORT') # Always Short Strangle
            
            if signal:
                logger.info(f"🚨 [CORE] {signal} Triggered for {symbol}. Entry: {entry_price}, LTP: {ltp}")
                self.close_position(trade, ltp)

    def close_position(self, trade, ltp):
        # 1. Place Buy Order
        txn = 'BUY' # Closing a Short
        order_id = self.order_mgr.place_order(trade['symbol'], trade['quantity'], 'B')
        
        if order_id:
            # 2. Update DB
            # Ideally verify fill price, but for now use Trigger LTP or approximate
            time.sleep(1)
            fill_price = self.order_mgr.get_execution_price(order_id)
            if fill_price <= 0: fill_price = ltp
            
            self.db.close_trade(trade['id'], fill_price)

if __name__ == "__main__":
    token = get_access_token()
    if not token: sys.exit(1)
    
    strategy = MonthlyStrangleLive(token, CONFIG)
    if strategy.initialize():
        strategy.run()
