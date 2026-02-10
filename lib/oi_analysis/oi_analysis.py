"""
Open Interest (OI) Analysis Module for Option Selling Strategy
Focuses on sentiment analysis and real-time monitoring from option selling perspective
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from lib.api.market_data import get_filtered_option_chain, get_option_chain_atm
from lib.oi_analysis.oi_analysis_fallback import OIAnalysisFallback


class OIAnalyzer:
    """
    Open Interest Analysis for Option Selling Strategy
    """
    
    def __init__(self, access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50", 
                 min_oi_threshold: float = 5.0, significant_oi_threshold: float = 10.0):
        """
        Initialize OI Analyzer
        
        Args:
            access_token (str): Upstox API access token
            underlying_key (str): Underlying instrument key
            min_oi_threshold (float): Minimum OI change % to consider significant (default: 5%)
            significant_oi_threshold (float): OI change % for high significance (default: 10%)
        """
        self.access_token = access_token
        self.underlying_key = underlying_key
        self.min_oi_threshold = min_oi_threshold
        self.significant_oi_threshold = significant_oi_threshold
        self.oi_history = {}  # Store historical OI data for trend analysis
        self.sentiment_cache = {}  # Cache sentiment analysis results
        self.fallback_analyzer = OIAnalysisFallback(access_token, underlying_key)  # Fallback analyzer
    
    def check_option_chain_availability(self) -> bool:
        """
        Check if option chain API is available and working
        
        Returns:
            bool: True if option chain API is working, False otherwise
        """
        try:
            # Try to get option chain data with minimal parameters
            expiry = self._get_current_expiry()
            option_chain_df = get_option_chain_atm(
                self.access_token, self.underlying_key, expiry,
                strikes_above=2, strikes_below=2
            )
            
            # Check if we got valid data
            if option_chain_df.empty:
                print("⚠️  Option chain API not available - using fallback analysis")
                return False
            
            # Check if we have OI data
            if 'oi' not in option_chain_df.columns or 'prev_oi' not in option_chain_df.columns:
                print("⚠️  OI data not available in option chain - using fallback analysis")
                return False
            
            # Option chain API is working (silent)
            return True
            
        except Exception as e:
            print(f"⚠️  Option chain API error: {e} - using fallback analysis")
            return False
    
    def _get_current_expiry(self) -> str:
        """Get current expiry date"""
        from datetime import datetime, timedelta
        today = datetime.now()
        # Simple logic to get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
    def classify_oi_activity(self, current_oi: int, prev_oi: int, price_change: float, 
                           option_type: str) -> str:
        """
        Classify OI activity based on OI change and price movement from option selling perspective
        
        Args:
            current_oi (int): Current OI
            prev_oi (int): Previous OI
            price_change (float): Price change (positive = price up, negative = price down)
            option_type (str): "call" or "put"
            min_oi_threshold (float): Minimum OI change percentage to consider significant (default: 5%)
        
        Returns:
            str: Classification - "long_build", "short_build", "long_unwinding", "short_unwinding", "insignificant"
        """
        oi_change = current_oi - prev_oi
        oi_change_percent = (oi_change / prev_oi * 100) if prev_oi > 0 else 0
        
        # Check if OI change is significant enough to classify
        if abs(oi_change_percent) < self.min_oi_threshold:
            return "insignificant"
        
        # For option selling strategy, we need to understand what's happening:
        # - Long Build: Buyers are accumulating (bad for sellers - price pressure)
        # - Short Build: Sellers are accumulating (good for sellers - price support)
        # - Long Unwinding: Buyers are exiting (good for sellers - less price pressure)
        # - Short Unwinding: Sellers are exiting (bad for sellers - less price support)
        
        if oi_change > 0:  # OI Building
            if price_change > 0:  # Price UP, OI UP
                return "long_build"
            else:  # Price DOWN, OI UP
                return "short_build"
        else:  # OI Unwinding
            if price_change < 0:  # Price DOWN, OI DOWN
                return "long_unwinding"
            else:  # Price UP, OI DOWN
                return "short_covering"
    
    def analyze_strike_sentiment(self, option_chain_df: pd.DataFrame, 
                               strike_price: int) -> Dict:
        """
        Analyze sentiment for a specific strike price from option selling perspective
        
        Args:
            option_chain_df (pd.DataFrame): Option chain data
            strike_price (int): Strike price to analyze
        
        Returns:
            Dict: Sentiment analysis for the strike
        """
        try:
            # Filter data for the specific strike
            strike_data = option_chain_df[option_chain_df['strike_price'] == strike_price]
            
            if strike_data.empty:
                return {"error": f"No data found for strike {strike_price}"}
            
            # Get call and put data
            call_data = strike_data[strike_data['type'] == 'call']
            put_data = strike_data[strike_data['type'] == 'put']
            
            if call_data.empty or put_data.empty:
                return {"error": f"Incomplete data for strike {strike_price}"}
            
            call_row = call_data.iloc[0]
            put_row = put_data.iloc[0]
            
            # Calculate price changes from current and previous LTP
            call_price_change = 0
            put_price_change = 0
            
            # If we have previous LTP data, calculate price change
            if 'prev_ltp' in call_row and call_row['prev_ltp'] > 0:
                call_price_change = call_row['ltp'] - call_row['prev_ltp']
            if 'prev_ltp' in put_row and put_row['prev_ltp'] > 0:
                put_price_change = put_row['ltp'] - put_row['prev_ltp']
            
            # Classify OI activity
            call_oi_activity = self.classify_oi_activity(
                call_row['oi'], call_row['prev_oi'], call_price_change, "call"
            )
            put_oi_activity = self.classify_oi_activity(
                put_row['oi'], put_row['prev_oi'], put_price_change, "put"
            )
            
            # Calculate OI change percentages
            call_oi_change_pct = ((call_row['oi'] - call_row['prev_oi']) / call_row['prev_oi'] * 100) if call_row['prev_oi'] > 0 else 0
            put_oi_change_pct = ((put_row['oi'] - put_row['prev_oi']) / put_row['prev_oi'] * 100) if put_row['prev_oi'] > 0 else 0
            
            # Determine overall strike sentiment for option sellers
            strike_sentiment = self._determine_strike_sentiment(
                call_oi_activity, put_oi_activity, call_oi_change_pct, put_oi_change_pct
            )
            
            # Calculate confidence based on OI change magnitude and activity clarity
            confidence = self._calculate_confidence(
                call_oi_activity, put_oi_activity, call_oi_change_pct, put_oi_change_pct
            )
            
            return {
                "strike_price": strike_price,
                "call_oi": call_row['oi'],
                "call_prev_oi": call_row['prev_oi'],
                "call_oi_change_pct": call_oi_change_pct,
                "call_oi_activity": call_oi_activity,
                "put_oi": put_row['oi'],
                "put_prev_oi": put_row['prev_oi'],
                "put_oi_change_pct": put_oi_change_pct,
                "put_oi_activity": put_oi_activity,
                "strike_sentiment": strike_sentiment,
                "confidence": confidence,
                "pcr": call_row['pcr'],
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error analyzing strike {strike_price}: {str(e)}"}
    
    def _determine_strike_sentiment(self, call_oi_activity: str, put_oi_activity: str,
                                  call_oi_change_pct: float, put_oi_change_pct: float) -> str:
        """
        Determine overall strike sentiment for option sellers
        
        Args:
            call_oi_activity (str): Call OI activity classification
            put_oi_activity (str): Put OI activity classification
            call_oi_change_pct (float): Call OI change percentage
            put_oi_change_pct (float): Put OI change percentage
        
        Returns:
            str: Overall sentiment - "bullish_for_sellers", "bearish_for_sellers", "neutral"
        """
        # For option sellers:
        # Bullish for sellers: Less buying pressure, more selling pressure
        # Bearish for sellers: More buying pressure, less selling pressure
        
        bullish_signals = 0
        bearish_signals = 0
        
        # Analyze call activity (ignore insignificant changes)
        if call_oi_activity == "long_build":
            bearish_signals += 1  # Aggressive call buying (bearish for sellers)
        elif call_oi_activity == "short_build":
            bullish_signals += 1  # Aggressive call selling (bullish for sellers)
        elif call_oi_activity == "long_unwinding":
            bullish_signals += 0.5  # Call buyers exiting (mildly bullish)
        elif call_oi_activity == "short_covering":
            bearish_signals += 1  # Call sellers panicking (bearish for sellers)
        
        # Analyze put activity (ignore insignificant changes)
        if put_oi_activity == "long_build":
            bearish_signals += 1  # Aggressive put buying = Market Down (bearish for sellers)
        elif put_oi_activity == "short_build":
            bullish_signals += 1  # Aggressive put selling = Market Support (bullish for sellers)
        elif put_oi_activity == "long_unwinding":
            bullish_signals += 0.5  # Put buyers exiting (mildly bullish)
        elif put_oi_activity == "short_covering":
            bearish_signals += 1  # Put sellers panicking (bearish for sellers)
        
        # Weight by OI change magnitude (only for significant changes)
        if abs(call_oi_change_pct) > self.significant_oi_threshold:
            if call_oi_change_pct > 0 and call_oi_activity in ["long_build", "short_covering"]:
                bearish_signals += 0.5
            elif call_oi_change_pct < 0 and call_oi_activity in ["long_unwinding", "short_build"]:
                bullish_signals += 0.5
        
        if abs(put_oi_change_pct) > self.significant_oi_threshold:
            if put_oi_change_pct > 0 and put_oi_activity in ["long_build", "short_covering"]:
                bearish_signals += 0.5
            elif put_oi_change_pct < 0 and put_oi_activity in ["long_unwinding", "short_build"]:
                bullish_signals += 0.5
        
        # Determine overall sentiment
        if bullish_signals > bearish_signals + 1:
            return "bullish_for_sellers"
        elif bearish_signals > bullish_signals + 1:
            return "bearish_for_sellers"
        else:
            return "neutral"
    
    def _calculate_confidence(self, call_oi_activity: str, put_oi_activity: str,
                            call_oi_change_pct: float, put_oi_change_pct: float) -> float:
        """
        Calculate confidence level based on OI activity clarity and magnitude
        
        Args:
            call_oi_activity (str): Call OI activity classification
            put_oi_activity (str): Put OI activity classification
            call_oi_change_pct (float): Call OI change percentage
            put_oi_change_pct (float): Put OI change percentage
        
        Returns:
            float: Confidence percentage (0-100)
        """
        confidence = 50  # Base confidence
        
        # Increase confidence for significant OI changes
        significant_changes = 0
        if abs(call_oi_change_pct) > self.significant_oi_threshold:
            significant_changes += 1
            # Higher confidence for larger changes
            if abs(call_oi_change_pct) > self.significant_oi_threshold * 2:
                confidence += 15
            else:
                confidence += 10
        
        if abs(put_oi_change_pct) > self.significant_oi_threshold:
            significant_changes += 1
            # Higher confidence for larger changes
            if abs(put_oi_change_pct) > self.significant_oi_threshold * 2:
                confidence += 15
            else:
                confidence += 10
        
        # Increase confidence for clear activity patterns
        clear_activities = 0
        if call_oi_activity not in ['insignificant', 'neutral']:
            clear_activities += 1
        if put_oi_activity not in ['insignificant', 'neutral']:
            clear_activities += 1
        
        # Bonus for multiple clear signals
        if significant_changes >= 2:
            confidence += 10
        if clear_activities >= 2:
            confidence += 10
        
        # Increase confidence for consistent directional signals
        if (call_oi_activity in ['long_unwinding', 'short_build'] and 
            put_oi_activity in ['long_unwinding', 'short_build']):
            confidence += 15  # Both favorable for sellers
        elif (call_oi_activity in ['long_build', 'short_unwinding'] and 
              put_oi_activity in ['long_build', 'short_unwinding']):
            confidence += 15  # Both unfavorable for sellers
        
        # Ensure confidence is within bounds
        return max(0, min(100, confidence))
    
    def analyze_market_sentiment(self, option_chain_df: pd.DataFrame = None, 
                               atm_strikes: List[int] = None) -> Dict:
        """
        Analyze overall market sentiment from option selling perspective
        
        Args:
            option_chain_df (pd.DataFrame): Option chain data (optional, will use fallback if None)
            atm_strikes (List[int]): List of ATM strikes to analyze (default: auto-detect)
        
        Returns:
            Dict: Market sentiment analysis
        """
        try:
            # Check if option chain data is available
            if option_chain_df is None or option_chain_df.empty:
                print("📊 Using fallback analysis - option chain data not available")
                return self.fallback_analyzer.get_fallback_monitoring_update()
            
            if atm_strikes is None:
                # Auto-detect ATM strikes (spot ± 2 strikes)
                spot_price = option_chain_df['underlying_spot'].iloc[0]
                atm_strikes = [
                    spot_price - 100, spot_price - 50, spot_price, 
                    spot_price + 50, spot_price + 100
                ]
            
            strike_sentiments = []
            total_call_oi = 0
            total_put_oi = 0
            total_call_oi_change = 0
            total_put_oi_change = 0
            
            for strike in atm_strikes:
                sentiment = self.analyze_strike_sentiment(option_chain_df, strike)
                if "error" not in sentiment:
                    strike_sentiments.append(sentiment)
                    
                    # Aggregate OI data
                    total_call_oi += sentiment['call_oi']
                    total_put_oi += sentiment['put_oi']
                    total_call_oi_change += sentiment['call_oi_change_pct']
                    total_put_oi_change += sentiment['put_oi_change_pct']
            
            if not strike_sentiments:
                return {"error": "No valid strike sentiments found"}
            
            # Calculate overall market sentiment
            bullish_count = sum(1 for s in strike_sentiments if s['strike_sentiment'] == 'bullish_for_sellers')
            bearish_count = sum(1 for s in strike_sentiments if s['strike_sentiment'] == 'bearish_for_sellers')
            neutral_count = sum(1 for s in strike_sentiments if s['strike_sentiment'] == 'neutral')
            
            # Calculate PCR (Put-Call Ratio)
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            # Determine overall market sentiment
            if bullish_count > bearish_count + neutral_count:
                market_sentiment = "bullish_for_sellers"
            elif bearish_count > bullish_count + neutral_count:
                market_sentiment = "bearish_for_sellers"
            else:
                market_sentiment = "neutral"
            
            return {
                "market_sentiment": market_sentiment,
                "bullish_strikes": bullish_count,
                "bearish_strikes": bearish_count,
                "neutral_strikes": neutral_count,
                "total_strikes_analyzed": len(strike_sentiments),
                "pcr": pcr,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "avg_call_oi_change_pct": total_call_oi_change / len(strike_sentiments),
                "avg_put_oi_change_pct": total_put_oi_change / len(strike_sentiments),
                "strike_details": strike_sentiments,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error analyzing market sentiment: {str(e)}"}
    
    def get_optimal_selling_strikes(self, option_chain_df: pd.DataFrame, 
                                  spot_price: int, num_strikes: int = 5) -> List[Dict]:
        """
        Get optimal strikes for option selling based on OI analysis
        
        Args:
            option_chain_df (pd.DataFrame): Option chain data
            spot_price (int): Current spot price
            num_strikes (int): Number of strikes to analyze
        
        Returns:
            List[Dict]: List of optimal strikes with sentiment analysis
        """
        try:
            # Get strikes around ATM
            strikes_to_analyze = []
            for i in range(-num_strikes//2, num_strikes//2 + 1):
                strike = spot_price + (i * 50)  # 50 point intervals for NIFTY
                strikes_to_analyze.append(strike)
            
            optimal_strikes = []
            
            for strike in strikes_to_analyze:
                sentiment = self.analyze_strike_sentiment(option_chain_df, strike)
                if "error" not in sentiment:
                    # Add selling score based on sentiment
                    selling_score = self._calculate_selling_score(sentiment)
                    sentiment['selling_score'] = selling_score
                    sentiment['distance_from_spot'] = abs(strike - spot_price)
                    optimal_strikes.append(sentiment)
            
            # Sort by selling score (higher is better for sellers)
            optimal_strikes.sort(key=lambda x: x['selling_score'], reverse=True)
            
            return optimal_strikes
            
        except Exception as e:
            return [{"error": f"Error getting optimal strikes: {str(e)}"}]
    
    def _calculate_selling_score(self, sentiment: Dict) -> float:
        """
        Calculate selling score for a strike (higher = better for selling)
        
        Args:
            sentiment (Dict): Strike sentiment analysis
        
        Returns:
            float: Selling score (0-100)
        """
        score = 50  # Base score
        
        # Adjust based on strike sentiment
        if sentiment['strike_sentiment'] == 'bullish_for_sellers':
            score += 20
        elif sentiment['strike_sentiment'] == 'bearish_for_sellers':
            score -= 20
        
        # Adjust based on OI activities
        if sentiment['call_oi_activity'] == 'long_unwinding':
            score += 10  # Call buyers exiting
        elif sentiment['call_oi_activity'] == 'long_build':
            score -= 10  # Call buyers accumulating
        
        if sentiment['put_oi_activity'] == 'long_build':
            score += 10  # Put buyers accumulating
        elif sentiment['put_oi_activity'] == 'long_unwinding':
            score -= 10  # Put buyers exiting
        
        # Adjust based on OI change magnitude (only for significant changes)
        if abs(sentiment['call_oi_change_pct']) > self.significant_oi_threshold:
            if sentiment['call_oi_change_pct'] < 0:  # OI decreasing
                score += 5
            else:  # OI increasing
                score -= 5
        
        if abs(sentiment['put_oi_change_pct']) > self.significant_oi_threshold:
            if sentiment['put_oi_change_pct'] > 0:  # Put OI increasing
                score += 5
            else:  # Put OI decreasing
                score -= 5
        
        # Ensure score is within bounds
        return max(0, min(100, score))
    
    def format_sentiment_analysis(self, sentiment_data: Dict) -> str:
        """
        Format sentiment analysis for display
        
        Args:
            sentiment_data (Dict): Sentiment analysis data
        
        Returns:
            str: Formatted string for display
        """
        if "error" in sentiment_data:
            return f"❌ Error: {sentiment_data['error']}"
        
        output = []
        output.append("="*60)
        output.append("OI SENTIMENT ANALYSIS (OPTION SELLING PERSPECTIVE)")
        output.append("="*60)
        
        if "market_sentiment" in sentiment_data:
            # Market sentiment
            market_sentiment = sentiment_data['market_sentiment']
            sentiment_emoji = "🟢" if market_sentiment == "bullish_for_sellers" else "🔴" if market_sentiment == "bearish_for_sellers" else "🟡"
            
            output.append(f"\n📊 MARKET SENTIMENT: {sentiment_emoji} {market_sentiment.upper()}")
            output.append(f"📈 Bullish Strikes: {sentiment_data['bullish_strikes']}")
            output.append(f"📉 Bearish Strikes: {sentiment_data['bearish_strikes']}")
            output.append(f"➖ Neutral Strikes: {sentiment_data['neutral_strikes']}")
            output.append(f"📊 PCR: {sentiment_data['pcr']:.2f}")
            output.append(f"📊 Total Call OI: {sentiment_data['total_call_oi']:,}")
            output.append(f"📊 Total Put OI: {sentiment_data['total_put_oi']:,}")
            
            # Strike details
            output.append(f"\n📋 STRIKE DETAILS:")
            for strike_detail in sentiment_data['strike_details']:
                strike = strike_detail['strike_price']
                sentiment = strike_detail['strike_sentiment']
                call_activity = strike_detail['call_oi_activity']
                put_activity = strike_detail['put_oi_activity']
                
                sentiment_emoji = "🟢" if sentiment == "bullish_for_sellers" else "🔴" if sentiment == "bearish_for_sellers" else "🟡"
                
                output.append(f"  {strike}: {sentiment_emoji} {sentiment}")
                output.append(f"    Call: {call_activity} ({strike_detail['call_oi_change_pct']:+.1f}%)")
                output.append(f"    Put: {put_activity} ({strike_detail['put_oi_change_pct']:+.1f}%)")
        
        else:
            # Single strike sentiment
            strike = sentiment_data['strike_price']
            sentiment = sentiment_data['strike_sentiment']
            sentiment_emoji = "🟢" if sentiment == "bullish_for_sellers" else "🔴" if sentiment == "bearish_for_sellers" else "🟡"
            
            output.append(f"\n📊 STRIKE {strike} SENTIMENT: {sentiment_emoji} {sentiment.upper()}")
            output.append(f"📞 Call OI: {sentiment_data['call_oi']:,} ({sentiment_data['call_oi_change_pct']:+.1f}%) - {sentiment_data['call_oi_activity']}")
            output.append(f"📞 Put OI: {sentiment_data['put_oi']:,} ({sentiment_data['put_oi_change_pct']:+.1f}%) - {sentiment_data['put_oi_activity']}")
            output.append(f"📊 PCR: {sentiment_data['pcr']:.2f}")
            
            if 'selling_score' in sentiment_data:
                output.append(f"🎯 Selling Score: {sentiment_data['selling_score']:.1f}/100")
        
        output.append("="*60)
        return "\n".join(output)


def get_oi_sentiment_analysis(access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50",
                            expiry: str = None, strikes_around_atm: int = 5) -> Dict:
    """
    Quick function to get OI sentiment analysis with fallback support
    
    Args:
        access_token (str): Upstox API access token
        underlying_key (str): Underlying instrument key
        expiry (str): Expiry date (YYYY-MM-DD format)
        strikes_around_atm (int): Number of strikes to analyze around ATM
    
    Returns:
        Dict: OI sentiment analysis
    """
    try:
        # Initialize analyzer
        analyzer = OIAnalyzer(access_token, underlying_key)
        
        # Check if option chain API is available
        if not analyzer.check_option_chain_availability():
            print("📊 Option chain API not available - using fallback analysis")
            return analyzer.fallback_analyzer.get_fallback_monitoring_update()
        
        # Get option chain data
        if expiry is None:
            expiry = analyzer._get_current_expiry()
        
        option_chain_df = get_option_chain_atm(
            access_token, underlying_key, expiry, 
            strikes_above=strikes_around_atm, strikes_below=strikes_around_atm
        )
        
        if option_chain_df.empty:
            print("📊 No option chain data - using fallback analysis")
            return analyzer.fallback_analyzer.get_fallback_monitoring_update()
        
        # Analyze market sentiment
        sentiment = analyzer.analyze_market_sentiment(option_chain_df)
        
        return sentiment
        
    except Exception as e:
        print(f"📊 Error in OI sentiment analysis: {e} - using fallback")
        try:
            analyzer = OIAnalyzer(access_token, underlying_key)
            return analyzer.fallback_analyzer.get_fallback_monitoring_update()
        except Exception as fallback_error:
            return {"error": f"Both main and fallback analysis failed: {str(e)}, {str(fallback_error)}"}


# Example usage and testing
if __name__ == "__main__":
    # This would be called from main.py with proper parameters
    print("OI Analysis Module for Option Selling Strategy")
    print("This module should be imported and used from main.py")
