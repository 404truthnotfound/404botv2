"""
404Bot v2 - Logging Utility
Provides standardized logging functionality across the application
"""

import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Create logs directory if it doesn't exist
logs_dir = Path(__file__).resolve().parent.parent / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure logging format
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logger(name: str, log_level: str = None) -> logging.Logger:
    """
    Set up and configure a logger instance
    
    Args:
        name: Name of the logger
        log_level: Optional log level override
        
    Returns:
        Configured logger instance
    """
    # Get log level from environment or use default
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)
    
    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Create file handler
    log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    if log_to_file:
        log_file = logs_dir / f"{name.lower()}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

def log_trade(trade_data: Dict[str, Any], success: bool = True) -> None:
    """
    Log trade information to a dedicated trade log file
    
    Args:
        trade_data: Dictionary containing trade details
        success: Whether the trade was successful
    """
    # Create trade logger
    trade_logger = logging.getLogger("trades")
    trade_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    if trade_logger.hasHandlers():
        trade_logger.handlers.clear()
    
    # Create file handler for trades
    trade_log_file = logs_dir / "trades.log"
    trade_handler = logging.FileHandler(trade_log_file)
    trade_handler.setLevel(logging.INFO)
    trade_formatter = logging.Formatter("%(asctime)s - %(message)s", DATE_FORMAT)
    trade_handler.setFormatter(trade_formatter)
    trade_logger.addHandler(trade_handler)
    
    # Add timestamp and status
    trade_data["timestamp"] = datetime.now().isoformat()
    trade_data["success"] = success
    
    # Log trade as JSON
    trade_logger.info(json.dumps(trade_data))
    
    # Also log to a JSON file for analytics
    try:
        trades_json_file = logs_dir / "trades.json"
        
        # Read existing trades if file exists
        if trades_json_file.exists():
            with open(trades_json_file, 'r') as f:
                try:
                    trades = json.load(f)
                except json.JSONDecodeError:
                    trades = []
        else:
            trades = []
        
        # Append new trade
        trades.append(trade_data)
        
        # Write updated trades
        with open(trades_json_file, 'w') as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        # Log error but don't crash
        logging.getLogger("logger").error(f"Error writing trade to JSON: {str(e)}")

def log_performance(component: str, metrics: Dict[str, Any]) -> None:
    """
    Log performance metrics
    
    Args:
        component: Name of the component being measured
        metrics: Dictionary of performance metrics
    """
    # Create performance logger
    perf_logger = logging.getLogger("performance")
    perf_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    if perf_logger.hasHandlers():
        perf_logger.handlers.clear()
    
    # Create file handler for performance logs
    perf_log_file = logs_dir / "performance.log"
    perf_handler = logging.FileHandler(perf_log_file)
    perf_handler.setLevel(logging.INFO)
    perf_formatter = logging.Formatter("%(asctime)s - %(message)s", DATE_FORMAT)
    perf_handler.setFormatter(perf_formatter)
    perf_logger.addHandler(perf_handler)
    
    # Add timestamp and component
    metrics["timestamp"] = datetime.now().isoformat()
    metrics["component"] = component
    
    # Log metrics as JSON
    perf_logger.info(json.dumps(metrics))
