"""
404Bot v2 - Configuration Module
Handles all configuration settings with secure key management
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration manager with secure key handling"""
    
    def __init__(self, config_file: str = None):
        """
        Initialize configuration
        
        Args:
            config_file: Optional path to JSON config file
        """
        # Core settings
        self.MODE = self._get_env("MODE", "paper_trading")
        self.LOG_LEVEL = self._get_env("LOG_LEVEL", "INFO")
        
        # Web3 settings
        self.WEB3_PROVIDER_URL = self._get_env("WEB3_PROVIDER_URL", "")
        self.FALLBACK_PROVIDER_URLS = [
            self._get_env("FALLBACK_PROVIDER_URL1", ""),
            self._get_env("FALLBACK_PROVIDER_URL2", "")
        ]
        
        # Wallet settings
        self.WALLET_ADDRESS = self._get_env("WALLET_ADDRESS", "")
        self.PRIVATE_KEY = self._get_env("PRIVATE_KEY", "", is_sensitive=True)
        
        # Contract addresses
        self.FLASH_LOAN_CONTRACT = self._get_env("FLASH_LOAN_CONTRACT", "")
        self.UNISWAP_ROUTER = self._get_env("UNISWAP_ROUTER", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
        self.SUSHISWAP_ROUTER = self._get_env("SUSHISWAP_ROUTER", "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F")
        self.AAVE_LENDING_POOL = self._get_env("AAVE_LENDING_POOL", "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9")
        
        # Exchange API credentials
        self.EXCHANGE_CREDENTIALS = {
            "binance": {
                "apiKey": self._get_env("BINANCE_API_KEY", "", is_sensitive=True),
                "secret": self._get_env("BINANCE_SECRET", "", is_sensitive=True)
            },
            "bybit": {
                "apiKey": self._get_env("BYBIT_API_KEY", "", is_sensitive=True),
                "secret": self._get_env("BYBIT_SECRET", "", is_sensitive=True)
            }
        }
        
        # Trading parameters
        self.MIN_PROFIT_USD = float(self._get_env("MIN_PROFIT_USD", "50.0"))
        self.MAX_SLIPPAGE = float(self._get_env("MAX_SLIPPAGE", "0.5")) / 100  # Convert from percentage to decimal
        self.GAS_PRICE_BUFFER = float(self._get_env("GAS_PRICE_BUFFER", "1.15"))
        self.MAX_CONCURRENT_TRADES = int(self._get_env("MAX_CONCURRENT_TRADES", "5"))
        
        # Token addresses (common tokens)
        self.TOKEN_ADDRESSES = {
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
        }
        
        # MEV settings
        self.FLASHBOTS_ENDPOINT = self._get_env("FLASHBOTS_ENDPOINT", "https://relay.flashbots.net")
        self.EDEN_ENDPOINT = self._get_env("EDEN_ENDPOINT", "https://api.edennetwork.io/v1/bundle")
        
        # Load additional settings from config file if provided
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)
        
        # Validate configuration
        self._validate_config()
    
    def _get_env(self, key: str, default: str = "", is_sensitive: bool = False) -> str:
        """
        Safely get environment variable
        
        Args:
            key: Environment variable name
            default: Default value if not found
            is_sensitive: Whether this is sensitive data
            
        Returns:
            Environment variable value or default
        """
        value = os.environ.get(key, default)
        
        # Warn if sensitive data is empty
        if is_sensitive and value == default:
            logging.warning(f"Sensitive configuration {key} is not set")
        
        return value
    
    def _load_from_file(self, config_file: str):
        """
        Load configuration from JSON file
        
        Args:
            config_file: Path to JSON config file
        """
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            # Update attributes from file
            for key, value in config_data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                    
        except Exception as e:
            logging.error(f"Error loading config file: {str(e)}")
    
    def _validate_config(self):
        """Validate configuration and log warnings for missing critical values"""
        if not self.WEB3_PROVIDER_URL:
            logging.warning("WEB3_PROVIDER_URL is not set")
        
        if not self.WALLET_ADDRESS:
            logging.warning("WALLET_ADDRESS is not set")
        
        if not self.PRIVATE_KEY:
            logging.warning("PRIVATE_KEY is not set")
        
        if not self.FLASH_LOAN_CONTRACT:
            logging.warning("FLASH_LOAN_CONTRACT address is not set")
    
    def save_to_file(self, file_path: str):
        """
        Save non-sensitive configuration to a file
        
        Args:
            file_path: Path to save configuration
        """
        # Create a dictionary of non-sensitive configuration
        config_dict = {
            "MODE": self.MODE,
            "LOG_LEVEL": self.LOG_LEVEL,
            "WEB3_PROVIDER_URL": self.WEB3_PROVIDER_URL,
            "FALLBACK_PROVIDER_URLS": self.FALLBACK_PROVIDER_URLS,
            "WALLET_ADDRESS": self.WALLET_ADDRESS,
            "FLASH_LOAN_CONTRACT": self.FLASH_LOAN_CONTRACT,
            "UNISWAP_ROUTER": self.UNISWAP_ROUTER,
            "SUSHISWAP_ROUTER": self.SUSHISWAP_ROUTER,
            "AAVE_LENDING_POOL": self.AAVE_LENDING_POOL,
            "MIN_PROFIT_USD": self.MIN_PROFIT_USD,
            "MAX_SLIPPAGE": self.MAX_SLIPPAGE * 100,  # Convert back to percentage
            "GAS_PRICE_BUFFER": self.GAS_PRICE_BUFFER,
            "MAX_CONCURRENT_TRADES": self.MAX_CONCURRENT_TRADES,
            "TOKEN_ADDRESSES": self.TOKEN_ADDRESSES,
            "FLASHBOTS_ENDPOINT": self.FLASHBOTS_ENDPOINT,
            "EDEN_ENDPOINT": self.EDEN_ENDPOINT
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
                
            logging.info(f"Configuration saved to {file_path}")
            
        except Exception as e:
            logging.error(f"Error saving configuration: {str(e)}")
    
    def get_token_address(self, symbol: str) -> str:
        """
        Get token address by symbol
        
        Args:
            symbol: Token symbol (e.g., "WETH")
            
        Returns:
            Token address or empty string if not found
        """
        return self.TOKEN_ADDRESSES.get(symbol, "")
