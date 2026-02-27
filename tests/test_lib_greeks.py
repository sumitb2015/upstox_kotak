import unittest
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.utils.greeks_helper import calc_gamma_bs, calculate_gamma_profile, calculate_flip_point, calculate_gex_for_chain

class TestGreeksHelper(unittest.TestCase):
    
    def test_calc_gamma_bs(self):
        # Test Case: S=100, K=100, vol=0.2, T=1, r=0
        # Expected value from standard BS calculator
        # d1 = (ln(1) + 0.5*0.04*1) / (0.2*1) = 0.02 / 0.2 = 0.1
        # pdf(0.1) = 0.39695
        # Gamma = 0.39695 / (100 * 0.2 * 1) = 0.198475
        gamma = calc_gamma_bs(100, 100, 0.2, 1.0)
        self.assertAlmostEqual(gamma, 0.0198475, places=5) # Corrected manual calc: 0.39695 / 20 = 0.0198475
        
        # Test 0 DTE or 0 VOL
        self.assertEqual(calc_gamma_bs(100, 100, 0, 1.0), 0)
        self.assertEqual(calc_gamma_bs(100, 100, 0.2, 0), 0)

    def test_calculate_gex_units(self):
        # Verify Indian Standard formula: Gamma * OI * LotSize * Spot * 100
        # Mock Data (Upstox gives OI in lots)
        spot = 25000
        lot_size = 75
        df = pd.DataFrame([{
            'strike_price': 25000,
            'ce_iv': 20, 
            'ce_oi': 1000, # 1000 lots
            'pe_iv': 20,
            'pe_oi': 1000,
            'spot_price': spot,
            'expiry': '2026-03-01' # Roughly 10 days out
        }])
        
        # Calculate expected GEX
        today = datetime.now()
        exp_date = pd.to_datetime('2026-03-01')
        days = (exp_date.date() - today.date()).days + 1
        T = max(days, 0.5) / 365
        gamma = calc_gamma_bs(spot, 25000, 0.2, T, r=0.065)
        
        # Formula: Gamma * OI * LotSize * Spot * 100
        expected = gamma * 1000 * lot_size * spot * 100
        
        df = calculate_gex_for_chain(df, "NIFTY")
        
        self.assertAlmostEqual(df['ce_gex'].iloc[0], expected, delta=expected * 0.001)
        self.assertAlmostEqual(df['pe_gex'].iloc[0], -expected, delta=expected * 0.001)

    def test_calculate_gamma_profile_simple(self):
        # Simple straddle: If spot is at ATM, it should have a specific GEX level
        df = pd.DataFrame([
            {'strike_price': 25000, 'ce_oi': 1000, 'ce_iv': 10, 'expiry': '2026-03-01', 'spot_price': 25000},
            {'strike_price': 25000, 'pe_oi': 1000, 'pe_iv': 10, 'expiry': '2026-03-01', 'spot_price': 25000}
        ])
        
        profile = calculate_gamma_profile(df, points=10)
        self.assertEqual(len(profile['levels']), 10)
        self.assertEqual(len(profile['gex']), 10)
        
        # At equal OI/IV/Strike, Net GEX at spot should be near 0 (Gamma_CE = Gamma_PE)
        # Actually GEX_CE - GEX_PE
        # Calc Gamma(Spot=25000, K=25000, vol=0.1, T=...)
        # Profile should be symmetric
        mid_idx = 5
        self.assertAlmostEqual(profile['gex'][mid_idx], 0, delta=1e-5)

    def test_calculate_flip_point(self):
        # Create a skew: Call OI > Put OI at higher strikes, Put OI > Call OI at lower strikes
        # This should force a flip point.
        df = pd.DataFrame([
            {'strike_price': 24800, 'ce_oi': 100,  'ce_iv': 15, 'pe_oi': 1000, 'pe_iv': 15, 'expiry': '2026-03-01', 'spot_price': 25000},
            {'strike_price': 25200, 'ce_oi': 1000, 'ce_iv': 15, 'pe_oi': 100,  'pe_iv': 15, 'expiry': '2026-03-01', 'spot_price': 25000}
        ])
        
        flip = calculate_flip_point(df)
        self.assertTrue(24800 < flip < 25200)

if __name__ == '__main__':
    unittest.main()
