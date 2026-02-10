"""
utils.py: Common utility functions for trading strategies.

Provides helper functions for:
- Lot size retrieval
- Strike rounding
- Date/time handling
"""

import pandas as pd


def get_lot_size(master_df, symbol):
    """
    Get lot size for a trading symbol.
    
    Args:
        master_df (DataFrame): Master data
        symbol (str): Trading symbol
        
    Returns:
        int: Lot size or 50 (default for Nifty)
    """
    result = master_df[master_df['pSymbolName'] == symbol]
    if not result.empty and 'pLotSize' in result.columns:
        return int(result.iloc[0]['pLotSize'])
    return 50  # Default Nifty lot size


def round_to_strike_interval(price, interval=50):
    """
    Round price to nearest strike interval.
    
    Args:
        price (float): Price to round
        interval (int, optional): Strike interval. Defaults to 50.
        
    Returns:
        int: Rounded strike price
    """
    return round(price / interval) * interval


def is_market_hours():
    """
    Check if current time is within market hours (9:15 AM - 3:30 PM IST).
    
    Returns:
        bool: True if within market hours
    """
    from datetime import datetime
    now = datetime.now()
    
    # Market hours: 9:15 AM to 3:30 PM
    market_open = now.replace(hour=9, minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    
    return market_open <= now <= market_close


def setup_strategy_logger(strategy_name, log_file=None, level="INFO"):
    """
    Setup standardized logger for strategy.
    
    Args:
        strategy_name (str): Name of strategy (e.g., "RollingStrategy")
        log_file (str, optional): Log file path. Defaults to {strategy_name}.log
        level (str, optional): Logging level. Defaults to "INFO".
    
    Returns:
        logging.Logger: Configured logger instance
    
    Example:
        >>> logger = setup_strategy_logger("RollingStrategy")
        >>> logger.info("Strategy started")
    """
    import logging
    import sys
    
    # Determine log file path
    if log_file is None:
        log_file = f"{strategy_name.lower().replace(' ', '_')}.log"
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8', mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(strategy_name)
    logger.info("=" * 60)
    logger.info(f"{strategy_name.upper()} STARTED")
    logger.info("=" * 60)
    
    return logger
