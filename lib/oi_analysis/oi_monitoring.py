"""
Real-time Open Interest Monitoring for Option Selling Strategy
Integrates with existing straddle strategy for enhanced decision making
"""

import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from lib.oi_analysis.oi_analysis import OIAnalyzer
from lib.api.market_data import get_option_chain_atm


class OIMonitor:
    """
    Real-time OI monitoring for option selling strategy
    """
    
    def __init__(self, access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50"):
        """
        Initialize OI Monitor
        
        Args:
            access_token (str): Upstox API access token
            underlying_key (str): Underlying instrument key
        """
        self.access_token = access_token
        self.underlying_key = underlying_key
        self.analyzer = OIAnalyzer(access_token, underlying_key)
        
        # Monitoring data storage
        self.oi_history = {}  # {strike: {timestamp: oi_data}}
        self.sentiment_history = []  # List of sentiment snapshots
        self.alerts = []  # List of OI alerts
        
        # Monitoring parameters
        self.monitoring_interval = 30  # seconds
        self.alert_thresholds = {
            'oi_change_pct': 20,  # Alert if OI changes by 20%
            'sentiment_shift': True,  # Alert on sentiment changes
            'unusual_activity': True  # Alert on unusual OI patterns
        }
        
        # Current monitoring state
        self.is_monitoring = False
        self.monitored_strikes = []
        self.last_sentiment = None
        
    def start_monitoring(self, strikes_to_monitor: List[int], 
                        monitoring_interval: int = 30) -> bool:
        """
        Start real-time OI monitoring for specified strikes
        
        Args:
            strikes_to_monitor (List[int]): List of strikes to monitor
            monitoring_interval (int): Monitoring interval in seconds
        
        Returns:
            bool: True if monitoring started successfully
        """
        try:
            self.monitored_strikes = strikes_to_monitor
            self.monitoring_interval = monitoring_interval
            self.is_monitoring = True
            
            print(f"🔍 Starting OI monitoring for strikes: {strikes_to_monitor}")
            print(f"⏱️  Monitoring interval: {monitoring_interval} seconds")
            
            return True
            
        except Exception as e:
            print(f"❌ Error starting OI monitoring: {e}")
            return False
    
    def stop_monitoring(self):
        """Stop OI monitoring"""
        self.is_monitoring = False
        print("⏹️  OI monitoring stopped")
    
    def get_current_oi_snapshot(self, strikes: List[int] = None) -> Dict:
        """
        Get current OI snapshot for specified strikes
        
        Args:
            strikes (List[int]): Strikes to analyze (default: monitored strikes)
        
        Returns:
            Dict: Current OI snapshot
        """
        try:
            if strikes is None:
                strikes = self.monitored_strikes
            
            if not strikes:
                return {"error": "No strikes specified for monitoring"}
            
            # Get option chain data
            expiry = self._get_current_expiry()
            option_chain_df = get_option_chain_atm(
                self.access_token, self.underlying_key, expiry,
                strikes_above=10, strikes_below=10
            )
            
            if option_chain_df.empty:
                return {"error": "No option chain data available"}
            
            # Analyze each strike
            strike_data = {}
            for strike in strikes:
                sentiment = self.analyzer.analyze_strike_sentiment(option_chain_df, strike)
                if "error" not in sentiment:
                    strike_data[strike] = sentiment
            
            # Store in history
            timestamp = datetime.now()
            for strike, data in strike_data.items():
                if strike not in self.oi_history:
                    self.oi_history[strike] = {}
                self.oi_history[strike][timestamp] = data
            
            return {
                "timestamp": timestamp,
                "strikes": strike_data,
                "monitoring_active": self.is_monitoring
            }
            
        except Exception as e:
            return {"error": f"Error getting OI snapshot: {str(e)}"}
    
    def check_oi_alerts(self, current_snapshot: Dict) -> List[Dict]:
        """
        Check for OI alerts based on current snapshot
        
        Args:
            current_snapshot (Dict): Current OI snapshot
        
        Returns:
            List[Dict]: List of alerts
        """
        alerts = []
        
        try:
            if "error" in current_snapshot:
                return alerts
            
            timestamp = current_snapshot["timestamp"]
            strikes_data = current_snapshot["strikes"]
            
            for strike, data in strikes_data.items():
                # Check OI change threshold
                if abs(data['call_oi_change_pct']) > self.alert_thresholds['oi_change_pct']:
                    alerts.append({
                        "type": "oi_change",
                        "strike": strike,
                        "option_type": "call",
                        "change_pct": data['call_oi_change_pct'],
                        "activity": data['call_oi_activity'],
                        "timestamp": timestamp,
                        "severity": "high" if abs(data['call_oi_change_pct']) > 30 else "medium"
                    })
                
                if abs(data['put_oi_change_pct']) > self.alert_thresholds['oi_change_pct']:
                    alerts.append({
                        "type": "oi_change",
                        "strike": strike,
                        "option_type": "put",
                        "change_pct": data['put_oi_change_pct'],
                        "activity": data['put_oi_activity'],
                        "timestamp": timestamp,
                        "severity": "high" if abs(data['put_oi_change_pct']) > 30 else "medium"
                    })
                
                # Check sentiment changes
                if self.alert_thresholds['sentiment_shift'] and self.last_sentiment:
                    if strike in self.last_sentiment.get('strikes', {}):
                        old_sentiment = self.last_sentiment['strikes'][strike]['strike_sentiment']
                        new_sentiment = data['strike_sentiment']
                        
                        if old_sentiment != new_sentiment:
                            alerts.append({
                                "type": "sentiment_change",
                                "strike": strike,
                                "old_sentiment": old_sentiment,
                                "new_sentiment": new_sentiment,
                                "timestamp": timestamp,
                                "severity": "medium"
                            })
            
            # Store alerts
            self.alerts.extend(alerts)
            
            return alerts
            
        except Exception as e:
            print(f"❌ Error checking OI alerts: {e}")
            return alerts
    
    def get_oi_trend_analysis(self, strike: int, lookback_minutes: int = 30) -> Dict:
        """
        Get OI trend analysis for a specific strike
        
        Args:
            strike (int): Strike price to analyze
            lookback_minutes (int): Lookback period in minutes
        
        Returns:
            Dict: Trend analysis
        """
        try:
            if strike not in self.oi_history:
                return {"error": f"No historical data for strike {strike}"}
            
            # Get data within lookback period
            cutoff_time = datetime.now() - timedelta(minutes=lookback_minutes)
            recent_data = {
                timestamp: data for timestamp, data in self.oi_history[strike].items()
                if timestamp >= cutoff_time
            }
            
            if len(recent_data) < 2:
                return {"error": "Insufficient data for trend analysis"}
            
            # Sort by timestamp
            sorted_data = sorted(recent_data.items())
            
            # Analyze trends
            call_oi_trend = []
            put_oi_trend = []
            call_activity_trend = []
            put_activity_trend = []
            
            for timestamp, data in sorted_data:
                call_oi_trend.append(data['call_oi'])
                put_oi_trend.append(data['put_oi'])
                call_activity_trend.append(data['call_oi_activity'])
                put_activity_trend.append(data['put_oi_activity'])
            
            # Calculate trend direction
            call_oi_direction = "increasing" if call_oi_trend[-1] > call_oi_trend[0] else "decreasing"
            put_oi_direction = "increasing" if put_oi_trend[-1] > put_oi_trend[0] else "decreasing"
            
            # Calculate trend strength
            call_oi_change = ((call_oi_trend[-1] - call_oi_trend[0]) / call_oi_trend[0] * 100) if call_oi_trend[0] > 0 else 0
            put_oi_change = ((put_oi_trend[-1] - put_oi_trend[0]) / put_oi_trend[0] * 100) if put_oi_trend[0] > 0 else 0
            
            # Determine overall trend sentiment
            trend_sentiment = self._analyze_trend_sentiment(
                call_oi_direction, put_oi_direction, call_oi_change, put_oi_change,
                call_activity_trend[-1], put_activity_trend[-1]
            )
            
            return {
                "strike": strike,
                "lookback_minutes": lookback_minutes,
                "data_points": len(sorted_data),
                "call_oi_trend": {
                    "direction": call_oi_direction,
                    "change_pct": call_oi_change,
                    "current_activity": call_activity_trend[-1]
                },
                "put_oi_trend": {
                    "direction": put_oi_direction,
                    "change_pct": put_oi_change,
                    "current_activity": put_activity_trend[-1]
                },
                "trend_sentiment": trend_sentiment,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error in trend analysis: {str(e)}"}
    
    def _analyze_trend_sentiment(self, call_direction: str, put_direction: str,
                               call_change: float, put_change: float,
                               call_activity: str, put_activity: str) -> str:
        """
        Analyze trend sentiment for option sellers
        
        Args:
            call_direction (str): Call OI trend direction
            put_direction (str): Put OI trend direction
            call_change (float): Call OI change percentage
            put_change (float): Put OI change percentage
            call_activity (str): Current call OI activity
            put_activity (str): Current put OI activity
        
        Returns:
            str: Trend sentiment
        """
        bullish_signals = 0
        bearish_signals = 0
        
        # Analyze call trends
        if call_activity in ["long_unwinding", "short_build"]:
            bullish_signals += 1  # Favorable for call sellers
        elif call_activity in ["long_build", "short_covering"]:
            bearish_signals += 1  # Unfavorable for call sellers
        
        # Analyze put trends
        if put_activity in ["long_unwinding", "short_build"]:
            bullish_signals += 1  # Favorable for put sellers
        elif put_activity in ["long_build", "short_covering"]:
            bearish_signals += 1  # Unfavorable for put sellers
        
        # Weight by change magnitude
        if abs(call_change) > 15:
            if call_activity in ["long_unwinding", "short_build"]:
                bullish_signals += 1
            elif call_activity in ["long_build", "short_covering"]:
                bearish_signals += 1
        
        if abs(put_change) > 15:
            if put_activity in ["long_unwinding", "short_build"]:
                bullish_signals += 1
            elif put_activity in ["long_build", "short_covering"]:
                bearish_signals += 1
        
        # Determine sentiment
        if bullish_signals > bearish_signals:
            return "bullish_for_sellers"
        elif bearish_signals > bullish_signals:
            return "bearish_for_sellers"
        else:
            return "neutral"
    
    def get_selling_recommendations(self, current_snapshot: Dict) -> Dict:
        """
        Get selling recommendations based on OI analysis
        
        Args:
            current_snapshot (Dict): Current OI snapshot
        
        Returns:
            Dict: Selling recommendations
        """
        try:
            if "error" in current_snapshot:
                return {"error": current_snapshot["error"]}
            
            recommendations = {
                "timestamp": current_snapshot["timestamp"],
                "strike_recommendations": {},
                "overall_recommendation": "neutral",
                "risk_level": "medium"
            }
            
            strikes_data = current_snapshot["strikes"]
            bullish_strikes = 0
            bearish_strikes = 0
            
            for strike, data in strikes_data.items():
                # Calculate selling score
                selling_score = self.analyzer._calculate_selling_score(data)
                
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
                
                recommendations["strike_recommendations"][strike] = {
                    "recommendation": recommendation,
                    "selling_score": selling_score,
                    "risk_level": risk_level,
                    "sentiment": data["strike_sentiment"],
                    "call_activity": data["call_oi_activity"],
                    "put_activity": data["put_oi_activity"],
                    "reasoning": self._get_recommendation_reasoning(data, selling_score)
                }
                
                # Count for overall recommendation
                if recommendation in ["strong_sell", "sell"]:
                    bullish_strikes += 1
                elif recommendation in ["strong_avoid", "avoid"]:
                    bearish_strikes += 1
            
            # Determine overall recommendation
            total_strikes = len(strikes_data)
            if bullish_strikes > total_strikes * 0.6:
                recommendations["overall_recommendation"] = "bullish_for_selling"
                recommendations["risk_level"] = "low"
            elif bearish_strikes > total_strikes * 0.6:
                recommendations["overall_recommendation"] = "bearish_for_selling"
                recommendations["risk_level"] = "high"
            else:
                recommendations["overall_recommendation"] = "neutral"
                recommendations["risk_level"] = "medium"
            
            return recommendations
            
        except Exception as e:
            return {"error": f"Error getting selling recommendations: {str(e)}"}
    
    def _get_recommendation_reasoning(self, data: Dict, selling_score: float) -> str:
        """
        Get reasoning for selling recommendation
        
        Args:
            data (Dict): Strike sentiment data
            selling_score (float): Calculated selling score
        
        Returns:
            str: Reasoning text
        """
        reasons = []
        
        # Sentiment reasoning
        if data["strike_sentiment"] == "bullish_for_sellers":
            reasons.append("Bullish sentiment for sellers")
        elif data["strike_sentiment"] == "bearish_for_sellers":
            reasons.append("Bearish sentiment for sellers")
        
        # Activity reasoning
        if data["call_oi_activity"] == "long_unwinding":
            reasons.append("Call buyers exiting (bullish)")
        elif data["call_oi_activity"] == "long_build":
            reasons.append("Call buyers accumulating (bearish)")
        elif data["call_oi_activity"] == "short_covering":
            reasons.append("Call sellers covering (bearish)")
        
        if data["put_oi_activity"] == "long_build":
            reasons.append("Put buyers accumulating (bearish)")
        elif data["put_oi_activity"] == "long_unwinding":
            reasons.append("Put buyers exiting (bullish)")
        elif data["put_oi_activity"] == "short_covering":
            reasons.append("Put sellers covering (bearish)")
        
        # Score reasoning
        if selling_score >= 70:
            reasons.append("High selling score - optimal conditions")
        elif selling_score <= 30:
            reasons.append("Low selling score - unfavorable conditions")
        
        return "; ".join(reasons) if reasons else "Neutral conditions"
    
    def _get_current_expiry(self) -> str:
        """
        Get current expiry date (simplified - you might want to enhance this)
        
        Returns:
            str: Expiry date in YYYY-MM-DD format
        """
        from datetime import datetime, timedelta
        today = datetime.now()
        # Simple logic to get next Thursday (typical NIFTY expiry)
        days_ahead = (3 - today.weekday()) % 7  # Thursday is 3
        if days_ahead == 0:  # If today is Thursday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    def format_monitoring_display(self, snapshot: Dict, recommendations: Dict = None) -> str:
        """
        Format monitoring data for display
        
        Args:
            snapshot (Dict): Current OI snapshot
            recommendations (Dict): Selling recommendations (optional)
        
        Returns:
            str: Formatted display string
        """
        if "error" in snapshot:
            return f"❌ Error: {snapshot['error']}"
        
        output = []
        output.append("="*70)
        output.append("REAL-TIME OI MONITORING (OPTION SELLING PERSPECTIVE)")
        output.append("="*70)
        
        timestamp = snapshot["timestamp"].strftime("%H:%M:%S")
        output.append(f"⏰ Timestamp: {timestamp}")
        output.append(f"🔍 Monitoring: {'Active' if snapshot['monitoring_active'] else 'Inactive'}")
        
        strikes_data = snapshot["strikes"]
        output.append(f"\n📊 MONITORED STRIKES ({len(strikes_data)}):")
        
        for strike, data in sorted(strikes_data.items()):
            sentiment_emoji = "🟢" if data['strike_sentiment'] == "bullish_for_sellers" else "🔴" if data['strike_sentiment'] == "bearish_for_sellers" else "🟡"
            
            output.append(f"\n  📍 Strike {strike}: {sentiment_emoji} {data['strike_sentiment']}")
            output.append(f"    📞 Call: {data['call_oi']:,} ({data['call_oi_change_pct']:+.1f}%) - {data['call_oi_activity']}")
            output.append(f"    📞 Put: {data['put_oi']:,} ({data['put_oi_change_pct']:+.1f}%) - {data['put_oi_activity']}")
            
            # Add recommendations if available
            if recommendations and "strike_recommendations" in recommendations:
                if strike in recommendations["strike_recommendations"]:
                    rec = recommendations["strike_recommendations"][strike]
                    rec_emoji = "🟢" if rec["recommendation"] in ["strong_sell", "sell"] else "🔴" if rec["recommendation"] in ["strong_avoid", "avoid"] else "🟡"
                    output.append(f"    🎯 Recommendation: {rec_emoji} {rec['recommendation']} (Score: {rec['selling_score']:.1f})")
        
        # Overall recommendation
        if recommendations and "overall_recommendation" in recommendations:
            overall_rec = recommendations["overall_recommendation"]
            rec_emoji = "🟢" if overall_rec == "bullish_for_selling" else "🔴" if overall_rec == "bearish_for_selling" else "🟡"
            output.append(f"\n🎯 OVERALL RECOMMENDATION: {rec_emoji} {overall_rec.upper()}")
            output.append(f"⚠️  Risk Level: {recommendations.get('risk_level', 'medium').upper()}")
        
        # Recent alerts
        if self.alerts:
            recent_alerts = [alert for alert in self.alerts if (datetime.now() - alert['timestamp']).seconds < 300]  # Last 5 minutes
            if recent_alerts:
                output.append(f"\n🚨 RECENT ALERTS ({len(recent_alerts)}):")
                for alert in recent_alerts[-3:]:  # Show last 3 alerts
                    alert_time = alert['timestamp'].strftime("%H:%M:%S")
                    severity_emoji = "🔴" if alert['severity'] == "high" else "🟡" if alert['severity'] == "medium" else "🟢"
                    output.append(f"  {severity_emoji} [{alert_time}] {alert['type']} - Strike {alert.get('strike', 'N/A')}")
        
        output.append("="*70)
        return "\n".join(output)


# Example usage and testing
if __name__ == "__main__":
    print("OI Monitoring Module for Option Selling Strategy")
    print("This module should be imported and used from main.py")
