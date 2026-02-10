"""
EMA Directional Hedge Strategy Package

Sells credit spreads (Bull Put / Bear Call) based on EMA momentum.
"""

from .config import CONFIG, validate_config
from .core import EMAHedgeCore, SpreadPosition

__all__ = ['CONFIG', 'validate_config', 'EMAHedgeCore', 'SpreadPosition']
