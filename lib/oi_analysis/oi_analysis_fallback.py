"""
Fallback OI Analysis for when Option Chain API is not available
Uses alternative data sources and simplified analysis
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from lib.api.market_quotes import get_ltp_quote, get_multiple_ltp_quotes


class OIAnalysisFallback:
    """
    Fallback OI analysis when option chain API is not available
    Uses LTP data and basic market analysis
    """
    
    def __init__(self, access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50"):
        """
        Initialize fallback OI analyzer
        
        Args:
            access_token (str): Upstox API access token
            underlying_key (str): Underlying instrument key
        """
        self.access_token = access_token
        self.underlying_key = underlying_key
        self.price_history = {}  # Store price history for trend analysis
        
    def get_basic_market_sentiment(self) -> Dict:
        """
        Get basic market sentiment using available data
        
        Returns:
            Dict: Basic market sentiment analysis
        """
        try:
            # Get NIFTY spot price
            nifty_quote = get_ltp_quote(self.access_token, self.underlying_key)
            
            if not nifty_quote or nifty_quote.get('status') != 'success':
                return {"error": "Could not fetch NIFTY spot price"}
            
            data = nifty_quote.get('data', {})
            if not data:
                return {"error": "No data in NIFTY response"}
            
            key = list(data.keys())[0]
            spot_price = data[key].get('last_price', 0)
            
            if spot_price <= 0:
                return {"error": "Invalid NIFTY spot price"}
            
            # Calculate ATM strike
            atm_strike = round(spot_price / 50) * 50
            
            # Basic sentiment based on price movement (simplified)
            sentiment = self._calculate_basic_sentiment(spot_price)
            
            return {
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "sentiment": sentiment,
                "timestamp": datetime.now(),
                "data_source": "fallback_ltp"
            }
            
        except Exception as e:
            return {"error": f"Error in basic market sentiment: {str(e)}"}
    
    def _calculate_basic_sentiment(self, current_price: float) -> str:
        """
        Calculate basic sentiment based on price movement
        
        Args:
            current_price (float): Current spot price
        
        Returns:
            str: Basic sentiment
        """
        try:
            # Store price in history
            timestamp = datetime.now()
            self.price_history[timestamp] = current_price
            
            # Keep only last 10 prices
            if len(self.price_history) > 10:
                oldest_key = min(self.price_history.keys())
                del self.price_history[oldest_key]
            
            # Need at least 2 prices for trend analysis
            if len(self.price_history) < 2:
                return "neutral"
            
            # Calculate simple trend
            prices = list(self.price_history.values())
            recent_trend = (prices[-1] - prices[-2]) / prices[-2] * 100 if prices[-2] > 0 else 0
            
            # Basic sentiment classification
            if recent_trend > 0.5:
                return "bullish"
            elif recent_trend < -0.5:
                return "bearish"
            else:
                return "neutral"
                
        except Exception as e:
            return "neutral"
    
    def get_simplified_selling_recommendation(self, strike: int) -> Dict:
        """
        Get simplified selling recommendation based on available data
        
        Args:
            strike (int): Strike price to analyze
        
        Returns:
            Dict: Simplified selling recommendation
        """
        try:
            # Get basic market sentiment
            market_data = self.get_basic_market_sentiment()
            
            if "error" in market_data:
                return market_data
            
            spot_price = market_data["spot_price"]
            atm_strike = market_data["atm_strike"]
            sentiment = market_data["sentiment"]
            
            # Calculate distance from ATM
            distance_from_atm = abs(strike - atm_strike)
            
            # Calculate basic selling score
            selling_score = self._calculate_simple_selling_score(
                strike, spot_price, atm_strike, sentiment, distance_from_atm
            )
            
            # Determine recommendation
            if selling_score >= 70:
                recommendation = "strong_sell"
                risk_level = "low"
            elif selling_score >= 60:
                recommendation = "sell"
                risk_level = "low"
            elif selling_score >= 50:
                recommendation = "neutral"
                risk_level = "medium"
            elif selling_score >= 40:
                recommendation = "avoid"
                risk_level = "high"
            else:
                recommendation = "strong_avoid"
                risk_level = "very_high"
            
            return {
                "strike": strike,
                "recommendation": recommendation,
                "selling_score": selling_score,
                "risk_level": risk_level,
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "distance_from_atm": distance_from_atm,
                "market_sentiment": sentiment,
                "reasoning": self._get_simple_reasoning(strike, spot_price, atm_strike, sentiment, selling_score),
                "data_source": "fallback_analysis",
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error in simplified selling recommendation: {str(e)}"}
    
    def _calculate_simple_selling_score(self, strike: int, spot_price: float, 
                                      atm_strike: int, sentiment: str, 
                                      distance_from_atm: int) -> float:
        """
        Calculate simple selling score based on available data
        
        Args:
            strike (int): Strike price
            spot_price (float): Current spot price
            atm_strike (int): ATM strike price
            sentiment (str): Market sentiment
            distance_from_atm (int): Distance from ATM in points
        
        Returns:
            float: Selling score (0-100)
        """
        score = 50  # Base score
        
        # Adjust based on distance from ATM
        if distance_from_atm <= 50:  # Very close to ATM
            score += 10
        elif distance_from_atm <= 100:  # Close to ATM
            score += 5
        elif distance_from_atm >= 200:  # Far from ATM
            score -= 10
        
        # Adjust based on market sentiment
        if sentiment == "bullish":
            # In bullish market, selling calls closer to spot might be better
            if strike > spot_price:
                score += 5
            else:
                score -= 5
        elif sentiment == "bearish":
            # In bearish market, selling puts closer to spot might be better
            if strike < spot_price:
                score += 5
            else:
                score -= 5
        
        # Adjust based on strike position relative to spot
        if abs(strike - spot_price) <= 50:  # Very close to spot
            score += 5
        elif abs(strike - spot_price) <= 100:  # Close to spot
            score += 2
        
        # Ensure score is within bounds
        return max(0, min(100, score))
    
    def _get_simple_reasoning(self, strike: int, spot_price: float, 
                            atm_strike: int, sentiment: str, selling_score: float) -> str:
        """
        Get simple reasoning for selling recommendation
        
        Args:
            strike (int): Strike price
            spot_price (float): Current spot price
            atm_strike (int): ATM strike price
            sentiment (str): Market sentiment
            selling_score (float): Selling score
        
        Returns:
            str: Reasoning text
        """
        reasons = []
        
        # Distance reasoning
        distance = abs(strike - atm_strike)
        if distance <= 50:
            reasons.append("Close to ATM (good for selling)")
        elif distance <= 100:
            reasons.append("Near ATM (reasonable for selling)")
        elif distance >= 200:
            reasons.append("Far from ATM (higher risk)")
        
        # Sentiment reasoning
        if sentiment == "bullish":
            reasons.append("Bullish market sentiment")
        elif sentiment == "bearish":
            reasons.append("Bearish market sentiment")
        else:
            reasons.append("Neutral market sentiment")
        
        # Score reasoning
        if selling_score >= 70:
            reasons.append("High selling score - optimal conditions")
        elif selling_score <= 30:
            reasons.append("Low selling score - unfavorable conditions")
        
        return "; ".join(reasons) if reasons else "Basic analysis completed"
    
    def get_fallback_monitoring_update(self) -> Dict:
        """
        Get fallback monitoring update when option chain is not available
        
        Returns:
            Dict: Fallback monitoring data
        """
        try:
            # Get basic market data
            market_data = self.get_basic_market_sentiment()
            
            if "error" in market_data:
                return market_data
            
            # Generate basic recommendations for common strikes
            atm_strike = market_data["atm_strike"]
            common_strikes = [
                atm_strike - 100,
                atm_strike - 50,
                atm_strike,
                atm_strike + 50,
                atm_strike + 100
            ]
            
            strike_recommendations = {}
            for strike in common_strikes:
                rec = self.get_simplified_selling_recommendation(strike)
                if "error" not in rec:
                    strike_recommendations[strike] = rec
            
            # Calculate overall recommendation
            if strike_recommendations:
                scores = [rec["selling_score"] for rec in strike_recommendations.values()]
                avg_score = sum(scores) / len(scores)
                
                if avg_score >= 60:
                    overall_recommendation = "bullish_for_selling"
                    risk_level = "low"
                elif avg_score <= 40:
                    overall_recommendation = "bearish_for_selling"
                    risk_level = "high"
                else:
                    overall_recommendation = "neutral"
                    risk_level = "medium"
            else:
                overall_recommendation = "neutral"
                risk_level = "medium"
            
            return {
                "timestamp": datetime.now(),
                "market_data": market_data,
                "strike_recommendations": strike_recommendations,
                "overall_recommendation": overall_recommendation,
                "risk_level": risk_level,
                "data_source": "fallback_monitoring"
            }
            
        except Exception as e:
            return {"error": f"Error in fallback monitoring: {str(e)}"}
    
    def format_fallback_display(self, monitoring_data: Dict) -> str:
        """
        Format fallback monitoring data for display
        
        Args:
            monitoring_data (Dict): Fallback monitoring data
        
        Returns:
            str: Formatted display string
        """
        if "error" in monitoring_data:
            return f"❌ Error: {monitoring_data['error']}"
        
        output = []
        output.append("="*70)
        output.append("FALLBACK OI ANALYSIS (BASED ON AVAILABLE DATA)")
        output.append("="*70)
        
        timestamp = monitoring_data["timestamp"].strftime("%H:%M:%S")
        output.append(f"⏰ Timestamp: {timestamp}")
        output.append(f"📊 Data Source: {monitoring_data.get('data_source', 'fallback')}")
        
        market_data = monitoring_data.get("market_data", {})
        if market_data:
            output.append(f"\n📊 MARKET DATA:")
            output.append(f"  Spot Price: ₹{market_data.get('spot_price', 0):.2f}")
            output.append(f"  ATM Strike: {market_data.get('atm_strike', 0)}")
            output.append(f"  Sentiment: {market_data.get('sentiment', 'neutral')}")
        
        strike_recommendations = monitoring_data.get("strike_recommendations", {})
        if strike_recommendations:
            output.append(f"\n📋 STRIKE RECOMMENDATIONS ({len(strike_recommendations)}):")
            
            for strike, rec in sorted(strike_recommendations.items()):
                rec_emoji = "🟢" if rec['recommendation'] in ["strong_sell", "sell"] else "🔴" if rec['recommendation'] in ["strong_avoid", "avoid"] else "🟡"
                
                output.append(f"\n  📍 Strike {strike}: {rec_emoji} {rec['recommendation']}")
                output.append(f"    Score: {rec['selling_score']:.1f}/100")
                output.append(f"    Risk: {rec['risk_level']}")
                output.append(f"    Distance from ATM: {rec['distance_from_atm']} points")
                output.append(f"    Reasoning: {rec['reasoning']}")
        
        overall_rec = monitoring_data.get("overall_recommendation", "neutral")
        risk_level = monitoring_data.get("risk_level", "medium")
        
        rec_emoji = "🟢" if overall_rec == "bullish_for_selling" else "🔴" if overall_rec == "bearish_for_selling" else "🟡"
        output.append(f"\n🎯 OVERALL RECOMMENDATION: {rec_emoji} {overall_rec.upper()}")
        output.append(f"⚠️  Risk Level: {risk_level.upper()}")
        
        output.append(f"\n💡 NOTE: This is a simplified analysis based on available data.")
        output.append(f"   For full OI analysis, ensure option chain API is working.")
        
        output.append("="*70)
        return "\n".join(output)


# Example usage
if __name__ == "__main__":
    print("Fallback OI Analysis Module")
    print("This module provides basic OI analysis when option chain API is not available")
