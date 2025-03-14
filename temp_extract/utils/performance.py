"""
Performance Tracking Module
Tracks and analyzes trading performance and system metrics
"""

import time
import functools
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, asdict

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("Performance")

# Decorator to measure function execution time
def measure_execution_time(func):
    """Decorator to measure and log function execution time"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Log execution time for functions taking longer than 0.1 seconds
        if execution_time > 0.1:
            logger.debug(f"{func.__name__} executed in {execution_time:.3f} seconds")
        
        return result
    return wrapper

class PerformanceTracker:
    """Tracks trading performance and system metrics"""
    
    def __init__(self, data_file: str = "logs/performance_data.json"):
        """
        Initialize the performance tracker
        
        Args:
            data_file: File to store performance data
        """
        self.data_file = data_file
        self.trades = []
        self.daily_stats = {}
        self.hourly_stats = {}
        self.execution_times = {}
        
        # Load existing data if available
        self.load_data()
    
    def load_data(self):
        """Load performance data from file"""
        try:
            import os
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                
                self.trades = data.get('trades', [])
                self.daily_stats = data.get('daily_stats', {})
                self.hourly_stats = data.get('hourly_stats', {})
                self.execution_times = data.get('execution_times', {})
                
                logger.info(f"Loaded performance data: {len(self.trades)} trades")
        except Exception as e:
            logger.error(f"Error loading performance data: {str(e)}")
    
    def save_data(self):
        """Save performance data to file"""
        try:
            import os
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            data = {
                'trades': self.trades,
                'daily_stats': self.daily_stats,
                'hourly_stats': self.hourly_stats,
                'execution_times': self.execution_times
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved performance data to {self.data_file}")
        except Exception as e:
            logger.error(f"Error saving performance data: {str(e)}")
    
    def record_trade(self, trade):
        """Record a completed trade"""
        # Convert to dict if not already
        if hasattr(trade, '__dict__'):
            trade_data = asdict(trade)
        else:
            trade_data = dict(trade)
        
        # Add timestamp if not present
        if 'timestamp' not in trade_data:
            trade_data['timestamp'] = datetime.utcnow().isoformat()
        
        # Add to trades list
        self.trades.append(trade_data)
        
        # Update daily and hourly stats
        self._update_time_based_stats(trade_data)
        
        # Save data periodically (every 10 trades)
        if len(self.trades) % 10 == 0:
            self.save_data()
    
    def record_execution_time(self, function_name: str, execution_time: float):
        """Record function execution time"""
        if function_name not in self.execution_times:
            self.execution_times[function_name] = {
                'count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0
            }
        
        stats = self.execution_times[function_name]
        stats['count'] += 1
        stats['total_time'] += execution_time
        stats['min_time'] = min(stats['min_time'], execution_time)
        stats['max_time'] = max(stats['max_time'], execution_time)
    
    def get_total_profit(self) -> float:
        """Get the total profit across all trades"""
        return sum(trade.get('profit_realized', 0) for trade in self.trades)
    
    def get_daily_profit(self) -> float:
        """Get the profit for the current day"""
        today = datetime.utcnow().date().isoformat()
        return self.daily_stats.get(today, {}).get('profit', 0)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        stats = {}
        
        # Calculate avg execution time for each function
        for func_name, func_stats in self.execution_times.items():
            if func_stats['count'] > 0:
                avg_time = func_stats['total_time'] / func_stats['count']
                stats[func_name] = {
                    'avg_time': round(avg_time, 3),
                    'min_time': round(func_stats['min_time'], 3),
                    'max_time': round(func_stats['max_time'], 3),
                    'count': func_stats['count']
                }
        
        return stats
    
    def get_strategy_performance(self) -> Dict[str, Any]:
        """Get performance metrics by strategy"""
        strategies = {}
        
        for trade in self.trades:
            strategy = trade.get('strategy')
            if not strategy:
                continue
            
            if strategy not in strategies:
                strategies[strategy] = {
                    'count': 0,
                    'profit': 0,
                    'success_count': 0,
                    'failure_count': 0
                }
            
            stats = strategies[strategy]
            stats['count'] += 1
            stats['profit'] += trade.get('profit_realized', 0)
            
            if trade.get('order_status') == 'filled':
                stats['success_count'] += 1
            elif trade.get('order_status') in ['failed', 'timeout']:
                stats['failure_count'] += 1
        
        # Calculate success rates
        for strategy, stats in strategies.items():
            if stats['count'] > 0:
                stats['success_rate'] = round(stats['success_count'] / stats['count'] * 100, 2)
            else:
                stats['success_rate'] = 0
        
        return strategies
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report"""
        report = {
            'total_trades': len(self.trades),
            'total_profit': self.get_total_profit(),
            'strategies': self.get_strategy_performance(),
            'execution_stats': self.get_execution_stats(),
            'daily_stats': self._get_recent_daily_stats(7),  # Last 7 days
            'hourly_stats': self._get_recent_hourly_stats(24)  # Last 24 hours
        }
        
        # Calculate overall success rate
        success_count = sum(1 for trade in self.trades if trade.get('order_status') == 'filled')
        if report['total_trades'] > 0:
            report['success_rate'] = round(success_count / report['total_trades'] * 100, 2)
        else:
            report['success_rate'] = 0
        
        # Calculate average profit per trade
        if report['total_trades'] > 0:
            report['avg_profit'] = round(report['total_profit'] / report['total_trades'], 4)
        else:
            report['avg_profit'] = 0
        
        return report
    
    def _update_time_based_stats(self, trade_data: Dict[str, Any]):
        """Update daily and hourly statistics"""
        # Get timestamp
        timestamp = trade_data.get('timestamp')
        if not timestamp:
            return
        
        try:
            dt = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            # Try parsing different format
            try:
                dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                logger.error(f"Invalid timestamp format: {timestamp}")
                return
        
        # Update daily stats
        day_key = dt.date().isoformat()
        if day_key not in self.daily_stats:
            self.daily_stats[day_key] = {
                'count': 0,
                'profit': 0,
                'success_count': 0,
                'failure_count': 0,
                'strategies': {}
            }
        
        day_stats = self.daily_stats[day_key]
        day_stats['count'] += 1
        day_stats['profit'] += trade_data.get('profit_realized', 0)
        
        if trade_data.get('order_status') == 'filled':
            day_stats['success_count'] += 1
        elif trade_data.get('order_status') in ['failed', 'timeout']:
            day_stats['failure_count'] += 1
        
        # Track by strategy
        strategy = trade_data.get('strategy')
        if strategy:
            if strategy not in day_stats['strategies']:
                day_stats['strategies'][strategy] = {
                    'count': 0,
                    'profit': 0
                }
            
            day_stats['strategies'][strategy]['count'] += 1
            day_stats['strategies'][strategy]['profit'] += trade_data.get('profit_realized', 0)
        
        # Update hourly stats
        hour_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        if hour_key not in self.hourly_stats:
            self.hourly_stats[hour_key] = {
                'count': 0,
                'profit': 0
            }
        
        hour_stats = self.hourly_stats[hour_key]
        hour_stats['count'] += 1
        hour_stats['profit'] += trade_data.get('profit_realized', 0)
    
    def _get_recent_daily_stats(self, days: int) -> Dict[str, Any]:
        """Get statistics for the most recent days"""
        today = datetime.utcnow().date()
        result = {}
        
        for i in range(days):
            day = (today - timedelta(days=i)).isoformat()
            if day in self.daily_stats:
                result[day] = self.daily_stats[day]
            else:
                result[day] = {
                    'count': 0,
                    'profit': 0,
                    'success_count': 0,
                    'failure_count': 0,
                    'strategies': {}
                }
        
        return result
    
    def _get_recent_hourly_stats(self, hours: int) -> Dict[str, Any]:
        """Get statistics for the most recent hours"""
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        result = {}
        
        for i in range(hours):
            hour = (now - timedelta(hours=i)).isoformat()
            if hour in self.hourly_stats:
                result[hour] = self.hourly_stats[hour]
            else:
                result[hour] = {
                    'count': 0,
                    'profit': 0
                }
        
        return result