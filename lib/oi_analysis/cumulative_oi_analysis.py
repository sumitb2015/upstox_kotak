"""
Cumulative Open Interest Analysis Module
Provides multi-strike OI analysis for better overall market sentiment
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from lib.api.market_data import get_option_chain_atm
from lib.api.option_chain import get_option_chain_dataframe, get_atm_strike_from_chain


class CumulativeOIAnalyzer:
    """
    Analyzes cumulative OI across multiple strikes for overall market sentiment
    """
    
    def __init__(self, access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50"):
        """
        Initialize Cumulative OI Analyzer
        
        Args:
            access_token (str): Upstox API access token
            underlying_key (str): Underlying instrument key
        """
        self.access_token = access_token
        self.underlying_key = underlying_key
        self.oi_history = {}  # Store historical OI data
        self.cumulative_history = []  # Store cumulative analysis history
        
    def _get_current_expiry(self) -> str:
        """Get current expiry date"""
        today = datetime.now()
        # Simple logic to get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    def calculate_cumulative_oi(self, strikes_to_analyze: List[int] = None, 
                              option_chain_df: pd.DataFrame = None) -> Dict:
        """
        Calculate cumulative OI across multiple strikes
        
        Args:
            strikes_to_analyze (List[int]): Strikes to analyze (default: ATM ± 5)
            option_chain_df (pd.DataFrame): Option chain data (optional)
        
        Returns:
            Dict: Cumulative OI analysis
        """
        try:
            # Get option chain data if not provided
            if option_chain_df is None or option_chain_df.empty:
                expiry = self._get_current_expiry()
                option_chain_df = get_option_chain_atm(
                    self.access_token, self.underlying_key, expiry,
                    strikes_above=5, strikes_below=5
                )
            
            if option_chain_df.empty:
                return {"error": "No option chain data available"}
            
            # Get spot price
            spot_price = option_chain_df['underlying_spot'].iloc[0]
            
            # Default strikes if not provided
            if strikes_to_analyze is None:
                atm_strike = round(spot_price / 50) * 50
                strikes_to_analyze = [
                    atm_strike - 250, atm_strike - 200, atm_strike - 150,
                    atm_strike - 100, atm_strike - 50, atm_strike,
                    atm_strike + 50, atm_strike + 100, atm_strike + 150,
                    atm_strike + 200, atm_strike + 250
                ]
            
            # Initialize cumulative counters
            total_call_oi = 0
            total_put_oi = 0
            total_call_prev_oi = 0
            total_put_prev_oi = 0
            total_call_volume = 0
            total_put_volume = 0
            
            strike_details = []
            strikes_found = 0
            
            # Analyze each strike
            for strike in strikes_to_analyze:
                strike_data = option_chain_df[option_chain_df['strike_price'] == strike]
                
                if not strike_data.empty:
                    # Get call and put data
                    call_data = strike_data[strike_data['type'] == 'call']
                    put_data = strike_data[strike_data['type'] == 'put']
                    
                    if not call_data.empty and not put_data.empty:
                        call_row = call_data.iloc[0]
                        put_row = put_data.iloc[0]
                        
                        # Add to cumulative totals
                        total_call_oi += call_row['oi']
                        total_put_oi += put_row['oi']
                        total_call_prev_oi += call_row['prev_oi']
                        total_put_prev_oi += put_row['prev_oi']
                        total_call_volume += call_row['volume']
                        total_put_volume += put_row['volume']
                        
                        # Store strike details
                        strike_details.append({
                            'strike': strike,
                            'call_oi': call_row['oi'],
                            'put_oi': put_row['oi'],
                            'call_prev_oi': call_row['prev_oi'],
                            'put_prev_oi': put_row['prev_oi'],
                            'call_oi_change': call_row['oi'] - call_row['prev_oi'],
                            'put_oi_change': put_row['oi'] - put_row['prev_oi'],
                            'call_oi_change_pct': ((call_row['oi'] - call_row['prev_oi']) / call_row['prev_oi'] * 100) if call_row['prev_oi'] > 0 else 0,
                            'put_oi_change_pct': ((put_row['oi'] - put_row['prev_oi']) / put_row['prev_oi'] * 100) if put_row['prev_oi'] > 0 else 0,
                            'call_ltp': call_row['ltp'],
                            'put_ltp': put_row['ltp'],
                            'call_prev_ltp': call_row['prev_ltp'] if 'prev_ltp' in call_row else 0,
                            'put_prev_ltp': put_row['prev_ltp'] if 'prev_ltp' in put_row else 0
                        })
                        
                        strikes_found += 1
            
            if strikes_found == 0:
                return {"error": "No valid strikes found for analysis"}
            
            # Calculate cumulative changes
            total_call_oi_change = total_call_oi - total_call_prev_oi
            total_put_oi_change = total_put_oi - total_put_prev_oi
            
            total_call_oi_change_pct = (total_call_oi_change / total_call_prev_oi * 100) if total_call_prev_oi > 0 else 0
            total_put_oi_change_pct = (total_put_oi_change / total_put_prev_oi * 100) if total_put_prev_oi > 0 else 0
            
            # Calculate Put-Call OI Ratio (PCR)
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            change_pcr = total_put_oi_change / total_call_oi_change if total_call_oi_change > 0 else 0
            
            # Calculate net OI change
            net_oi_change = total_put_oi_change - total_call_oi_change
            net_oi_change_pct = total_put_oi_change_pct - total_call_oi_change_pct
            
            return {
                'timestamp': datetime.now(),
                'spot_price': spot_price,
                'strikes_analyzed': strikes_found,
                'strike_range': f"{min(strikes_to_analyze)}-{max(strikes_to_analyze)}",
                
                # Cumulative totals
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'total_call_prev_oi': total_call_prev_oi,
                'total_put_prev_oi': total_put_prev_oi,
                'total_call_volume': total_call_volume,
                'total_put_volume': total_put_volume,
                
                # Changes
                'total_call_oi_change': total_call_oi_change,
                'total_put_oi_change': total_put_oi_change,
                'total_call_oi_change_pct': total_call_oi_change_pct,
                'total_put_oi_change_pct': total_put_oi_change_pct,
                'net_oi_change': net_oi_change,
                'net_oi_change_pct': net_oi_change_pct,
                
                # Ratios
                'pcr': pcr,
                'change_pcr': change_pcr,
                'call_put_oi_ratio': total_call_oi / total_put_oi if total_put_oi > 0 else 0,
                
                # Strike details
                'strike_details': strike_details
            }
            
        except Exception as e:
            return {"error": f"Error calculating cumulative OI: {str(e)}"}
    
    def get_overall_sentiment(self, cumulative_data: Dict = None) -> Dict:
        """
        Determine overall market sentiment based on cumulative OI data
        
        Args:
            cumulative_data (Dict): Cumulative OI data (optional)
        
        Returns:
            Dict: Overall sentiment analysis
        """
        try:
            if cumulative_data is None:
                cumulative_data = self.calculate_cumulative_oi()
            
            if "error" in cumulative_data:
                return cumulative_data
            
            # Extract key metrics
            call_oi_change_pct = cumulative_data['total_call_oi_change_pct']
            put_oi_change_pct = cumulative_data['total_put_oi_change_pct']
            net_oi_change_pct = cumulative_data['net_oi_change_pct']
            pcr = cumulative_data['pcr']
            
            # Initialize sentiment signals
            bullish_signals = 0
            bearish_signals = 0
            # Analyze cumulative OI changes with a better understanding of buildup
            # If Put OI is building much faster than Call OI AND underlying is supportive (Short Build on Puts)
            # we consider it bullish for sellers.
            
            # Use total change for a broad view
            if put_oi_change_pct > call_oi_change_pct + 5:
                bullish_signals += 2
            elif call_oi_change_pct > put_oi_change_pct + 5:
                bearish_signals += 2
                
            # PCR trend
            if pcr > 1.3:
                bullish_signals += 1
            elif pcr < 0.7:
                bearish_signals += 1
            
            # Analyze PCR
            if pcr > 1.2:  # High PCR (more puts than calls)
                bullish_signals += 1  # More put buying (good for put sellers)
            elif pcr < 0.8:  # Low PCR (more calls than puts)
                bearish_signals += 1  # More call buying (bad for call sellers)
            
            # Analyze net OI change
            if net_oi_change_pct > 5:  # Net put OI building
                bullish_signals += 1
            elif net_oi_change_pct < -5:  # Net call OI building
                bearish_signals += 1
            
            # Determine overall sentiment
            if bullish_signals > bearish_signals + 2:
                overall_sentiment = "bullish_for_sellers"
                sentiment_strength = "strong"
            elif bullish_signals > bearish_signals:
                overall_sentiment = "bullish_for_sellers"
                sentiment_strength = "moderate"
            elif bearish_signals > bullish_signals + 2:
                overall_sentiment = "bearish_for_sellers"
                sentiment_strength = "strong"
            elif bearish_signals > bullish_signals:
                overall_sentiment = "bearish_for_sellers"
                sentiment_strength = "moderate"
            else:
                overall_sentiment = "neutral"
                sentiment_strength = "balanced"
            
            # Calculate sentiment score (0-100)
            sentiment_score = 50  # Base neutral score
            if overall_sentiment == "bullish_for_sellers":
                sentiment_score = 50 + min(30, (bullish_signals - bearish_signals) * 5)
            elif overall_sentiment == "bearish_for_sellers":
                sentiment_score = 50 - min(30, (bearish_signals - bullish_signals) * 5)
            
            return {
                'overall_sentiment': overall_sentiment,
                'sentiment_strength': sentiment_strength,
                'sentiment_score': sentiment_score,
                'bullish_signals': bullish_signals,
                'bearish_signals': bearish_signals,
                'analysis_details': {
                    'call_oi_trend': 'decreasing' if call_oi_change_pct < -2 else 'increasing' if call_oi_change_pct > 2 else 'stable',
                    'put_oi_trend': 'decreasing' if put_oi_change_pct < -2 else 'increasing' if put_oi_change_pct > 2 else 'stable',
                    'pcr_level': 'high' if pcr > 1.2 else 'low' if pcr < 0.8 else 'normal',
                    'net_oi_trend': 'put_building' if net_oi_change_pct > 2 else 'call_building' if net_oi_change_pct < -2 else 'balanced'
                },
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error determining overall sentiment: {str(e)}"}
    
    def analyze_oi_trends(self, cumulative_data: Dict = None) -> Dict:
        """
        Analyze OI trends and patterns
        
        Args:
            cumulative_data (Dict): Cumulative OI data (optional)
        
        Returns:
            Dict: OI trend analysis
        """
        try:
            if cumulative_data is None:
                cumulative_data = self.calculate_cumulative_oi()
            
            if "error" in cumulative_data:
                return cumulative_data
            
            # Analyze individual strike patterns
            strike_details = cumulative_data['strike_details']
            
            # Categorize strikes by OI activity
            high_oi_change_strikes = []
            low_oi_change_strikes = []
            call_dominant_strikes = []
            put_dominant_strikes = []
            
            for strike_data in strike_details:
                strike = strike_data['strike']
                call_change_pct = strike_data['call_oi_change_pct']
                put_change_pct = strike_data['put_oi_change_pct']
                
                # High OI change strikes
                if abs(call_change_pct) > 10 or abs(put_change_pct) > 10:
                    high_oi_change_strikes.append({
                        'strike': strike,
                        'call_change_pct': call_change_pct,
                        'put_change_pct': put_change_pct
                    })
                
                # Low OI change strikes
                if abs(call_change_pct) < 2 and abs(put_change_pct) < 2:
                    low_oi_change_strikes.append(strike)
                
                # Call dominant strikes
                if call_change_pct > put_change_pct + 5:
                    call_dominant_strikes.append(strike)
                
                # Put dominant strikes
                if put_change_pct > call_change_pct + 5:
                    put_dominant_strikes.append(strike)
            
            # Determine overall trend
            total_call_change = cumulative_data['total_call_oi_change_pct']
            total_put_change = cumulative_data['total_put_oi_change_pct']
            
            if total_call_change > 5 and total_put_change > 5:
                overall_trend = "both_building"
            elif total_call_change < -5 and total_put_change < -5:
                overall_trend = "both_unwinding"
            elif total_call_change > 5:
                overall_trend = "call_building"
            elif total_put_change > 5:
                overall_trend = "put_building"
            elif total_call_change < -5:
                overall_trend = "call_unwinding"
            elif total_put_change < -5:
                overall_trend = "put_unwinding"
            else:
                overall_trend = "stable"
            
            return {
                'overall_trend': overall_trend,
                'high_activity_strikes': high_oi_change_strikes,
                'low_activity_strikes': low_oi_change_strikes,
                'call_dominant_strikes': call_dominant_strikes,
                'put_dominant_strikes': put_dominant_strikes,
                'trend_strength': 'strong' if len(high_oi_change_strikes) > 3 else 'moderate' if len(high_oi_change_strikes) > 1 else 'weak',
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error analyzing OI trends: {str(e)}"}
    


    def get_strike_pcr_structure(self, offset: int = 600) -> Dict:
        """
        Get PCR for strikes within a range from ATM.
        
        Args:
            offset (int): Offset from ATM (e.g., 600) to filter strikes [ATM-offset, ATM+offset]
            
        Returns:
            Dict: Structure containing ATM, offset range, and per-strike PCR data.
        """
        try:
            # 1. Fetch Option Chain (Pandas DataFrame - Wide Format)
            expiry = self._get_current_expiry()
            df = get_option_chain_dataframe(
                self.access_token, self.underlying_key, expiry
            )
            
            if df is None or df.empty:
                return {"error": "Option chain data empty"}
            
            # 2. Find ATM
            # Use the helper from option_chain module which handles spot price extraction
            atm = get_atm_strike_from_chain(df)
            if not atm:
                # Fallback if helper fails (unlikely if df not empty)
                spot = df['spot_price'].iloc[0]
                strike_step = 50 
                if "Bank" in self.underlying_key: strike_step = 100
                atm = round(spot / strike_step) * strike_step
            else:
                spot = df['spot_price'].iloc[0]

            min_strike = atm - offset
            max_strike = atm + offset
            
            # 3. Filter Strikes
            subset = df[(df['strike_price'] >= min_strike) & (df['strike_price'] <= max_strike)].copy()
            
            # 4. Build Result Structure
            strike_pcr_map = {}
            pcr_data_list = []
            
            for _, row in subset.iterrows():
                strike = int(row['strike_price'])
                
                # Prefer API PCR if available and valid
                api_pcr = row.get('pcr')
                
                # Calculate manually as fallback or verification
                ce_oi = row.get('ce_oi', 0)
                pe_oi = row.get('pe_oi', 0)
                calc_pcr = pe_oi / ce_oi if ce_oi > 0 else 0.0
                
                # Use API PCR if it exists, else calculated
                final_pcr = api_pcr if (api_pcr is not None and not pd.isna(api_pcr)) else calc_pcr
                
                pcr_data = {
                    'strike': strike,
                    'pcr': float(final_pcr),
                    'ce_oi': float(ce_oi),
                    'pe_oi': float(pe_oi),
                    'distance_from_atm': strike - atm
                }
                
                strike_pcr_map[strike] = final_pcr
                pcr_data_list.append(pcr_data)
                
            return {
                'timestamp': datetime.now(),
                'spot': spot,
                'atm': atm,
                'offset': offset,
                'strikes_count': len(pcr_data_list),
                'pcr_map': strike_pcr_map,  # {24000: 0.8, ...} Easy lookup
                'details': pcr_data_list    # List of dicts with more info
            }

        except Exception as e:
            return {"error": f"Error tracking PCR structure: {str(e)}"}

    def get_oi_momentum(self, lookback_periods: int = 3) -> Dict:
        """
        Calculate OI momentum over time
        
        Args:
            lookback_periods (int): Number of periods to look back
        
        Returns:
            Dict: OI momentum analysis
        """
        try:
            if len(self.cumulative_history) < lookback_periods:
                return {"error": f"Insufficient history data. Need {lookback_periods} periods, have {len(self.cumulative_history)}"}
            
            # Get recent data
            recent_data = self.cumulative_history[-lookback_periods:]
            
            # Calculate momentum indicators
            call_oi_momentum = []
            put_oi_momentum = []
            pcr_momentum = []
            
            for data in recent_data:
                call_oi_momentum.append(data['total_call_oi_change_pct'])
                put_oi_momentum.append(data['total_put_oi_change_pct'])
                pcr_momentum.append(data['pcr'])
            
            # Calculate momentum trends
            call_momentum_trend = 'increasing' if call_oi_momentum[-1] > call_oi_momentum[0] else 'decreasing'
            put_momentum_trend = 'increasing' if put_oi_momentum[-1] > put_oi_momentum[0] else 'decreasing'
            pcr_momentum_trend = 'increasing' if pcr_momentum[-1] > pcr_momentum[0] else 'decreasing'
            
            # Calculate momentum strength
            call_momentum_strength = abs(call_oi_momentum[-1] - call_oi_momentum[0])
            put_momentum_strength = abs(put_oi_momentum[-1] - put_oi_momentum[0])
            
            return {
                'call_momentum_trend': call_momentum_trend,
                'put_momentum_trend': put_momentum_trend,
                'pcr_momentum_trend': pcr_momentum_trend,
                'call_momentum_strength': call_momentum_strength,
                'put_momentum_strength': put_momentum_strength,
                'overall_momentum': 'strong' if (call_momentum_strength + put_momentum_strength) > 10 else 'moderate' if (call_momentum_strength + put_momentum_strength) > 5 else 'weak',
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            return {"error": f"Error calculating OI momentum: {str(e)}"}
    
    def format_cumulative_analysis(self, cumulative_data: Dict, sentiment_data: Dict, trend_data: Dict) -> str:
        """
        Format cumulative OI analysis for display
        
        Args:
            cumulative_data (Dict): Cumulative OI data
            sentiment_data (Dict): Sentiment analysis
            trend_data (Dict): Trend analysis
        
        Returns:
            str: Formatted analysis string
        """
        if "error" in cumulative_data:
            return f"❌ Error: {cumulative_data['error']}"
        
        output = []
        output.append("="*70)
        output.append("CUMULATIVE OI ANALYSIS - MULTI-STRIKE SENTIMENT")
        output.append("="*70)
        
        # Overall summary
        sentiment = sentiment_data.get('overall_sentiment', 'unknown')
        sentiment_strength = sentiment_data.get('sentiment_strength', 'unknown')
        sentiment_score = sentiment_data.get('sentiment_score', 50)
        
        sentiment_emoji = "🟢" if sentiment == "bullish_for_sellers" else "🔴" if sentiment == "bearish_for_sellers" else "🟡"
        
        output.append(f"\n📊 OVERALL SENTIMENT: {sentiment_emoji} {sentiment.upper()} ({sentiment_strength})")
        output.append(f"🎯 Sentiment Score: {sentiment_score:.1f}/100")
        
        # Cumulative OI data
        output.append(f"\n📈 CUMULATIVE OI DATA:")
        output.append(f"   Total Call OI: {cumulative_data['total_call_oi']:,} ({cumulative_data['total_call_oi_change_pct']:+.1f}%)")
        output.append(f"   Total Put OI: {cumulative_data['total_put_oi']:,} ({cumulative_data['total_put_oi_change_pct']:+.1f}%)")
        output.append(f"   Net OI Change: {cumulative_data['net_oi_change']:+,} ({cumulative_data['net_oi_change_pct']:+.1f}%)")
        output.append(f"   Put-Call Ratio: {cumulative_data['pcr']:.2f}")
        
        # Trend analysis
        overall_trend = trend_data.get('overall_trend', 'unknown')
        trend_strength = trend_data.get('trend_strength', 'unknown')
        
        output.append(f"\n📊 OI TREND ANALYSIS:")
        output.append(f"   Overall Trend: {overall_trend.replace('_', ' ').title()}")
        output.append(f"   Trend Strength: {trend_strength.title()}")
        
        # High activity strikes
        high_activity = trend_data.get('high_activity_strikes', [])
        if high_activity:
            output.append(f"\n🔥 HIGH ACTIVITY STRIKES:")
            for strike_data in high_activity[:3]:  # Show top 3
                strike = strike_data['strike']
                call_change = strike_data['call_change_pct']
                put_change = strike_data['put_change_pct']
                output.append(f"   {strike}: Call {call_change:+.1f}%, Put {put_change:+.1f}%")
        
        # Analysis details
        analysis_details = sentiment_data.get('analysis_details', {})
        output.append(f"\n🔍 ANALYSIS DETAILS:")
        output.append(f"   Call OI Trend: {analysis_details.get('call_oi_trend', 'unknown').title()}")
        output.append(f"   Put OI Trend: {analysis_details.get('put_oi_trend', 'unknown').title()}")
        output.append(f"   PCR Level: {analysis_details.get('pcr_level', 'unknown').title()}")
        output.append(f"   Net OI Trend: {analysis_details.get('net_oi_trend', 'unknown').replace('_', ' ').title()}")
        
        output.append("="*70)
        return "\n".join(output)


# Example usage and testing
if __name__ == "__main__":
    print("Cumulative OI Analysis Module")
    print("This module should be imported and used from the main strategy")
