"""
Logging utility for the arbitrage bot
Provides standardized logging across all components
Includes trade logging in the required JSON format
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio
import time
import uuid

# Ensure logs directory exists
if not os.path.exists("logs"):
    os.makedirs("logs")

def setup_logger(name: str, log_level: str = "INFO") -> logging.Logger:
    """Set up and return a logger with the specified name and level"""
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)
    
    # Check if logger already has handlers
    if logger.handlers:
        return logger
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    
    # Create file handler
    file_handler = logging.FileHandler(f"logs/{name.lower()}.log")
    file_handler.setLevel(numeric_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set formatter for handlers
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

class TradeLogger:
    """Logger specifically for trade execution and results with batch writing"""
    
    def __init__(self, batch_size=10):
        # Create specific trade log file
        self.logger = logging.getLogger("TradeLogger")
        self.log_file = "logs/trades.json"
        self.batch_size = batch_size
        self.pending_trades = []
        
        # Create handler for trade logs
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_trade(self, trade_data: Dict[str, Any]):
        """Log a trade in the standardized JSON format"""
        try:
            # Ensure all required fields are present
            required_fields = [
                "timestamp", "strategy", "exchange_1", "exchange_2", 
                "pair", "price_1", "price_2", "spread_percentage",
                "trade_size", "profit_expected", "profit_realized",
                "execution_time_ms", "order_status", "slippage"
            ]
            
            # Set defaults for missing fields
            for field in required_fields:
                if field not in trade_data:
                    if field == "timestamp":
                        trade_data[field] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        trade_data[field] = None
            
            # Add a unique trade ID
            if "trade_id" not in trade_data:
                trade_data["trade_id"] = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
            
            # Log as JSON
            self.logger.info(json.dumps(trade_data))
            
            # Add to pending batch
            self.pending_trades.append(trade_data)
            
            # Write batch if reached batch size
            if len(self.pending_trades) >= self.batch_size:
                self._write_batch()
            
            return True
        
        except Exception as e:
            logging.error(f"Error logging trade: {str(e)}")
            return False
    
    def _write_batch(self):
        """Write pending trades batch to JSON file"""
        if not self.pending_trades:
            return
            
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            
            # Read existing data
            trades = []
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > 0:
                with open(self.log_file, 'r') as f:
                    try:
                        trades = json.load(f)
                        if not isinstance(trades, list):
                            trades = [trades]
                    except json.JSONDecodeError:
                        # File exists but isn't valid JSON, start fresh
                        trades = []
            
            # Append all pending trades
            trades.extend(self.pending_trades)
            
            # Write back to file
            with open(self.log_file, 'w') as f:
                json.dump(trades, f, indent=2)
                
            # Clear pending trades
            self.pending_trades = []
            
        except Exception as e:
            logging.error(f"Error writing trade batch: {str(e)}")
    
    def flush(self):
        """Force write any pending trades"""
        self._write_batch()
    
    # Make sure to flush on shutdown
    def __del__(self):
        self.flush()

# Global trade logger instance
trade_logger = None

async def log_trade(trade_data: Dict[str, Any]) -> bool:
    """Global function to log trade data"""
    global trade_logger
    if trade_logger is None:
        trade_logger = TradeLogger()
    return trade_logger.log_trade(trade_data)

async def get_recent_trades(limit: int = 10) -> List[Dict[str, Any]]:
    """Global function to get recent trades"""
    global trade_logger
    if trade_logger is None:
        trade_logger = TradeLogger()
    try:
        if os.path.exists(trade_logger.log_file) and os.path.getsize(trade_logger.log_file) > 0:
            with open(trade_logger.log_file, 'r') as f:
                trades = json.load(f)
                if isinstance(trades, list):
                    return trades[-limit:]
                else:
                    return [trades]
        return []
    
    except Exception as e:
        logging.error(f"Error reading trades: {str(e)}")
        return []

def format_trade_for_logging(
    strategy: str,
    exchange_1: str,
    exchange_2: str,
    pair: str,
    price_1: float,
    price_2: float,
    spread_percentage: float,
    trade_size: float,
    profit_expected: float,
    profit_realized: float,
    execution_time_ms: int,
    order_status: str,
    slippage: float
) -> Dict[str, Any]:
    """
    Format trade data for logging in standardized format
    
    Args:
        Various trade parameters
        
    Returns:
        Trade data dictionary ready for logging
    """
    return {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": strategy,
        "exchange_1": exchange_1,
        "exchange_2": exchange_2,
        "pair": pair,
        "price_1": price_1,
        "price_2": price_2,
        "spread_percentage": spread_percentage,
        "trade_size": trade_size,
        "profit_expected": profit_expected,
        "profit_realized": profit_realized,
        "execution_time_ms": execution_time_ms,
        "order_status": order_status,
        "slippage": slippage
    }

async def main():
    trade_data = format_trade_for_logging(
        "test_strategy",
        "exchange_1",
        "exchange_2",
        "pair",
        1.0,
        2.0,
        10.0,
        100.0,
        10.0,
        10.0,
        100,
        "filled",
        0.1
    )
    await log_trade(trade_data)
    global trade_logger
    if trade_logger is not None:
        await trade_logger.flush()

asyncio.run(main())