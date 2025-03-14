"""
Configuration module for the arbitrage bot
Loads and manages configuration settings
"""

import os
import json
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

# Default configuration
DEFAULT_CONFIG = {
    # General settings
    "MODE": "paper_trading",  # Options: paper_trading, live_trading
    "LOG_LEVEL": "INFO",
    
    # API credentials - should be loaded from environment variables in production
    "EXCHANGE_CREDENTIALS": {
        "binance": {
            "apiKey": os.environ.get("BINANCE_API_KEY", ""),
            "secret": os.environ.get("BINANCE_SECRET", ""),
        },
        "bybit": {
            "apiKey": os.environ.get("BYBIT_API_KEY", ""),
            "secret": os.environ.get("BYBIT_SECRET", ""),
        },
        "okx": {
            "apiKey": os.environ.get("OKX_API_KEY", ""),
            "secret": os.environ.get("OKX_SECRET", ""),
            "password": os.environ.get("OKX_PASSPHRASE", ""),
        },
    },
    
    # Blockchain settings
    "WEB3_PROVIDER_URL": os.environ.get("WEB3_PROVIDER_URL", "https://mainnet.infura.io/v3/YOUR_INFURA_KEY"),
    "FALLBACK_PROVIDER_URLS": [
        os.environ.get("FALLBACK_PROVIDER_URL1", ""),
        os.environ.get("FALLBACK_PROVIDER_URL2", ""),
    ],
    "WALLET_ADDRESS": os.environ.get("WALLET_ADDRESS", ""),
    "PRIVATE_KEY": os.environ.get("PRIVATE_KEY", ""),
    
    # Trading parameters
    "TRADING_PAIRS": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "ETH/BTC", 
        "BNB/USDT", "XRP/USDT", "ADA/USDT", "MATIC/USDT"
    ],
    "STABLECOIN_PAIRS": ["USDT/USDC", "USDT/DAI", "USDC/DAI", "USDT/BUSD"],
    
    # Strategy parameters
    "MIN_PROFIT_THRESHOLD": 0.1,  # Minimum profit percentage to execute trade
    "MAX_TRADE_SIZE": 1.0,  # Maximum size per trade in BTC equivalent
    "TRADE_SIZE_PERCENTAGE": 0.8,  # Percentage of available balance to use
    "SLIPPAGE_TOLERANCE": 0.2,  # Maximum acceptable slippage percentage
    "FLASH_LOAN_FEE": 0.09,  # Flash loan fee percentage
    
    # Risk management
    "CIRCUIT_BREAKER_THRESHOLD": 3,  # Failed trades before circuit breaker
    "PROFIT_TARGET_PERCENTAGE": 5.0,  # Daily profit target
    
    # Performance settings
    "MAX_CONCURRENT_EXECUTIONS": 3,  # Maximum concurrent trade executions
    "EXECUTION_TIMEOUT": 5,  # Timeout for trade execution in seconds
    "SCAN_INTERVAL": 1.0,  # Time between opportunity scans
    "MONITORING_INTERVAL": 60.0,  # Time between system monitoring checks
    
    # Smart contract addresses
    "CONTRACT_ADDRESSES": {
        "AAVE_LENDING_POOL": "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
        "UNISWAP_ROUTER": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        "SUSHISWAP_ROUTER": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        "CURVE_ROUTER": "0x7fC77b5c7614E1533320Ea6DDc2Eb61fa00A9714",
    },
    
    # Token addresses
    "TOKEN_ADDRESSES": {
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    },
    
    # Performance tracking
    "MARKET_DATA_TTL": 0.1,  # Cache time-to-live for market data
    "REDIS_URL": "redis://localhost:6379/0",  # Redis connection for caching
    "WEBSOCKET_RECONNECT_DELAY": 3,  # Websocket reconnection delay
}

# Configuration singleton
_config = None

@dataclass
class Config:
    """Configuration class for arbitrage bot"""
    
    def __init__(self, config_dict: Dict[str, Any]):
        # Set all config parameters as attributes
        for key, value in config_dict.items():
            setattr(self, key, value)

def load_config(config_file: str = "config.json") -> Config:
    """Load configuration from file or use defaults"""
    global _config
    
    if _config is not None:
        return _config
    
    config_dict = DEFAULT_CONFIG.copy()
    
    # Try to load from config file
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                
                # Update config with file values
                for key, value in file_config.items():
                    if key in config_dict:
                        if isinstance(config_dict[key], dict) and isinstance(value, dict):
                            # Merge dictionaries
                            config_dict[key].update(value)
                        else:
                            # Replace value
                            config_dict[key] = value
    
    except Exception as e:
        logging.error(f"Error loading config file: {str(e)}")
        logging.warning("Using default configuration")
    
    # Create config object
    _config = Config(config_dict)
    return _config

def save_config(config: Config, config_file: str = "config.json") -> bool:
    """Save current configuration to file"""
    try:
        # Convert config to dictionary
        config_dict = {key: getattr(config, key) for key in dir(config) 
                      if not key.startswith('_') and not callable(getattr(config, key))}
        
        # Write to file
        with open(config_file, 'w') as f:
            json.dump(config_dict, f, indent=2)
        
        return True
    
    except Exception as e:
        logging.error(f"Error saving config file: {str(e)}")
        return False

def get_credential(exchange: str, key: str) -> str:
    """Get API credential for an exchange"""
    config = load_config()
    
    if hasattr(config, "EXCHANGE_CREDENTIALS"):
        exchange_creds = config.EXCHANGE_CREDENTIALS.get(exchange, {})
        return exchange_creds.get(key, "")
    
    return ""

def get_contract_address(contract_name: str) -> str:
    """Get smart contract address by name"""
    config = load_config()
    
    if hasattr(config, "CONTRACT_ADDRESSES"):
        return config.CONTRACT_ADDRESSES.get(contract_name, "")
    
    return ""

def get_token_address(token_name: str) -> str:
    """Get token address by name"""
    config = load_config()
    
    if hasattr(config, "TOKEN_ADDRESSES"):
        return config.TOKEN_ADDRESSES.get(token_name, "")
    
    return ""