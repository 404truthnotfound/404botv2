"""
Enhanced logging utility for the 404-Bot
Provides standardized logging across all components with improved features:
- Rotating file handlers with size limits
- Console output with color coding
- Configurable log levels per component
- Structured JSON logging for automated analysis
- Trade logging with detailed metrics
"""

import os
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform colored terminal output
colorama.init()

# Ensure logs directory exists with subdirectories
def ensure_log_dirs():
    """Create necessary log directories if they don't exist"""
    log_dirs = ["logs", "logs/trades", "logs/errors", "logs/archived", "logs/performance"]
    for dir_path in log_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

ensure_log_dirs()

# Global configuration
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 10  # Number of backup files to keep

# Log format with timestamps and component
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Color mapping for different log levels in console output
LEVEL_COLORS = {
    'DEBUG': Fore.CYAN,
    'INFO': Fore.GREEN,
    'WARNING': Fore.YELLOW,
    'ERROR': Fore.RED,
    'CRITICAL': Fore.MAGENTA + Style.BRIGHT
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to console output"""
    
    def format(self, record):
        levelname = record.levelname
        message = super().format(record)
        
        color = LEVEL_COLORS.get(levelname, Fore.WHITE)
        return f"{color}{message}{Style.RESET_ALL}"

class JSONFormatter(logging.Formatter):
    """Formats log records as JSON for structured logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'name': record.name,
            'level': record.levelname,
            'message': record.getMessage()
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
            
        # Add any extra attributes
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
            
        return json.dumps(log_data)

def setup_logger(name: str, log_level: str = None) -> logging.Logger:
    """
    Set up and return a logger with the specified name and level
    
    Args:
        name: Logger name (typically component name)
        log_level: Optional override for log level
        
    Returns:
        Configured logger instance
    """
    # Convert log level string to logging constant
    log_level = log_level or DEFAULT_LOG_LEVEL
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        print(f"Invalid log level: {log_level}, defaulting to INFO")
        numeric_level = logging.INFO
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)
    
    # Check if logger already has handlers to avoid duplicates
    if logger.handlers:
        return logger
    
    # Create console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = ColoredFormatter(LOG_FORMAT)
    console_handler.setFormatter(console_formatter)
    
    # Create file handler with rotation
    file_handler = RotatingFileHandler(
        f"logs/{name.lower()}.log",
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=BACKUP_COUNT
    )
    file_handler.setLevel(numeric_level)
    file_formatter = logging.Formatter(LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    
    # Create JSON file handler for structured logging
    json_handler = RotatingFileHandler(
        f"logs/{name.lower()}_json.log",
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=BACKUP_COUNT
    )
    json_handler.setLevel(numeric_level)
    json_formatter = JSONFormatter()
    json_handler.setFormatter(json_formatter)
    
    # Create error handler that logs only errors and above to a dedicated file
    error_handler = RotatingFileHandler(
        f"logs/errors/{name.lower()}_error.log",
        maxBytes=MAX_LOG_FILE_SIZE,
        backupCount=BACKUP_COUNT
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(json_handler)
    logger.addHandler(error_handler)
    
    return logger

class AsyncTradeLogger:
    """
    Logger specifically for trade execution and results with async batch writing
    Includes performance metrics and detailed trade information
    """
    
    def __init__(self, batch_size=10, flush_interval=60):
        # Create specific trade log file
        self.logger = logging.getLogger("TradeLogger")
        self.log_file = "logs/trades/trades.json"
        self.performance_file = "logs/performance/performance.json"
        self.batch_size = batch_size
        self.flush_interval = flush_interval  # seconds
        self.pending_trades = []
        self.pending_performance = []
        self.lock = threading.Lock()
        self.last_flush_time = time.time()
        
        # Start background thread for periodic flushing
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.executor.submit(self._periodic_flush)
        
        # Ensure trade log and performance log files exist
        for file_path in [self.log_file, self.performance_file]:
            directory = os.path.dirname(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory)
            
            # Create empty JSON array if file doesn't exist
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    json.dump([], f)
    
    def log_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        Log a trade in the standardized JSON format
        
        Args:
            trade_data: Dictionary containing trade information
            
        Returns:
            True if successfully queued for logging, False otherwise
        """
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
            
            # Log as JSON to standard logger
            self.logger.info(f"Trade executed: {json.dumps(trade_data)}")
            
            # Add to pending batch with thread safety
            with self.lock:
                self.pending_trades.append(trade_data)
                
                # Add summarized version to performance metrics
                perf_data = {
                    "timestamp": trade_data["timestamp"],
                    "trade_id": trade_data["trade_id"],
                    "strategy": trade_data["strategy"],
                    "pair": trade_data["pair"],
                    "profit_realized": trade_data["profit_realized"],
                    "execution_time_ms": trade_data["execution_time_ms"],
                    "order_status": trade_data["order_status"]
                }
                self.pending_performance.append(perf_data)
                
                # Write batch if reached batch size
                if len(self.pending_trades) >= self.batch_size:
                    self.executor.submit(self._write_batch)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error logging trade: {str(e)}", exc_info=True)
            return False
    
    def _write_batch(self):
        """Write pending trades batch to JSON file with error handling"""
        with self.lock:
            pending_trades = self.pending_trades.copy()
            pending_performance = self.pending_performance.copy()
            self.pending_trades = []
            self.pending_performance = []
            self.last_flush_time = time.time()
            
        if not pending_trades:
            return
            
        try:
            # Process trades file
            self._write_to_json_file(self.log_file, pending_trades)
            
            # Process performance file
            self._write_to_json_file(self.performance_file, pending_performance)
                
        except Exception as e:
            self.logger.error(f"Error writing trade batch: {str(e)}", exc_info=True)
            # Recover the pending trades to try again later
            with self.lock:
                self.pending_trades = pending_trades + self.pending_trades
                self.pending_performance = pending_performance + self.pending_performance
    
    def _write_to_json_file(self, file_path: str, data_to_append: List[Dict]):
        """Helper method to write data to a JSON file"""
        if not data_to_append:
            return
            
        # Read existing data
        existing_data = []
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r') as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    # File exists but isn't valid JSON, start fresh
                    existing_data = []
        
        # Append new data
        existing_data.extend(data_to_append)
        
        # Write back to file (create temporary file first for safety)
        temp_file = f"{file_path}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(existing_data, f, indent=2)
            
        # Rename temp file to actual file (atomic operation)
        os.replace(temp_file, file_path)
    
    def _periodic_flush(self):
        """Background task to periodically flush pending trades"""
        while True:
            try:
                time.sleep(5)  # Check every 5 seconds
                
                current_time = time.time()
                if current_time - self.last_flush_time >= self.flush_interval:
                    # More than flush_interval seconds passed since last flush
                    with self.lock:
                        if self.pending_trades:  # Only flush if there's something to flush
                            self._write_batch()
            except Exception as e:
                # Just log the error and continue - this is a background task
                try:
                    print(f"Error in periodic flush: {str(e)}")
                except:
                    pass
    
    def flush(self):
        """Force write any pending trades"""
        self._write_batch()
    
    # Make sure to flush on shutdown
    def __del__(self):
        try:
            self.flush()
            self.executor.shutdown(wait=False)
        except:
            pass

# Global trade logger instance
_trade_logger = None

def get_trade_logger() -> AsyncTradeLogger:
    """Get the global trade logger instance"""
    global _trade_logger
    if _trade_logger is None:
        _trade_logger = AsyncTradeLogger()
    return _trade_logger

async def log_trade(trade_data: Dict[str, Any]) -> bool:
    """Global function to log trade data"""
    return get_trade_logger().log_trade(trade_data)

async def get_recent_trades(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Global function to get recent trades
    
    Args:
        limit: Maximum number of recent trades to return
        
    Returns:
        List of recent trade records
    """
    trade_logger = get_trade_logger()
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
        logging.error(f"Error reading trades: {str(e)}", exc_info=True)
        return []

def log_exception(logger: logging.Logger, e: Exception, message: str = "An error occurred"):
    """
    Helper function to log exceptions with full traceback in a standard format
    
    Args:
        logger: Logger instance to use
        e: Exception to log
        message: Custom message to include
    """
    error_id = uuid.uuid4().hex[:8]
    error_details = {
        'error_id': error_id,
        'error_type': type(e).__name__,
        'error_message': str(e),
        'traceback': traceback.format_exc()
    }
    
    logger.error(f"{message} - Error ID: {error_id}", exc_info=True, 
                 extra={'error_details': error_details})
    return error_id

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
        strategy: Name of trading strategy
        exchange_1: Name of first exchange
        exchange_2: Name of second exchange
        pair: Trading pair (e.g., "BTC/USDT")
        price_1: Price on first exchange
        price_2: Price on second exchange
        spread_percentage: Percentage spread between exchanges
        trade_size: Size of trade in base currency
        profit_expected: Expected profit before execution
        profit_realized: Actual profit after execution
        execution_time_ms: Time to execute trade in milliseconds
        order_status: Status of the order (e.g., "FILLED", "PARTIAL", "FAILED")
        slippage: Price slippage during execution
        
    Returns:
        Dictionary with trade data formatted for logging
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

# Example usage and self-test
if __name__ == "__main__":
    # Setup test logger
    test_logger = setup_logger("LoggerTest")
    
    # Test various log levels
    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")
    
    # Test exception logging
    try:
        1 / 0
    except Exception as e:
        error_id = log_exception(test_logger, e, "Division by zero test")
        print(f"Logged error with ID: {error_id}")
    
    # Test trade logging
    trade_data = format_trade_for_logging(
        strategy="DEX_ARBITRAGE",
        exchange_1="Uniswap",
        exchange_2="SushiSwap",
        pair="ETH/USDT",
        price_1=1500.25,
        price_2=1505.75,
        spread_percentage=0.367,
        trade_size=0.5,
        profit_expected=2.75,
        profit_realized=2.45,
        execution_time_ms=1250,
        order_status="FILLED",
        slippage=0.12
    )
    
    # Get trade logger and log the trade
    logger = get_trade_logger()
    logger.log_trade(trade_data)
    
    # Flush pending trades
    logger.flush()
    
    print("Logger test completed. Check logs directory for results.")
