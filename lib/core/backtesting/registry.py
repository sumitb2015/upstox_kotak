"""
Strategy Registry

Central registry of all available backtestable strategies.
"""

# Import strategy implementations here
from strategies.non_directional.vwap_straddle_v2.backtest import VWAPStraddleBacktest
from strategies.backtest_testing.backtest import BacktestTestingBacktest
from strategies.dual_renko_dip.backtest import DualRenkoBacktest

STRATEGY_REGISTRY = {
    'vwap_straddle': VWAPStraddleBacktest,
    'backtest_testing': BacktestTestingBacktest,
    'dual_renko_dip': DualRenkoBacktest,
    # 'dynamic_strangle': DynamicStrangleBacktest,
    # 'orb_retest': ORBRetestBacktest,
}

def get_strategy(name: str):
    """
    Get strategy class by name.
    
    Args:
        name: Strategy name (key in registry)
    
    Returns:
        Strategy class
    
    Raises:
        KeyError if strategy not found
    """
    if name not in STRATEGY_REGISTRY:
        available = ', '.join(STRATEGY_REGISTRY.keys())
        raise KeyError(f"Strategy '{name}' not found. Available: {available}")
    
    return STRATEGY_REGISTRY[name]

def list_strategies():
    """
    List all available strategies.
    
    Returns:
        List of strategy names
    """
    return list(STRATEGY_REGISTRY.keys())
