"""
BrokerClient: Wrapper for Kotak Neo API with authentication and data loading.

This module provides:
- Authentication with Kotak Neo API using TOTP
- Master data loading for NSE CM and FO segments
- Instrument token resolution
"""

import os
import pyotp
import pandas as pd
import logging
from neo_api_client import NeoAPI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class BrokerClient:
    """
    Wrapper for Kotak Neo API with authentication.
    """
    
    def __init__(self):
        """Initialize broker client and load credentials from environment."""
        # Load .env from Kotak_Api directory
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        load_dotenv(env_path)
        self.consumer_key = os.getenv("KOTAK_CONSUMER_KEY")
        self.mobile = os.getenv("KOTAK_MOBILE_NUMBER")
        self.ucc = os.getenv("KOTAK_UCC")
        self.totp_secret = os.getenv("TOTP", "GC6A75CPAEY5WBWTQGMOGKQ2DE")
        self.mpin = os.getenv("KOTAK_MPIN")
        self.client = None
        self.master_df = None
    
    def authenticate(self):
        """
        Authenticate with Kotak Neo API using TOTP.
        """
        logger.info("Authenticating with Kotak Neo API...")
        try:
            self.client = NeoAPI(environment='prod', consumer_key=self.consumer_key)
            totp = pyotp.TOTP(self.totp_secret).now()
            self.client.totp_login(mobile_number=self.mobile, ucc=self.ucc, totp=totp)
            self.client.totp_validate(mpin=self.mpin)
            logger.info("Authentication successful!")
            return self.client
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise
    
    def download_fresh_master(self):
        """Download fresh master data files from broker."""
        import requests
        try:
            original_dir = os.getcwd()
            kotak_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            os.chdir(kotak_dir)
            
            def download_from_url(url, filename):
                if not url or not isinstance(url, str) or not url.startswith('http'):
                    logger.error(f"Invalid URL for {filename}")
                    return False
                
                try:
                    resp = requests.get(url, timeout=60)
                    if resp.status_code == 200:
                        with open(filename, 'wb') as f:
                            f.write(resp.content)
                        logger.info(f"{filename} downloaded.")
                        return True
                    return False
                except Exception as e:
                    logger.error(f"Error downloading {filename}: {e}")
                    return False

            logger.info("Updating master data files (this may take a moment)...")
            url_fo = self.client.scrip_master(exchange_segment="nse_fo")
            download_from_url(url_fo, "nse_fo.csv")

            url_cm = self.client.scrip_master(exchange_segment="nse_cm")
            download_from_url(url_cm, "nse_cm.csv")
            
            os.chdir(original_dir)
        except Exception as e:
            logger.error(f"Error in master data refresh: {e}")
            os.chdir(original_dir)
    
    def load_master_data(self, force_download=False):
        """
        Load and merge master data for NSE FO and CM segments.
        """
        kotak_dir = os.path.join(os.path.dirname(__file__), '..')
        segments = [
            os.path.join(kotak_dir, 'nse_fo.csv'),
            os.path.join(kotak_dir, 'nse_cm.csv')
        ]
        
        if force_download or not all(os.path.exists(f) for f in segments):
            if not self.client:
                raise ValueError("Must authenticate before downloading master data")
            self.download_fresh_master()
        
        logger.info("Loading master data...")
        dfs = []
        for path in segments:
            if os.path.exists(path):
                df = pd.read_csv(path)
                dfs.append(df)
                logger.info(f"Loaded {os.path.basename(path)}: {len(df)} records")
            else:
                logger.warning(f"{path} not found")
        
        if not dfs:
            raise FileNotFoundError("No master data files found!")
        
        self.master_df = pd.concat(dfs, ignore_index=True)
        logger.info(f"Loaded {len(self.master_df):,} instruments from master data")
        return self.master_df
    
    def get_instrument_token(self, symbol, exchange="nse_fo"):
        """
        Get instrument token for a symbol.
        """
        if self.master_df is None:
            raise ValueError("Master data not loaded. Call load_master_data() first.")
        
        result = self.master_df[
            (self.master_df['pSymbol'] == symbol) &
            (self.master_df['pExchSeg'] == exchange)
        ]
        
        if not result.empty:
            return str(result.iloc[0]['pSymbolName'])
        return None

    def get_funds(self):
        """
        Fetch funds and margin limits.
        """
        if not self.client:
            logger.error("Client not authenticated")
            return None
            
        try:
            logger.info("Fetching funds...")
            limits = self.client.limits()
            if limits and isinstance(limits, dict):
                logger.info(f"Funds fetched")
                return limits
            return None
        except Exception as e:
            logger.error(f"Error fetching funds: {e}")
            return None

    def logout(self):
        """Logout from the API session."""
        if not self.client:
            return
            
        try:
            logger.info("Logging out from Kotak Neo API...")
            self.client.logout()
            logger.info("Logged out successfully")
        except Exception as e:
            logger.error(f"Logout error: {e}")

    def get_ltp(self, trading_symbol, exchange_segment="nse_fo"):
        """
        Fetch Last Traded Price (LTP) for a symbol using Quotes API.
        """
        if not self.client:
            return 0.0
            
        try:
            # Prepare quote request
            # Usually requires token or instrument details, but Neo API usually accepts trading_symbol if instrument_token logic is handled internally or required
            # The get_instrument_token method exists, let's use it.
            
            # Neo API specific pattern: requires instrument token usually for Quotes
            # But library might abstract it. Let's try flexible approach.
            
            tokens = []
            # Find token in master
            token = None
            if self.master_df is not None:
                row = self.master_df[self.master_df['pTrdSymbol'] == trading_symbol]
                if not row.empty:
                    token = str(row.iloc[0]['pSymbol'])
            
            if not token:
                logger.warning(f"Could not resolve token for {trading_symbol} in master")
                return 0.0
                
            quote_requests = [
                {"instrument_token": token, "exchange_segment": exchange_segment}
            ]
            
            resp = self.client.quotes(instrument_tokens=quote_requests, quote_type="ltp")
            
            if resp and 'message' in resp:
                # Check structure
                data = resp.get('message', [])
                if data and len(data) > 0:
                    return float(data[0].get('last_price', 0))
                    
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching LTP for {trading_symbol}: {e}")
            return 0.0

    def positions(self):
        """
        Fetch current positions.
        """
        if not self.client:
            logger.error("Client not authenticated")
            return None
            
        try:
            logger.info("Fetching positions...")
            return self.client.positions()
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return None
