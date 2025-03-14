"""
Performance Tracking Module
Provides utilities for tracking and optimizing performance
"""

import time
import threading
import asyncio
import statistics
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("Performance")

class PerformanceTracker:
    """Tracks performance metrics for different components of the bot"""
    
    def __init__(self, component_name: str):
        """
        Initialize performance tracker
        
        Args:
            component_name: Name of the component being tracked
        """
        self.component_name = component_name
        self.metrics = {}
        self.lock = threading.Lock()
        
        # Initialize metrics dictionary
        self.reset_metrics()
        
        logger.debug(f"Performance tracker initialized for {component_name}")
    
    def reset_metrics(self):
        """Reset all metrics"""
        with self.lock:
            self.metrics = {
                'execution_times': {},
                'call_counts': {},
                'last_execution': {},
                'total_execution_time': 0,
                'start_time': time.time()
            }
    
    @contextmanager
    def measure(self, operation_name: str):
        """
        Context manager for measuring execution time of an operation
        
        Args:
            operation_name: Name of the operation being measured
        """
        start_time = time.time()
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            self._record_execution(operation_name, execution_time)
    
    def _record_execution(self, operation_name: str, execution_time: float):
        """
        Record execution time for an operation
        
        Args:
            operation_name: Name of the operation
            execution_time: Execution time in seconds
        """
        with self.lock:
            # Initialize if this is the first time seeing this operation
            if operation_name not in self.metrics['execution_times']:
                self.metrics['execution_times'][operation_name] = []
                self.metrics['call_counts'][operation_name] = 0
            
            # Record execution time
            self.metrics['execution_times'][operation_name].append(execution_time)
            self.metrics['call_counts'][operation_name] += 1
            self.metrics['last_execution'][operation_name] = time.time()
            self.metrics['total_execution_time'] += execution_time
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics
        
        Returns:
            Dictionary of performance metrics
        """
        with self.lock:
            metrics = {
                'component': self.component_name,
                'uptime': time.time() - self.metrics['start_time'],
                'total_execution_time': self.metrics['total_execution_time'],
                'operations': {}
            }
            
            # Calculate metrics for each operation
            for op_name in self.metrics['execution_times']:
                times = self.metrics['execution_times'][op_name]
                if not times:
                    continue
                
                # Calculate statistics
                avg_time = sum(times) / len(times)
                
                # Only calculate these if we have enough data
                if len(times) > 1:
                    min_time = min(times)
                    max_time = max(times)
                    median_time = statistics.median(times)
                    
                    # Calculate 95th percentile if we have enough data
                    if len(times) >= 20:
                        p95_time = statistics.quantiles(sorted(times), n=20)[19]
                    else:
                        p95_time = max_time
                else:
                    min_time = avg_time
                    max_time = avg_time
                    median_time = avg_time
                    p95_time = avg_time
                
                # Record operation metrics
                metrics['operations'][op_name] = {
                    'calls': self.metrics['call_counts'][op_name],
                    'avg_time': avg_time,
                    'min_time': min_time,
                    'max_time': max_time,
                    'median_time': median_time,
                    'p95_time': p95_time,
                    'total_time': sum(times),
                    'last_execution': self.metrics['last_execution'].get(op_name, 0)
                }
            
            return metrics
    
    def log_metrics(self, detailed: bool = False):
        """
        Log current performance metrics
        
        Args:
            detailed: Whether to log detailed metrics
        """
        metrics = self.get_metrics()
        
        logger.info(f"Performance metrics for {self.component_name}:")
        logger.info(f"  Uptime: {metrics['uptime']:.2f} seconds")
        logger.info(f"  Total execution time: {metrics['total_execution_time']:.2f} seconds")
        
        # Sort operations by total time (descending)
        sorted_ops = sorted(
            metrics['operations'].items(),
            key=lambda x: x[1]['total_time'],
            reverse=True
        )
        
        for op_name, op_metrics in sorted_ops:
            logger.info(f"  Operation: {op_name}")
            logger.info(f"    Calls: {op_metrics['calls']}")
            logger.info(f"    Avg time: {op_metrics['avg_time']:.6f} seconds")
            
            if detailed:
                logger.info(f"    Min time: {op_metrics['min_time']:.6f} seconds")
                logger.info(f"    Max time: {op_metrics['max_time']:.6f} seconds")
                logger.info(f"    Median time: {op_metrics['median_time']:.6f} seconds")
                logger.info(f"    P95 time: {op_metrics['p95_time']:.6f} seconds")
                logger.info(f"    Total time: {op_metrics['total_time']:.6f} seconds")
    
    def get_slow_operations(self, threshold: float = 0.1) -> List[str]:
        """
        Get list of operations that are slower than the threshold
        
        Args:
            threshold: Time threshold in seconds
            
        Returns:
            List of slow operation names
        """
        metrics = self.get_metrics()
        slow_ops = []
        
        for op_name, op_metrics in metrics['operations'].items():
            if op_metrics['avg_time'] > threshold:
                slow_ops.append(op_name)
        
        return slow_ops
