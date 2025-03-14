"""
Profit Predictor Module
Predicts future profitability of trades using historical data and market indicators
"""

import time
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os

from utils.logger import setup_logger
from utils.performance import PerformanceTracker

# Initialize logger
logger = setup_logger("ProfitPredictor")

class ProfitPredictor:
    """Predicts profitability of trades based on historical data and market conditions"""
    
    def __init__(self, history_file: str = "logs/trades.json"):
        """
        Initialize profit predictor
        
        Args:
            history_file: Path to trade history file
        """
        self.history_file = history_file
        self.trade_history = []
        self.strategy_metrics = {}
        self.exchange_metrics = {}
        self.pair_metrics = {}
        self.time_metrics = {}
        self.performance = PerformanceTracker("ProfitPredictor")
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        
        # Load trade history
        self.load_history()
        
        # Calculate initial metrics
        self.calculate_metrics()
    
    def load_history(self):
        """Load trade history from file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.trade_history = json.load(f)
                logger.info(f"Loaded {len(self.trade_history)} trades from history")
            else:
                logger.warning(f"Trade history file not found: {self.history_file}")
        except Exception as e:
            logger.error(f"Error loading trade history: {str(e)}")
    
    def save_history(self):
        """Save trade history to file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.trade_history, f, indent=2)
            logger.info(f"Saved {len(self.trade_history)} trades to history")
        except Exception as e:
            logger.error(f"Error saving trade history: {str(e)}")
    
    def add_trade(self, trade_data: Dict[str, Any]):
        """
        Add a trade to history
        
        Args:
            trade_data: Trade data dictionary
        """
        # Add timestamp if not present
        if 'timestamp' not in trade_data:
            trade_data['timestamp'] = time.time()
        
        # Add trade to history
        self.trade_history.append(trade_data)
        
        # Save history
        self.save_history()
        
        # Recalculate metrics
        self.calculate_metrics()
    
    def calculate_metrics(self):
        """Calculate metrics from trade history"""
        with self.performance.measure("calculate_metrics"):
            # Reset metrics
            self.strategy_metrics = {}
            self.exchange_metrics = {}
            self.pair_metrics = {}
            self.time_metrics = {
                'hourly': {},
                'daily': {},
                'weekly': {}
            }
            
            # Process each trade
            for trade in self.trade_history:
                self._process_trade_for_metrics(trade)
            
            logger.debug("Metrics calculated from trade history")
    
    def _process_trade_for_metrics(self, trade: Dict[str, Any]):
        """
        Process a trade for metrics calculation
        
        Args:
            trade: Trade data dictionary
        """
        # Extract key data
        strategy = trade.get('strategy', 'unknown')
        source_exchange = trade.get('source_exchange', 'unknown')
        target_exchange = trade.get('target_exchange', 'unknown')
        token_symbol = trade.get('token_symbol', 'unknown')
        profit = trade.get('profit', 0)
        timestamp = trade.get('timestamp', 0)
        
        # Update strategy metrics
        if strategy not in self.strategy_metrics:
            self.strategy_metrics[strategy] = {
                'count': 0,
                'total_profit': 0,
                'avg_profit': 0,
                'success_rate': 0,
                'profitable_trades': 0
            }
        
        self.strategy_metrics[strategy]['count'] += 1
        self.strategy_metrics[strategy]['total_profit'] += profit
        
        if profit > 0:
            self.strategy_metrics[strategy]['profitable_trades'] += 1
        
        self.strategy_metrics[strategy]['avg_profit'] = (
            self.strategy_metrics[strategy]['total_profit'] / 
            self.strategy_metrics[strategy]['count']
        )
        
        self.strategy_metrics[strategy]['success_rate'] = (
            self.strategy_metrics[strategy]['profitable_trades'] / 
            self.strategy_metrics[strategy]['count']
        )
        
        # Update exchange metrics
        for exchange in [source_exchange, target_exchange]:
            if exchange not in self.exchange_metrics:
                self.exchange_metrics[exchange] = {
                    'count': 0,
                    'total_profit': 0,
                    'avg_profit': 0
                }
            
            self.exchange_metrics[exchange]['count'] += 1
            self.exchange_metrics[exchange]['total_profit'] += profit
            self.exchange_metrics[exchange]['avg_profit'] = (
                self.exchange_metrics[exchange]['total_profit'] / 
                self.exchange_metrics[exchange]['count']
            )
        
        # Update pair metrics
        pair = f"{source_exchange}_{target_exchange}"
        if pair not in self.pair_metrics:
            self.pair_metrics[pair] = {
                'count': 0,
                'total_profit': 0,
                'avg_profit': 0,
                'tokens': {}
            }
        
        self.pair_metrics[pair]['count'] += 1
        self.pair_metrics[pair]['total_profit'] += profit
        self.pair_metrics[pair]['avg_profit'] = (
            self.pair_metrics[pair]['total_profit'] / 
            self.pair_metrics[pair]['count']
        )
        
        # Update token metrics for this pair
        if token_symbol not in self.pair_metrics[pair]['tokens']:
            self.pair_metrics[pair]['tokens'][token_symbol] = {
                'count': 0,
                'total_profit': 0,
                'avg_profit': 0
            }
        
        self.pair_metrics[pair]['tokens'][token_symbol]['count'] += 1
        self.pair_metrics[pair]['tokens'][token_symbol]['total_profit'] += profit
        self.pair_metrics[pair]['tokens'][token_symbol]['avg_profit'] = (
            self.pair_metrics[pair]['tokens'][token_symbol]['total_profit'] / 
            self.pair_metrics[pair]['tokens'][token_symbol]['count']
        )
        
        # Update time metrics
        trade_time = datetime.fromtimestamp(timestamp)
        
        # Hourly metrics
        hour_key = trade_time.strftime('%H')
        if hour_key not in self.time_metrics['hourly']:
            self.time_metrics['hourly'][hour_key] = {
                'count': 0,
                'total_profit': 0,
                'avg_profit': 0
            }
        
        self.time_metrics['hourly'][hour_key]['count'] += 1
        self.time_metrics['hourly'][hour_key]['total_profit'] += profit
        self.time_metrics['hourly'][hour_key]['avg_profit'] = (
            self.time_metrics['hourly'][hour_key]['total_profit'] / 
            self.time_metrics['hourly'][hour_key]['count']
        )
        
        # Daily metrics
        day_key = trade_time.strftime('%a')  # Day of week abbreviation
        if day_key not in self.time_metrics['daily']:
            self.time_metrics['daily'][day_key] = {
                'count': 0,
                'total_profit': 0,
                'avg_profit': 0
            }
        
        self.time_metrics['daily'][day_key]['count'] += 1
        self.time_metrics['daily'][day_key]['total_profit'] += profit
        self.time_metrics['daily'][day_key]['avg_profit'] = (
            self.time_metrics['daily'][day_key]['total_profit'] / 
            self.time_metrics['daily'][day_key]['count']
        )
    
    def predict_profit(self, strategy: str, source_exchange: str, target_exchange: str, 
                      token_symbol: str, amount: float) -> Dict[str, Any]:
        """
        Predict profit for a potential trade
        
        Args:
            strategy: Trading strategy
            source_exchange: Source exchange
            target_exchange: Target exchange
            token_symbol: Token symbol
            amount: Trade amount
            
        Returns:
            Dictionary with profit prediction and confidence
        """
        with self.performance.measure("predict_profit"):
            # Default prediction
            prediction = {
                'expected_profit': 0,
                'confidence': 0,
                'factors': {}
            }
            
            # Check if we have enough data
            if len(self.trade_history) < 10:
                logger.warning("Not enough trade history for accurate prediction")
                prediction['confidence'] = 0.1
                return prediction
            
            # Strategy factor
            strategy_factor = self._get_strategy_factor(strategy)
            prediction['factors']['strategy'] = strategy_factor
            
            # Exchange pair factor
            pair_factor = self._get_pair_factor(source_exchange, target_exchange, token_symbol)
            prediction['factors']['pair'] = pair_factor
            
            # Time factor
            time_factor = self._get_time_factor()
            prediction['factors']['time'] = time_factor
            
            # Market conditions factor (placeholder - would need external data)
            market_factor = 1.0
            prediction['factors']['market'] = market_factor
            
            # Calculate combined factor
            combined_factor = (
                strategy_factor * 0.4 +
                pair_factor * 0.4 +
                time_factor * 0.1 +
                market_factor * 0.1
            )
            
            # Get baseline profit expectation
            baseline_profit = self._get_baseline_profit(strategy, source_exchange, target_exchange, token_symbol)
            
            # Scale by amount (assuming linear relationship)
            expected_profit = baseline_profit * (amount / 1.0) * combined_factor
            
            # Calculate confidence based on data availability
            confidence = self._calculate_confidence(strategy, source_exchange, target_exchange, token_symbol)
            
            # Update prediction
            prediction['expected_profit'] = expected_profit
            prediction['confidence'] = confidence
            
            return prediction
    
    def _get_strategy_factor(self, strategy: str) -> float:
        """
        Get factor based on strategy performance
        
        Args:
            strategy: Trading strategy
            
        Returns:
            Strategy performance factor
        """
        if strategy in self.strategy_metrics:
            metrics = self.strategy_metrics[strategy]
            
            # If strategy has been profitable, return a factor > 1
            if metrics['avg_profit'] > 0:
                # Scale based on success rate
                return 1.0 + (metrics['success_rate'] * 0.5)
            else:
                # If not profitable, return a factor < 1
                return 0.5
        else:
            # No data for this strategy
            return 1.0
    
    def _get_pair_factor(self, source_exchange: str, target_exchange: str, token_symbol: str) -> float:
        """
        Get factor based on exchange pair and token performance
        
        Args:
            source_exchange: Source exchange
            target_exchange: Target exchange
            token_symbol: Token symbol
            
        Returns:
            Pair performance factor
        """
        pair = f"{source_exchange}_{target_exchange}"
        
        if pair in self.pair_metrics:
            pair_metrics = self.pair_metrics[pair]
            
            # Check if we have data for this token
            if token_symbol in pair_metrics['tokens']:
                token_metrics = pair_metrics['tokens'][token_symbol]
                
                # If token has been profitable on this pair, return a factor > 1
                if token_metrics['avg_profit'] > 0:
                    return 1.0 + min(token_metrics['avg_profit'] * 2, 1.0)
                else:
                    return 0.5
            else:
                # No data for this token, use overall pair metrics
                if pair_metrics['avg_profit'] > 0:
                    return 1.0 + min(pair_metrics['avg_profit'], 0.5)
                else:
                    return 0.7
        else:
            # No data for this pair
            return 1.0
    
    def _get_time_factor(self) -> float:
        """
        Get factor based on time of day and day of week
        
        Returns:
            Time performance factor
        """
        current_time = datetime.now()
        hour_key = current_time.strftime('%H')
        day_key = current_time.strftime('%a')
        
        hour_factor = 1.0
        day_factor = 1.0
        
        # Check hourly metrics
        if hour_key in self.time_metrics['hourly']:
            hour_metrics = self.time_metrics['hourly'][hour_key]
            if hour_metrics['avg_profit'] > 0:
                hour_factor = 1.0 + min(hour_metrics['avg_profit'], 0.5)
            else:
                hour_factor = 0.8
        
        # Check daily metrics
        if day_key in self.time_metrics['daily']:
            day_metrics = self.time_metrics['daily'][day_key]
            if day_metrics['avg_profit'] > 0:
                day_factor = 1.0 + min(day_metrics['avg_profit'], 0.3)
            else:
                day_factor = 0.9
        
        # Combine factors (weighted)
        return (hour_factor * 0.7) + (day_factor * 0.3)
    
    def _get_baseline_profit(self, strategy: str, source_exchange: str, target_exchange: str, token_symbol: str) -> float:
        """
        Get baseline profit expectation
        
        Args:
            strategy: Trading strategy
            source_exchange: Source exchange
            target_exchange: Target exchange
            token_symbol: Token symbol
            
        Returns:
            Baseline profit expectation
        """
        # Try to get token-specific profit for this pair
        pair = f"{source_exchange}_{target_exchange}"
        if pair in self.pair_metrics and token_symbol in self.pair_metrics[pair]['tokens']:
            return self.pair_metrics[pair]['tokens'][token_symbol]['avg_profit']
        
        # Try to get overall pair profit
        if pair in self.pair_metrics:
            return self.pair_metrics[pair]['avg_profit']
        
        # Try to get strategy profit
        if strategy in self.strategy_metrics:
            return self.strategy_metrics[strategy]['avg_profit']
        
        # Default to small positive value
        return 0.001
    
    def _calculate_confidence(self, strategy: str, source_exchange: str, target_exchange: str, token_symbol: str) -> float:
        """
        Calculate confidence in prediction
        
        Args:
            strategy: Trading strategy
            source_exchange: Source exchange
            target_exchange: Target exchange
            token_symbol: Token symbol
            
        Returns:
            Confidence score (0-1)
        """
        # Start with base confidence
        confidence = 0.5
        
        # Adjust based on data availability
        pair = f"{source_exchange}_{target_exchange}"
        
        # Strategy data
        if strategy in self.strategy_metrics:
            strategy_count = self.strategy_metrics[strategy]['count']
            confidence += min(strategy_count / 100, 0.1)
        
        # Pair data
        if pair in self.pair_metrics:
            pair_count = self.pair_metrics[pair]['count']
            confidence += min(pair_count / 50, 0.2)
            
            # Token-specific data
            if token_symbol in self.pair_metrics[pair]['tokens']:
                token_count = self.pair_metrics[pair]['tokens'][token_symbol]['count']
                confidence += min(token_count / 20, 0.2)
        
        # Cap confidence at 1.0
        return min(confidence, 1.0)
    
    def get_best_pairs(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Get the best performing exchange pairs
        
        Args:
            top_n: Number of pairs to return
            
        Returns:
            List of best performing pairs with metrics
        """
        # Sort pairs by average profit
        sorted_pairs = sorted(
            self.pair_metrics.items(),
            key=lambda x: x[1]['avg_profit'],
            reverse=True
        )
        
        # Return top N pairs
        return [
            {
                'pair': pair,
                'avg_profit': metrics['avg_profit'],
                'count': metrics['count'],
                'total_profit': metrics['total_profit']
            }
            for pair, metrics in sorted_pairs[:top_n]
        ]
    
    def get_best_tokens(self, pair: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Get the best performing tokens for a specific exchange pair
        
        Args:
            pair: Exchange pair (e.g., "uniswap_sushiswap")
            top_n: Number of tokens to return
            
        Returns:
            List of best performing tokens with metrics
        """
        if pair not in self.pair_metrics:
            return []
        
        # Sort tokens by average profit
        sorted_tokens = sorted(
            self.pair_metrics[pair]['tokens'].items(),
            key=lambda x: x[1]['avg_profit'],
            reverse=True
        )
        
        # Return top N tokens
        return [
            {
                'token': token,
                'avg_profit': metrics['avg_profit'],
                'count': metrics['count'],
                'total_profit': metrics['total_profit']
            }
            for token, metrics in sorted_tokens[:top_n]
        ]
