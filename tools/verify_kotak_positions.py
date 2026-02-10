
import os
import sys
import logging
from datetime import datetime

# Add lib to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kotak_api.lib.broker import BrokerClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verifier")

def verify_account():
    broker = BrokerClient()
    try:
        client = broker.authenticate()
        
        # Check Orders
        print("\n" + "="*80)
        print("ORDER HISTORY (TODAY)")
        print("-" * 80)
        order_resp = client.order_report()
        orders = order_resp.get('data', []) if isinstance(order_resp, dict) else order_resp
        
        if not orders:
            print("No orders found for today.")
        else:
            print(f"{'TIME':<10} | {'SYMBOL':<20} | {'TYPE':<5} | {'QTY':<5} | {'PRICE':<8} | {'STATUS':<10} | {'ORDER_ID'}")
            print("-" * 80)
            for ord in orders:
                # Handle potential different keys
                time_str = ord.get('ordDtTm', ord.get('order_timestamp', 'N/A'))
                symbol = ord.get('trdSym', ord.get('trading_symbol', 'N/A'))
                side = ord.get('trantyp', ord.get('transaction_type', 'N/A'))
                qty = ord.get('qty', ord.get('quantity', '0'))
                price = ord.get('avgprc', ord.get('average_price', '0'))
                status = ord.get('ordSt', 'N/A')
                oid = ord.get('nOrdNo', ord.get('order_id', 'N/A'))
                
                print(f"{str(time_str)[-8:]:<10} | {symbol:<20} | {side:<5} | {qty:<5} | {price:<8} | {status:<10} | {oid}")

        # Check Positions
        print("\n" + "="*80)
        print("ACTIVE POSITIONS")
        print("-" * 80)
        pos_resp = client.positions()
        positions = pos_resp.get('data', []) if isinstance(pos_resp, dict) else pos_resp
        
        found = False
        print(f"{'SYMBOL':<25} | {'QTY':<10} | {'LTP':<10} | {'P&L':<10}")
        print("-" * 80)
        
        if positions:
            for pos in positions:
                symbol = pos.get('trdSym', 'N/A')
                buy_qty = int(pos.get('flBuyQty', 0))
                sell_qty = int(pos.get('flSellQty', 0))
                qty = buy_qty - sell_qty
                
                if qty != 0:
                    ltp = pos.get('ltp', 0)
                    pnl = pos.get('urPnL', 0)
                    print(f"{symbol:<25} | {qty:<10} | {ltp:<10} | {pnl:<10}")
                    found = True
        
        if not found:
            print("No open positions found.")
        print("="*80 + "\n")

    except Exception as e:
        logger.error(f"Verification failed: {e}")

if __name__ == "__main__":
    verify_account()
