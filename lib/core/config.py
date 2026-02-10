"""
Configuration module for the trading strategy
"""

class Config:
    """Global configuration for the trading strategy"""
    
    # Logging configuration
    VERBOSE_LOGGING = False  # Set to True for detailed debug output
    
    # Strategy configuration
    DEFAULT_LOT_SIZE = 1
    DEFAULT_PROFIT_TARGET = 3000
    DEFAULT_MAX_LOSS_LIMIT = 3000
    DEFAULT_RATIO_THRESHOLD = 0.6
    
    # WebSocket Configuration
    STREAMING_DEBUG = False # Set to True to see raw WebSocket data
    
    # API configuration
    DEFAULT_CHECK_INTERVAL = 15  # seconds
    
    @classmethod
    def set_verbose(cls, verbose: bool):
        """Set verbose logging mode"""
        cls.VERBOSE_LOGGING = verbose
    
    @classmethod
    def is_verbose(cls) -> bool:
        """Check if verbose logging is enabled"""
        return cls.VERBOSE_LOGGING

    @classmethod
    def set_streaming_debug(cls, enabled: bool):
        """Set streaming debug mode"""
        cls.STREAMING_DEBUG = enabled

    @classmethod
    def is_streaming_debug(cls) -> bool:
        """Check if streaming debug is enabled"""
        return cls.STREAMING_DEBUG

def debug_print(*args, **kwargs):
    """Print only if verbose mode is enabled"""
    if Config.is_verbose():
        print(*args, **kwargs)
