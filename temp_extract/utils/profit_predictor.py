"""
Profit Predictor Module
Predicts future profitability of trades using historical data and market indicators
"""

import time
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

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
        
        # Load trade history
        self.load_history()
        
        # Calculate initial metrics
        self.calculate_metrics()
    
    def load_history(self):
        """Load trade history from file"""
        try:
            import os
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.trade_history = json.load(f)
                logger.info(f"Loaded {len(self.trade_history)} trades from history")
            else:
                logger.warning(f"Trade history file not found: {self.history_file}")
        except Exception as e:
            logger.error(f"Error loading trade history: {str(e)}")
    
    def calculate_metrics(self):
        """Calculate metrics from trade history"""
        if not self.trade_history:
            logger.warning("No trade history to calculate metrics")
            return
        
        # Reset metrics
        self.strategy_metrics = {}
        self.exchange_metrics = {}
        self.pair_metrics = {}
        self.time_metrics = {}
        
        # Process trades
        for trade in self.trade_history:
            self._process_trade_for_metrics(trade)
        
        # Calculate success rates and average profits
        self._calculate_success_rates()
        
        logger.info(f"Calculated metrics from {len(self.trade_history)} trades")
    
    def _process_trade_for_metrics(self, trade: Dict[str, Any]):
        """Process a single trade for metrics calculation"""
        # Get trade details
        strategy = trade.get("strategy", "Unknown")
        exchange_1 = trade.get("exchange_1", "Unknown")
        exchange_2 = trade.get("exchange_2", "Unknown")
        pair = trade.get("pair", "Unknown")
        profit_expected = trade.get("profit_expected", 0)
        profit_realized = trade.get("profit_realized", 0)
        order_status = trade.get("order_status", "unknown")
        timestamp = trade.get("timestamp", "")
        
        # Initialize metrics if needed
        if strategy not in self.strategy_metrics:
            self.strategy_metrics[strategy] = {"count": 0, "success": 0, "profit": 0, "expected": 0}
        
        for exchange in [exchange_1, exchange_2]:
            if exchange not in self.exchange_metrics:
                self.exchange_metrics[exchange] = {"count": 0, "success": 0, "profit": 0, "expected": 0}
        
        if pair not in self.pair_metrics:
            self.pair_metrics[pair] = {"count": 0, "success": 0, "profit": 0, "expected": 0}
        
        # Extract time components
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            hour = dt.hour
            day = dt.strftime("%A")  # Day of week
            
            if hour not in self.time_metrics:
                self.time_metrics[hour] = {"count": 0, "success": 0, "profit": 0, "expected": 0}
            
            if day not in self.time_metrics:
                self.time_metrics[day] = {"count": 0, "success": 0, "profit": 0, "expected": 0}
        except Exception:
            pass
        
        # Update strategy metrics
        self.strategy_metrics[strategy]["count"] += 1
        if order_status == "filled":
            self.strategy_metrics[strategy]["success"] += 1
        self.strategy_metrics[strategy]["profit"] += profit_realized
        self.strategy_metrics[strategy]["expected"] += profit_expected
        
        # Update exchange metrics
        for exchange in [exchange_1, exchange_2]:
            self.exchange_metrics[exchange]["count"] += 1
            if order_status == "filled":
                self.exchange_metrics[exchange]["success"] += 1
            self.exchange_metrics[exchange]["profit"] += profit_realized / 2  # Split profit between exchanges
            self.exchange_metrics[exchange]["expected"] += profit_expected / 2
        
        # Update pair metrics
        self.pair_metrics[pair]["count"] += 1
        if order_status == "filled":
            self.pair_metrics[pair]["success"] += 1
        self.pair_metrics[pair]["profit"] += profit_realized
        self.pair_metrics[pair]["expected"] += profit_expected
        
        # Update time metrics if available
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            hour = dt.hour
            day = dt.strftime("%A")  # Day of week
            
            self.time_metrics[hour]["count"] += 1
            if order_status == "filled":
                self.time_metrics[hour]["success"] += 1
            self.time_metrics[hour]["profit"] += profit_realized
            self.time_metrics[hour]["expected"] += profit_expected
            
            self.time_metrics[day]["count"] += 1
            if order_status == "filled":
                self.time_metrics[day]["success"] += 1
            self.time_metrics[day]["profit"] += profit_realized
            self.time_metrics[day]["expected"] += profit_expected
        except Exception:
            pass
    
    def _calculate_success_rates(self):
        """Calculate success rates and other derived metrics"""
        # For strategies
        for strategy, metrics in self.strategy_metrics.items():
            if metrics["count"] > 0:
                metrics["success_rate"] = metrics["success"] / metrics["count"] * 100
                metrics["avg_profit"] = metrics["profit"] / metrics["count"]
                metrics["realization_rate"] = (metrics["profit"] / metrics["expected"] * 100 
                                            if metrics["expected"] > 0 else 0)
            else:
                metrics["success_rate"] = 0
                metrics["avg_profit"] = 0
                metrics["realization_rate"] = 0
        
        # For exchanges
        for exchange, metrics in self.exchange_metrics.items():
            if metrics["count"] > 0:
                metrics["success_rate"] = metrics["success"] / metrics["count"] * 100
                metrics["avg_profit"] = metrics["profit"] / metrics["count"]
                metrics["realization_rate"] = (metrics["profit"] / metrics["expected"] * 100 
                                            if metrics["expected"] > 0 else 0)
            else:
                metrics["success_rate"] = 0
                metrics["avg_profit"] = 0
                metrics["realization_rate"] = 0
        
        # For pairs
        for pair, metrics in self.pair_metrics.items():
            if metrics["count"] > 0:
                metrics["success_rate"] = metrics["success"] / metrics["count"] * 100
                metrics["avg_profit"] = metrics["profit"] / metrics["count"]
                metrics["realization_rate"] = (metrics["profit"] / metrics["expected"] * 100 
                                            if metrics["expected"] > 0 else 0)
            else:
                metrics["success_rate"] = 0
                metrics["avg_profit"] = 0
                metrics["realization_rate"] = 0
        
        # For time metrics
        for time_key, metrics in self.time_metrics.items():
            if metrics["count"] > 0:
                metrics["success_rate"] = metrics["success"] / metrics["count"] * 100
                metrics["avg_profit"] = metrics["profit"] / metrics["count"]
                metrics["realization_rate"] = (metrics["profit"] / metrics["expected"] * 100 
                                            if metrics["expected"] > 0 else 0)
            else:
                metrics["success_rate"] = 0
                metrics["avg_profit"] = 0
                metrics["realization_rate"] = 0
    
    def predict_profitability(
        self,
        strategy: str,
        exchange_1: str,
        exchange_2: str,
        pair: str,
        expected_profit: float,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Predict profitability of a trade based on historical data
        
        Args:
            strategy: Trading strategy
            exchange_1: First exchange
            exchange_2: Second exchange
            pair: Trading pair
            expected_profit: Expected profit
            timestamp: Optional timestamp for time-based prediction
            
        Returns:
            Dictionary with prediction results
        """
        # Default prediction
        prediction = {
            "expected_profit": expected_profit,
            "predicted_profit": expected_profit,
            "confidence": 0.5,
            "success_probability": 0.5,
            "adjusted_expectation": expected_profit * 0.5,
            "recommendation": "neutral"
        }
        
        # Get metrics for this strategy
        strategy_metrics = self.strategy_metrics.get(strategy, {})
        strategy_success_rate = strategy_metrics.get("success_rate", 50) / 100
        strategy_realization = strategy_metrics.get("realization_rate", 100) / 100
        
        # Get metrics for these exchanges
        exchange_1_metrics = self.exchange_metrics.get(exchange_1, {})
        exchange_2_metrics = self.exchange_metrics.get(exchange_2, {})
        exchange_1_success_rate = exchange_1_metrics.get("success_rate", 50) / 100
        exchange_2_success_rate = exchange_2_metrics.get("success_rate", 50) / 100
        exchange_1_realization = exchange_1_metrics.get("realization_rate", 100) / 100
        exchange_2_realization = exchange_2_metrics.get("realization_rate", 100) / 100
        
        # Get metrics for this pair
        pair_metrics = self.pair_metrics.get(pair, {})
        pair_success_rate = pair_metrics.get("success_rate", 50) / 100
        pair_realization = pair_metrics.get("realization_rate", 100) / 100
        
        # Time-based metrics if timestamp is provided
        time_success_rate = 0.5
        time_realization = 1.0
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                hour = dt.hour
                day = dt.strftime("%A")  # Day of week
                
                hour_metrics = self.time_metrics.get(hour, {})
                day_metrics = self.time_metrics.get(day, {})
                
                hour_success_rate = hour_metrics.get("success_rate", 50) / 100
                day_success_rate = day_metrics.get("success_rate", 50) / 100
                
                hour_realization = hour_metrics.get("realization_rate", 100) / 100
                day_realization = day_metrics.get("realization_rate", 100) / 100
                
                # Average time-based metrics
                time_success_rate = (hour_success_rate + day_success_rate) / 2
                time_realization = (hour_realization + day_realization) / 2
            except Exception:
                pass
        
        # Calculate combined metrics
        # Higher weight on strategy and pair metrics
        weights = {
            "strategy": 0.4,
            "exchanges": 0.2,
            "pair": 0.3,
            "time": 0.1
        }
        
        # Calculate combined success probability
        success_probability = (
            weights["strategy"] * strategy_success_rate +
            weights["exchanges"] * (exchange_1_success_rate + exchange_2_success_rate) / 2 +
            weights["pair"] * pair_success_rate +
            weights["time"] * time_success_rate
        )
        
        # Calculate combined realization rate
        realization_rate = (
            weights["strategy"] * strategy_realization +
            weights["exchanges"] * (exchange_1_realization + exchange_2_realization) / 2 +
            weights["pair"] * pair_realization +
            weights["time"] * time_realization
        )
        
        # Calculate confidence based on data points
        strategy_count = strategy_metrics.get("count", 0)
        exchange_1_count = exchange_1_metrics.get("count", 0)
        exchange_2_count = exchange_2_metrics.get("count", 0)
        pair_count = pair_metrics.get("count", 0)
        
        total_count = strategy_count + exchange_1_count + exchange_2_count + pair_count
        confidence = min(0.95, total_count / 100) if total_count > 0 else 0.5
        
        # Adjust expected profit based on realization rate
        predicted_profit = expected_profit * realization_rate
        
        # Calculate adjusted expectation (expected value)
        adjusted_expectation = predicted_profit * success_probability
        
        # Determine recommendation
        recommendation = "neutral"
        if adjusted_expectation > expected_profit * 0.7:
            recommendation = "strong_buy"
        elif adjusted_expectation > expected_profit * 0.5:
            recommendation = "buy"
        elif adjusted_expectation < expected_profit * 0.3:
            recommendation = "strong_avoid"
        elif adjusted_expectation < expected_profit * 0.5:
            recommendation = "avoid"
        
        # Update prediction
        prediction.update({
            "predicted_profit": predicted_profit,
            "confidence": confidence,
            "success_probability": success_probability,
            "adjusted_expectation": adjusted_expectation,
            "recommendation": recommendation
        })
        
        return prediction
    
    def historical_success_rate(self, strategy: str, exchange_1: str, exchange_2: str, pair: str) -> float:
        """
        Get historical success rate for a specific combination
        
        Args:
            strategy: Trading strategy
            exchange_1: First exchange
            exchange_2: Second exchange
            pair: Trading pair
            
        Returns:
            Success rate as a percentage
        """
        # Get relevant metrics
        strategy_metrics = self.strategy_metrics.get(strategy, {})
        strategy_success = strategy_metrics.get("success_rate", 50)
        
        exchange_1_metrics = self.exchange_metrics.get(exchange_1, {})
        exchange_2_metrics = self.exchange_metrics.get(exchange_2, {})
        exchange_1_success = exchange_1_metrics.get("success_rate", 50)
        exchange_2_success = exchange_2_metrics.get("success_rate", 50)
        exchange_success = (exchange_1_success + exchange_2_success) / 2
        
        pair_metrics = self.pair_metrics.get(pair, {})
        pair_success = pair_metrics.get("success_rate", 50)
        
        # Combine with weights
        weights = {
            "strategy": 0.4,
            "exchanges": 0.3,
            "pair": 0.3
        }
        
        combined_success_rate = (
            weights["strategy"] * strategy_success +
            weights["exchanges"] * exchange_success +
            weights["pair"] * pair_success
        )
        
        return combined_success_rate
    
    def expected_slippage(self, strategy: str, exchange_1: str, exchange_2: str, pair: str) -> float:
        """
        Estimate expected slippage based on historical data
        
        Args:
            strategy: Trading strategy
            exchange_1: First exchange
            exchange_2: Second exchange
            pair: Trading pair
            
        Returns:
            Expected slippage percentage
        """
        # This would analyze historical slippage from the trade history
        # For now, return a simplified estimate based on strategy and exchanges
        
        slippage_estimate = 0.2  # Default estimate (0.2%)
        
        # Adjust based on strategy
        if strategy == "Flash Loan":
            slippage_estimate *= 1.5  # Higher slippage for flash loans
        elif strategy == "DEX Arbitrage":
            slippage_estimate *= 1.3  # Higher slippage for DEX
        
        # Adjust based on exchanges (simplified)
        for exchange in [exchange_1, exchange_2]:
            if "binance" in exchange.lower() or "bybit" in exchange.lower():
                slippage_estimate *= 0.9  # Lower slippage on major exchanges
            elif "uniswap" in exchange.lower() or "sushiswap" in exchange.lower():
                slippage_estimate *= 1.2  # Higher slippage on DEXes
        
        # Adjust based on pair (simplified)
        if "BTC" in pair or "ETH" in pair:
            slippage_estimate *= 0.8  # Lower slippage for major assets
        elif "USDT" in pair or "USDC" in pair:
            slippage_estimate *= 0.9  # Lower slippage for stablecoins
        
        return slippage_estimate
    
    def update_with_trade(self, trade: Dict[str, Any]):
        """
        Update metrics with a new trade
        
        Args:
            trade: Trade data dictionary
        """
        # Add to history
        self.trade_history.append(trade)
        
        # Process for metrics
        self._process_trade_for_metrics(trade)
        
        # Recalculate success rates
        self._calculate_success_rates()