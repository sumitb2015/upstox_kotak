import sqlite3
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class TradeDB:
    """
    Simple SQLite wrapper for managing positional trades.
    """
    def __init__(self, db_path="trades.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create Trades Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN', 
                    exit_price REAL,
                    exit_time TEXT,
                    pnl REAL,
                    meta_data TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"DATASTORE: Connected to {self.db_path}")
        except Exception as e:
            logger.error(f"DATASTORE: Init failed: {e}")
            raise e

    def add_trade(self, strategy_name: str, symbol: str, transaction_type: str, 
                  quantity: int, price: float, meta_data: str = "") -> int:
        """Record a new trade entry."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            entry_time = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO trades (strategy_name, symbol, transaction_type, quantity, entry_price, entry_time, status, meta_data)
                VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?)
            ''', (strategy_name, symbol, transaction_type, quantity, price, entry_time, meta_data))
            
            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"DATASTORE: Added Trade ID {trade_id} ({symbol})")
            return trade_id
        except Exception as e:
            logger.error(f"DATASTORE: Add trade failed: {e}")
            return -1

    def get_open_trades(self, strategy_name: str) -> List[Dict]:
        """Fetch all OPEN trades for a strategy."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM trades 
                WHERE strategy_name = ? AND status = 'OPEN'
            ''', (strategy_name,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"DATASTORE: Fetch open trades failed: {e}")
            return []

    def close_trade(self, trade_id: int, exit_price: float):
        """Mark a trade as CLOSED and calculate P&L."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Fetch generic info for P&L calc
            cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.error(f"DATASTORE: Trade ID {trade_id} not found")
                return
            
            trade = dict(row)
            entry_price = trade['entry_price']
            qty = trade['quantity']
            txn_type = trade['transaction_type']
            
            # Calculate P&L
            # SELL Entry -> Buy Exit: (Entry - Exit) * Qty
            # BUY Entry -> Sell Exit: (Exit - Entry) * Qty
            if txn_type == 'SELL':
                pnl = (entry_price - exit_price) * qty
            else:
                pnl = (exit_price - entry_price) * qty
                
            exit_time = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE trades 
                SET status = 'CLOSED', exit_price = ?, exit_time = ?, pnl = ?
                WHERE id = ?
            ''', (exit_price, exit_time, pnl, trade_id))
            
            conn.commit()
            conn.close()
            logger.info(f"DATASTORE: Closed Trade ID {trade_id} | P&L: {pnl:.2f}")
            
        except Exception as e:
            logger.error(f"DATASTORE: Close trade failed: {e}")

    def update_status(self, trade_id: int, status: str, notes: str = ""):
        """Force update status (e.g. for sync fixes)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE trades SET status = ? WHERE id = ?", (status, trade_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DATASTORE: Update status failed: {e}")
