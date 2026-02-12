#!/usr/bin/env python
"""
Unified Backtest CLI

Usage:
    python backtest.py --strategy vwap_straddle --from 2024-10-01 --to 2024-10-31
    python backtest.py --strategy all --from 2024-10-01 --to 2024-10-31 --config my_config.yaml
"""

import argparse
import sys
import os
import yaml
from datetime import datetime

# Add root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from lib.core.backtesting.runner import UnifiedBacktestRunner
from lib.core.backtesting.registry import get_strategy, list_strategies, STRATEGY_REGISTRY
from lib.core.authentication import get_access_token


def load_config(config_path: str = None) -> dict:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to YAML config file (None = use default)
    
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'backtest_config.yaml')
    
    if not os.path.exists(config_path):
        print(f"⚠️  Config file not found: {config_path}")
        return {}
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_backtest(strategy_name: str, from_date: str, to_date: str, config_path: str = None):
    """
    Run backtest for a single strategy.
    
    Args:
        strategy_name: Name of strategy to backtest
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        config_path: Optional path to custom config file
    """
    # Load configuration
    all_config = load_config(config_path)
    strategy_config = all_config.get(strategy_name, {})
    global_config = all_config.get('global', {})
    
    # Get access token
    access_token = get_access_token()
    if not access_token:
        print("❌ No access token found. Please authenticate first.")
        sys.exit(1)
    
    # Get strategy class
    try:
        strategy_class = get_strategy(strategy_name)
    except KeyError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Get master path
    master_path = global_config.get('master_contracts_path')
    if master_path and not os.path.exists(master_path):
        print(f"⚠️  Master contracts file not found: {master_path}")
        master_path = None
    
    # Run backtest
    runner = UnifiedBacktestRunner(
        strategy_class=strategy_class,
        from_date=from_date,
        to_date=to_date,
        access_token=access_token,
        config=strategy_config,
        master_path=master_path
    )
    
    runner.run()


def main():
    parser = argparse.ArgumentParser(
        description='Unified Backtesting Framework',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backtest VWAP Straddle for October 2024
  python backtest.py --strategy vwap_straddle --from 2024-10-01 --to 2024-10-31
  
  # Backtest with custom config
  python backtest.py --strategy vwap_straddle --from 2024-10-01 --to 2024-10-31 --config my_config.yaml
  
  # Backtest all strategies
  python backtest.py --strategy all --from 2024-10-01 --to 2024-10-31
  
  # List available strategies
  python backtest.py --list
        """
    )
    
    parser.add_argument(
        '--strategy',
        type=str,
        help='Strategy to backtest (or "all" for all strategies)'
    )
    
    parser.add_argument(
        '--from',
        dest='from_date',
        type=str,
        help='Start date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--to',
        dest='to_date',
        type=str,
        help='End date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to custom config YAML file (optional)'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available strategies'
    )
    
    args = parser.parse_args()
    
    # List strategies
    if args.list:
        strategies = list_strategies()
        if strategies:
            print("Available strategies:")
            for s in strategies:
                print(f"  - {s}")
        else:
            print("No strategies registered yet.")
        sys.exit(0)
    
    # Validate required arguments
    if not args.strategy or not args.from_date or not args.to_date:
        parser.print_help()
        sys.exit(1)
    
    # Validate date format
    try:
        datetime.strptime(args.from_date, '%Y-%m-%d')
        datetime.strptime(args.to_date, '%Y-%m-%d')
    except ValueError:
        print("❌ Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)
    
    # Run backtest(s)
    if args.strategy == 'all':
        strategies = list_strategies()
        if not strategies:
            print("❌ No strategies registered.")
            sys.exit(1)
        
        print(f"🚀 Running backtest for {len(strategies)} strategies...")
        for strategy_name in strategies:
            print(f"\n{'='*70}")
            run_backtest(strategy_name, args.from_date, args.to_date, args.config)
    else:
        run_backtest(args.strategy, args.from_date, args.to_date, args.config)


if __name__ == "__main__":
    main()
