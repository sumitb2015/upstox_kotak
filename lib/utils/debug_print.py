"""
Utility module for debug-aware printing in the trading strategy.
Provides clean, single-line status updates in normal mode and detailed logs in debug mode.
"""

from datetime import datetime
from lib.core.config import Config


def debug_print(*args, **kwargs):
    """Print only if verbose/debug mode is enabled"""
    if Config.is_verbose():
        print(*args, **kwargs)


def status_print(message, level="INFO"):
    """
    Print status messages that are always shown (not debug-dependent).
    These are critical updates the user should always see.
    
    Args:
        message: The message to print
        level: INFO, SUCCESS, WARNING, ERROR
    """
    emoji_map = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "TRADE": "💰",
        "POSITION": "📊"
    }
    emoji = emoji_map.get(level, "")
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {emoji} {message}")


def position_status_line(positions_data):
    """
    Create a single-line status display for all positions.
    
    Args:
        positions_data: Dict with position information
    
    Returns:
        str: Single line status
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Extract data
    straddle_count = positions_data.get('straddle_count', 0)
    strangle_count = positions_data.get('strangle_count', 0)
    safe_otm_count = positions_data.get('safe_otm_count', 0)
    total_pnl = positions_data.get('total_pnl', 0)
    nifty_price = positions_data.get('nifty_price', 0)
    target = positions_data.get('target', 0)
    
    # Build compact status
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    
    status_parts = []
    if straddle_count > 0:
        status_parts.append(f"STR:{straddle_count}")
    if strangle_count > 0:
        status_parts.append(f"STG:{strangle_count}")
    if safe_otm_count > 0:
        status_parts.append(f"OTM:{safe_otm_count}")
    
    positions_str = " ".join(status_parts) if status_parts else "No Positions"
    
    return f"[{timestamp}] {pnl_emoji} P&L:₹{total_pnl:.0f}/₹{target:.0f} | {positions_str} | NIFTY:₹{nifty_price:.1f}"


def oi_summary_line(oi_data):
    """
    Create a single-line OI summary.
    
    Args:
        oi_data: Dict with OI analysis data
    
    Returns:
        str: Single line OI summary
    """
    sentiment = oi_data.get('sentiment', 'neutral')
    score = oi_data.get('score', 50)
    pcr = oi_data.get('pcr', 1.0)
    
    sentiment_emoji = "🟢" if sentiment == "bullish_for_sellers" else "🔴" if sentiment == "bearish_for_sellers" else "🟡"
    
    return f"{sentiment_emoji} OI: {sentiment.upper()} (Score:{score:.0f} PCR:{pcr:.2f})"
