"""
OI-Guided Strangle Analyzer
Finds optimal CE and PE strikes based on OI analysis for strangle strategies
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from lib.api.market_data import get_option_chain_atm


class OIStrangleAnalyzer:
    """
    Analyzes OI data to find optimal strikes for strangle strategies
    """
    
    def __init__(self, access_token: str, underlying_key: str = "NSE_INDEX|Nifty 50"):
        """
        Initialize OI Strangle Analyzer
        
        Args:
            access_token (str): Upstox API access token
            underlying_key (str): Underlying instrument key
        """
        self.access_token = access_token
        self.underlying_key = underlying_key
        self.strangle_history = []  # Store strangle analysis history
        
    def _get_current_expiry(self) -> str:
        """Get current expiry date"""
        today = datetime.now()
        # Simple logic to get next Tuesday (current NIFTY expiry)
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0:  # If today is Tuesday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    def analyze_strikes_for_strangle(self, strikes_to_analyze: List[int] = None, 
                                   option_chain_df: pd.DataFrame = None) -> Dict:
        """
        Analyze strikes to find optimal CE and PE strikes for strangle
        
        Args:
            strikes_to_analyze (List[int]): Strikes to analyze (default: ATM ± 10)
            option_chain_df (pd.DataFrame): Option chain data (optional)
        
        Returns:
            Dict: Strangle analysis with optimal strikes
        """
        try:
            # Get option chain data if not provided
            if option_chain_df is None or option_chain_df.empty:
                expiry = self._get_current_expiry()
                option_chain_df = get_option_chain_atm(
                    self.access_token, self.underlying_key, expiry,
                    strikes_above=10, strikes_below=10
                )
            
            if option_chain_df.empty:
                return {"error": "No option chain data available"}
            
            # Get spot price
            spot_price = option_chain_df['underlying_spot'].iloc[0]
            
            # Default strikes if not provided (focused around ATM, max 4 strikes away)
            if strikes_to_analyze is None:
                atm_strike = round(spot_price / 50) * 50
                strikes_to_analyze = [
                    atm_strike - 200, atm_strike - 150, atm_strike - 100,
                    atm_strike - 50, atm_strike,
                    atm_strike + 50, atm_strike + 100, atm_strike + 150,
                    atm_strike + 200
                ]
            
            # Analyze each strike for CE and PE separately
            strike_analysis = []
            
            for strike in strikes_to_analyze:
                strike_data = option_chain_df[option_chain_df['strike_price'] == strike]
                
                if not strike_data.empty:
                    # Get call and put data
                    call_data = strike_data[strike_data['type'] == 'call']
                    put_data = strike_data[strike_data['type'] == 'put']
                    
                    if not call_data.empty and not put_data.empty:
                        call_row = call_data.iloc[0]
                        put_row = put_data.iloc[0]
                        
                        # Calculate OI change percentages with division by zero protection
                        call_oi_change_pct = ((call_row['oi'] - call_row['prev_oi']) / call_row['prev_oi'] * 100) if call_row['prev_oi'] > 0 else 0
                        put_oi_change_pct = ((put_row['oi'] - put_row['prev_oi']) / put_row['prev_oi'] * 100) if put_row['prev_oi'] > 0 else 0
                        
                        # Calculate price changes from current and previous LTP (daily)
                        call_price_change = call_row['ltp'] - call_row['prev_ltp'] if 'prev_ltp' in call_row and call_row['prev_ltp'] > 0 else 0
                        put_price_change = put_row['ltp'] - put_row['prev_ltp'] if 'prev_ltp' in put_row and put_row['prev_ltp'] > 0 else 0
                        
                        # Calculate selling scores for each option type
                        call_selling_score = self._calculate_call_selling_score(call_row, call_oi_change_pct, call_price_change)
                        put_selling_score = self._calculate_put_selling_score(put_row, put_oi_change_pct, put_price_change)
                        
                        # Calculate distance from ATM
                        distance_from_atm = abs(strike - spot_price)
                        
                        strike_analysis.append({
                            'strike': strike,
                            'distance_from_atm': distance_from_atm,
                            'call_oi': call_row['oi'],
                            'call_prev_oi': call_row['prev_oi'],
                            'call_oi_change_pct': call_oi_change_pct,
                            'call_ltp': call_row['ltp'],
                            'call_selling_score': call_selling_score,
                            'put_oi': put_row['oi'],
                            'put_prev_oi': put_row['prev_oi'],
                            'put_oi_change_pct': put_oi_change_pct,
                            'put_ltp': put_row['ltp'],
                            'put_selling_score': put_selling_score,
                            'combined_score': (call_selling_score + put_selling_score) / 2
                        })
            
            if not strike_analysis:
                return {"error": "No valid strikes found for analysis"}
            
            # Find optimal strikes
            optimal_ce_strike = self._find_optimal_ce_strike(strike_analysis, spot_price)
            optimal_pe_strike = self._find_optimal_pe_strike(strike_analysis, spot_price)
            
            # Validate that CE and PE are different strikes (strangle requirement)
            if optimal_ce_strike['strike'] == optimal_pe_strike['strike']:
                return {"error": f"Invalid strangle: CE and PE cannot be same strike ({optimal_ce_strike['strike']})"}
            
            # Validate that CE is above ATM and PE is below ATM
            atm_strike = round(spot_price / 50) * 50
            if optimal_ce_strike['strike'] <= atm_strike:
                return {"error": f"Invalid strangle: CE strike ({optimal_ce_strike['strike']}) must be above ATM ({atm_strike})"}
            
            if optimal_pe_strike['strike'] >= atm_strike:
                return {"error": f"Invalid strangle: PE strike ({optimal_pe_strike['strike']}) must be below ATM ({atm_strike})"}
            
            # Calculate strangle metrics
            strangle_analysis = self._calculate_strangle_metrics(
                optimal_ce_strike, optimal_pe_strike, spot_price
            )
            
            return {
                'timestamp': datetime.now(),
                'spot_price': spot_price,
                'atm_strike': round(spot_price / 50) * 50,
                'strikes_analyzed': len(strike_analysis),
                'strike_analysis': strike_analysis,
                'optimal_ce_strike': optimal_ce_strike,
                'optimal_pe_strike': optimal_pe_strike,
                'strangle_analysis': strangle_analysis,
                'recommendation': self._get_strangle_recommendation(strangle_analysis),
                'filtering_criteria': {
                    'min_premium': 8.0,
                    'max_strikes_from_atm': 4,
                    'ce_must_be_otm': True,
                    'pe_must_be_otm': True
                }
            }
            
        except Exception as e:
            return {"error": f"Error analyzing strikes for strangle: {str(e)}"}
    
    def _calculate_call_selling_score(self, call_row: pd.Series, oi_change_pct: float, price_change: float = 0) -> float:
        """
        Calculate selling score for call options (higher = better for selling)
        
        Args:
            call_row (pd.Series): Call option data
            oi_change_pct (float): OI change percentage
            price_change (float): Price change (LTP - Prev Close)
        
        Returns:
            float: Selling score (0-100)
        """
        score = 50  # Base score
        
        # Determine buildup type
        if oi_change_pct > 5:
            if price_change > 0: # Long Build (Aggressive buying)
                score -= 20
            else: # Short Build (Aggressive selling)
                score += 20
        elif oi_change_pct < -5:
            if price_change < 0: # Long Unwinding (Buyers exiting)
                score += 10
            else: # Short Covering (Sellers exiting)
                score -= 10
        
        # Price analysis for premium attractiveness
        ltp = call_row['ltp']
        if 25 <= ltp <= 150:
            score += 10 # Ideal premium range for strangles
        
        # Liquidity analysis
        volume = call_row['volume']
        if volume > 500:
            score += 5
        
        return max(0, min(100, score))
    
    def _calculate_put_selling_score(self, put_row: pd.Series, oi_change_pct: float, price_change: float = 0) -> float:
        """
        Calculate selling score for put options (higher = better for selling)
        
        Args:
            put_row (pd.Series): Put option data
            oi_change_pct (float): OI change percentage
            price_change (float): Price change (LTP - Prev Close)
        
        Returns:
            float: Selling score (0-100)
        """
        score = 50  # Base score
        
        # Determine buildup type
        if oi_change_pct > 5:
            if price_change > 0: # Long Build (Aggressive Put Buying = Bearish Market)
                score -= 20
            else: # Short Build (Aggressive Put Selling = Support/Bullish)
                score += 20
        elif oi_change_pct < -5:
            if price_change < 0: # Long Unwinding (Put Buyers exiting)
                score += 10
            else: # Short Covering (Put Sellers exiting)
                score -= 10
        
        # Price analysis for premium attractiveness
        ltp = put_row['ltp']
        if 25 <= ltp <= 150:
            score += 10 # Ideal premium range for strangles
            
        # Liquidity analysis
        volume = put_row['volume']
        if volume > 500:
            score += 5
            
        return max(0, min(100, score))
    
    def _find_optimal_ce_strike(self, strike_analysis: List[Dict], spot_price: float) -> Dict:
        """
        Find optimal CE strike based on selling score (OTM calls only)
        
        Args:
            strike_analysis (List[Dict]): Strike analysis data
            spot_price (float): Current spot price
        
        Returns:
            Dict: Optimal CE strike data
        """
        # Calculate ATM strike
        atm_strike = round(spot_price / 50) * 50
        
        # Filter OTM call strikes (above ATM, max 4 strikes away, min ₹8 premium)
        ce_strikes = []
        for s in strike_analysis:
            strike = s['strike']
            call_ltp = s['call_ltp']
            
            # Must be OTM (above ATM)
            if strike <= atm_strike:
                continue
                
            # Must be within 4 strikes of ATM
            if strike > atm_strike + (4 * 50):  # 4 strikes = 200 points
                continue
                
            # Must have minimum ₹8 premium
            if call_ltp < 8.0:
                continue
                
            ce_strikes.append(s)
        
        if not ce_strikes:
            # Fallback: return first available strike above ATM with min price
            for s in strike_analysis:
                if s['strike'] > atm_strike and s['call_ltp'] >= 8.0:
                    return s
            return strike_analysis[0]  # Last resort fallback
        
        # Find strike with highest call selling score
        optimal_ce = max(ce_strikes, key=lambda x: x['call_selling_score'])
        
        return optimal_ce
    
    def _find_optimal_pe_strike(self, strike_analysis: List[Dict], spot_price: float) -> Dict:
        """
        Find optimal PE strike based on selling score (OTM puts only)
        
        Args:
            strike_analysis (List[Dict]): Strike analysis data
            spot_price (float): Current spot price
        
        Returns:
            Dict: Optimal PE strike data
        """
        # Calculate ATM strike
        atm_strike = round(spot_price / 50) * 50
        
        # Filter OTM put strikes (below ATM, max 4 strikes away, min ₹8 premium)
        pe_strikes = []
        for s in strike_analysis:
            strike = s['strike']
            put_ltp = s['put_ltp']
            
            # Must be OTM (below ATM)
            if strike >= atm_strike:
                continue
                
            # Must be within 4 strikes of ATM
            if strike < atm_strike - (4 * 50):  # 4 strikes = 200 points
                continue
                
            # Must have minimum ₹8 premium
            if put_ltp < 8.0:
                continue
                
            pe_strikes.append(s)
        
        if not pe_strikes:
            # Fallback: return first available strike below ATM with min price
            for s in strike_analysis:
                if s['strike'] < atm_strike and s['put_ltp'] >= 8.0:
                    return s
            return strike_analysis[0]  # Last resort fallback
        
        # Find strike with highest put selling score
        optimal_pe = max(pe_strikes, key=lambda x: x['put_selling_score'])
        
        return optimal_pe
    
    def _calculate_strangle_metrics(self, ce_strike: Dict, pe_strike: Dict, spot_price: float) -> Dict:
        """
        Calculate strangle-specific metrics
        
        Args:
            ce_strike (Dict): CE strike data
            pe_strike (Dict): PE strike data
            spot_price (float): Current spot price
        
        Returns:
            Dict: Strangle metrics
        """
        ce_strike_price = ce_strike['strike']
        pe_strike_price = pe_strike['strike']
        
        # Calculate strangle width
        strangle_width = ce_strike_price - pe_strike_price
        
        # Calculate combined premium
        combined_premium = ce_strike['call_ltp'] + pe_strike['put_ltp']
        
        # Calculate combined selling score
        combined_selling_score = (ce_strike['call_selling_score'] + pe_strike['put_selling_score']) / 2
        
        # Calculate distance from spot
        ce_distance = abs(ce_strike_price - spot_price)
        pe_distance = abs(pe_strike_price - spot_price)
        avg_distance = (ce_distance + pe_distance) / 2
        
        # Calculate risk metrics
        ce_risk_level = "low" if ce_distance > 200 else "medium" if ce_distance > 100 else "high"
        pe_risk_level = "low" if pe_distance > 200 else "medium" if pe_distance > 100 else "high"
        
        return {
            'strangle_width': strangle_width,
            'combined_premium': combined_premium,
            'combined_selling_score': combined_selling_score,
            'ce_distance_from_spot': ce_distance,
            'pe_distance_from_spot': pe_distance,
            'avg_distance_from_spot': avg_distance,
            'ce_risk_level': ce_risk_level,
            'pe_risk_level': pe_risk_level,
            'overall_risk_level': "low" if avg_distance > 200 else "medium" if avg_distance > 100 else "high"
        }
    
    def _get_strangle_recommendation(self, strangle_analysis: Dict) -> Dict:
        """
        Get strangle recommendation based on analysis
        
        Args:
            strangle_analysis (Dict): Strangle analysis data
        
        Returns:
            Dict: Recommendation data
        """
        combined_score = strangle_analysis['combined_selling_score']
        overall_risk = strangle_analysis['overall_risk_level']
        combined_premium = strangle_analysis['combined_premium']
        
        # Determine recommendation
        if combined_score >= 70 and overall_risk == "low":
            recommendation = "strong_strangle"
            confidence = "high"
        elif combined_score >= 60 and overall_risk in ["low", "medium"]:
            recommendation = "strangle"
            confidence = "medium"
        elif combined_score >= 50:
            recommendation = "weak_strangle"
            confidence = "low"
        else:
            recommendation = "avoid"
            confidence = "low"
        
        # Calculate risk-reward ratio
        if combined_premium > 0:
            risk_reward_ratio = strangle_analysis['strangle_width'] / combined_premium
        else:
            risk_reward_ratio = 0
        
        return {
            'recommendation': recommendation,
            'confidence': confidence,
            'risk_reward_ratio': risk_reward_ratio,
            'reasoning': self._get_recommendation_reasoning(recommendation, combined_score, overall_risk)
        }
    
    def _get_recommendation_reasoning(self, recommendation: str, score: float, risk: str) -> str:
        """
        Get reasoning for recommendation
        
        Args:
            recommendation (str): Recommendation type
            score (float): Combined selling score
            risk (str): Risk level
        
        Returns:
            str: Reasoning text
        """
        if recommendation == "strong_strangle":
            return f"Excellent OI conditions (Score: {score:.1f}) with low risk ({risk}) - ideal for strangle"
        elif recommendation == "strangle":
            return f"Good OI conditions (Score: {score:.1f}) with {risk} risk - suitable for strangle"
        elif recommendation == "weak_strangle":
            return f"Moderate OI conditions (Score: {score:.1f}) with {risk} risk - proceed with caution"
        else:
            return f"Poor OI conditions (Score: {score:.1f}) with {risk} risk - avoid strangle"
    
    def format_strangle_analysis(self, analysis_data: Dict) -> str:
        """
        Format strangle analysis for display
        
        Args:
            analysis_data (Dict): Strangle analysis data
        
        Returns:
            str: Formatted analysis string
        """
        if "error" in analysis_data:
            return f"❌ Error: {analysis_data['error']}"
        
        output = []
        output.append("="*70)
        output.append("OI-GUIDED STRANGLE ANALYSIS")
        output.append("="*70)
        
        # Overall summary
        ce_strike = analysis_data['optimal_ce_strike']
        pe_strike = analysis_data['optimal_pe_strike']
        strangle_analysis = analysis_data['strangle_analysis']
        recommendation = analysis_data['recommendation']
        
        output.append(f"\n🎯 OPTIMAL STRANGLE SELECTION:")
        output.append(f"   CE Strike: {ce_strike['strike']} (Score: {ce_strike['call_selling_score']:.1f})")
        output.append(f"   PE Strike: {pe_strike['strike']} (Score: {pe_strike['put_selling_score']:.1f})")
        output.append(f"   Combined Score: {strangle_analysis['combined_selling_score']:.1f}/100")
        
        # Recommendation
        rec_emoji = "🟢" if recommendation['recommendation'] in ["strong_strangle", "strangle"] else "🔴" if recommendation['recommendation'] == "avoid" else "🟡"
        output.append(f"\n📊 RECOMMENDATION: {rec_emoji} {recommendation['recommendation'].upper()}")
        output.append(f"   Confidence: {recommendation['confidence'].title()}")
        output.append(f"   Risk Level: {strangle_analysis['overall_risk_level'].title()}")
        output.append(f"   Reasoning: {recommendation['reasoning']}")
        
        # Strangle metrics
        output.append(f"\n📈 STRANGLE METRICS:")
        output.append(f"   Strangle Width: {strangle_analysis['strangle_width']} points")
        output.append(f"   Combined Premium: ₹{strangle_analysis['combined_premium']:.2f}")
        output.append(f"   CE Distance from Spot: {strangle_analysis['ce_distance_from_spot']:.0f} points")
        output.append(f"   PE Distance from Spot: {strangle_analysis['pe_distance_from_spot']:.0f} points")
        output.append(f"   Risk-Reward Ratio: {recommendation['risk_reward_ratio']:.2f}")
        
        # Strike details
        output.append(f"\n🔍 STRIKE DETAILS:")
        output.append(f"   CE {ce_strike['strike']}: OI {ce_strike['call_oi_change_pct']:+.1f}%, LTP ₹{ce_strike['call_ltp']:.2f}")
        output.append(f"   PE {pe_strike['strike']}: OI {pe_strike['put_oi_change_pct']:+.1f}%, LTP ₹{pe_strike['put_ltp']:.2f}")
        
        output.append("="*70)
        return "\n".join(output)


# Example usage and testing
if __name__ == "__main__":
    print("OI-Guided Strangle Analyzer Module")
    print("This module should be imported and used from the main strategy")
