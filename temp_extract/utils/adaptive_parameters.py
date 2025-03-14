"""
Adaptive Parameters Module
Dynamically adjusts trading parameters based on market conditions and execution results
"""

import time
import numpy as np
from typing import Dict, List, Optional, Any

from utils.config import load_config
from utils.logger import setup_logger

class AdaptiveParameters:
    """Class for dynamically adjusting trading parameters"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("AdaptiveParameters")
        
        # Initialize parameters
        self.min_profit_threshold = self.config.MIN_PROFIT_THRESHOLD
        self.slippage_tolerance = self.config.SLIPPAGE_TOLERANCE
        
        # Performance tracking
        self.execution_history = {
            "CEX Arbitrage": [],
            "DEX Arbitrage": [],
            "Triangular Arbitrage": [],
            "Flash Loan": []
        }
        
        # Exchange-specific adjustments
        self.exchange_performance = {}
        
        # Last parameter update time
        self.last_update_time = time.time()
        
        # Default weights for adaptations
        self.adaptation_weights = {
            "recent_success": 0.5,
            "slippage": 0.3,
            "profit_ratio": 0.2
        }
    
    def get_min_profit_threshold(self) -> float:
        """Get the current minimum profit threshold"""
        # Check if it's time to update parameters
        current_time = time.time()
        if current_time - self.last_update_time > 3600:  # Update hourly
            self._update_parameters()
            self.last_update_time = current_time
        
        return self.min_profit_threshold
    
    def get_slippage_tolerance(self) -> float:
        """Get the current slippage tolerance"""
        return self.slippage_tolerance
    
    def calculate_position_size(self, spread: float, max_size: float, 
                              exchange_1: str, exchange_2: str) -> float:
        """Calculate optimal position size based on spread and exchange performance"""
        # Base position sizing on spread size
        if spread < 0.2:
            base_size = 0.1 * max_size  # Very small spread = small position
        elif spread < 0.5:
            base_size = 0.25 * max_size  # Small spread = moderate position
        elif spread < 1.0:
            base_size = 0.5 * max_size   # Medium spread = medium position
        elif spread < 2.0:
            base_size = 0.75 * max_size  # Large spread = large position
        else:
            base_size = max_size          # Very large spread = max position
        
        # Adjust based on exchange performance
        exchange_1_factor = self._get_exchange_performance_factor(exchange_1)
        exchange_2_factor = self._get_exchange_performance_factor(exchange_2)
        
        # Combined factor (average of both exchanges)
        exchange_factor = (exchange_1_factor + exchange_2_factor) / 2
        
        # Apply exchange performance factor
        adjusted_size = base_size * exchange_factor
        
        # Ensure minimum viable trade size
        min_viable_size = 0.01 * max_size
        adjusted_size = max(adjusted_size, min_viable_size)
        
        # Round to appropriate precision based on asset
        return round(adjusted_size, 4)
    
    def calculate_flash_loan_size(self, profit_percentage: float, 
                               max_size: float, token: str) -> float:
        """Calculate optimal flash loan size based on profit and risk"""
        # For flash loans, we need to be more conservative due to gas costs
        if profit_percentage < 0.5:
            base_size = 0.1 * max_size  # Very small profit = small loan
        elif profit_percentage < 1.0:
            base_size = 0.3 * max_size  # Small profit = moderate loan
        elif profit_percentage < 2.0:
            base_size = 0.6 * max_size  # Medium profit = medium loan
        elif profit_percentage < 5.0:
            base_size = 0.8 * max_size  # Large profit = large loan
        else:
            base_size = max_size        # Very large profit = max loan
        
        # Adjust based on token volatility (simplified)
        token_factor = 1.0
        if token == "WETH" or token == "WBTC":
            token_factor = 1.0  # Major tokens are more reliable
        elif token in ["USDT", "USDC", "DAI"]:
            token_factor = 1.0  # Stablecoins are reliable
        else:
            token_factor = 0.7  # Other tokens have higher risk
        
        # Apply token factor
        adjusted_size = base_size * token_factor
        
        # Ensure minimum viable loan size for gas cost efficiency
        min_viable_size = 0.1 * max_size  # Higher minimum for flash loans
        adjusted_size = max(adjusted_size, min_viable_size)
        
        # Round to appropriate precision
        return round(adjusted_size, 4)
    
    def update_from_execution(self, opportunity):
        """Update parameters based on execution results"""
        strategy = opportunity.strategy
        exchange_1 = opportunity.exchange_1
        exchange_2 = opportunity.exchange_2
        
        # Add to execution history
        execution_record = {
            "timestamp": time.time(),
            "spread_percentage": opportunity.spread_percentage,
            "profit_expected": opportunity.profit_expected,
            "profit_realized": opportunity.profit_realized,
            "slippage": opportunity.slippage,
            "success": opportunity.order_status == "filled"
        }
        
        self.execution_history[strategy].append(execution_record)
        
        # Limit history size
        max_history = 100
        if len(self.execution_history[strategy]) > max_history:
            self.execution_history[strategy] = self.execution_history[strategy][-max_history:]
        
        # Update exchange performance
        for exchange in [exchange_1, exchange_2]:
            if exchange not in self.exchange_performance:
                self.exchange_performance[exchange] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "total_slippage": 0,
                    "execution_count": 0
                }
            
            perf = self.exchange_performance[exchange]
            perf["execution_count"] += 1
            
            if opportunity.order_status == "filled":
                perf["success_count"] += 1
            else:
                perf["failure_count"] += 1
                
            perf["total_slippage"] += opportunity.slippage
    
    def _update_parameters(self):
        """Update parameters based on recent execution history"""
        # Update min profit threshold based on recent slippage and success rate
        all_slippages = []
        all_success_rates = []
        all_profit_ratios = []
        
        for strategy, history in self.execution_history.items():
            if not history:
                continue
                
            # Get recent history (last 20 executions or fewer)
            recent_history = history[-20:]
            
            # Calculate average slippage
            slippages = [h["slippage"] for h in recent_history if h["slippage"] is not None]
            if slippages:
                avg_slippage = sum(slippages) / len(slippages)
                all_slippages.append(avg_slippage)
            
            # Calculate success rate
            success_count = sum(1 for h in recent_history if h["success"])
            success_rate = success_count / len(recent_history)
            all_success_rates.append(success_rate)
            
            # Calculate profit realization ratio
            profit_ratios = [h["profit_realized"] / h["profit_expected"] if h["profit_expected"] > 0 else 0
                           for h in recent_history if h["profit_realized"] is not None]
            if profit_ratios:
                avg_profit_ratio = sum(profit_ratios) / len(profit_ratios)
                all_profit_ratios.append(avg_profit_ratio)
        
        # Calculate new parameters if we have data
        if all_slippages and all_success_rates and all_profit_ratios:
            # Average metrics across all strategies
            avg_slippage = sum(all_slippages) / len(all_slippages)
            avg_success_rate = sum(all_success_rates) / len(all_success_rates)
            avg_profit_ratio = sum(all_profit_ratios) / len(all_profit_ratios)
            
            # Adjust min profit threshold
            # Higher slippage, lower success rate, or lower profit ratio = higher threshold
            slippage_factor = 1 + (avg_slippage / 10)  # 1% slippage = 1.1x factor
            success_factor = 2 - avg_success_rate      # 90% success = 1.1x factor, 50% success = 1.5x factor
            profit_factor = 1 + (1 - avg_profit_ratio) # 90% realized profit = 1.1x factor
            
            # Combine factors with weights
            combined_factor = (
                self.adaptation_weights["slippage"] * slippage_factor +
                self.adaptation_weights["recent_success"] * success_factor +
                self.adaptation_weights["profit_ratio"] * profit_factor
            )
            
            # Calculate new threshold
            base_threshold = self.config.MIN_PROFIT_THRESHOLD
            new_threshold = base_threshold * combined_factor
            
            # Apply bounds
            min_threshold = base_threshold * 0.5
            max_threshold = base_threshold * 3.0
            self.min_profit_threshold = max(min_threshold, min(new_threshold, max_threshold))
            
            # Adjust slippage tolerance
            self.slippage_tolerance = avg_slippage * 1.5  # Set to 1.5x recent average
            
            # Apply bounds to slippage tolerance
            min_slippage = self.config.SLIPPAGE_TOLERANCE * 0.5
            max_slippage = self.config.SLIPPAGE_TOLERANCE * 3.0
            self.slippage_tolerance = max(min_slippage, min(self.slippage_tolerance, max_slippage))
            
            self.logger.info(f"Updated parameters: min_profit_threshold={self.min_profit_threshold:.2f}%, " 
                         f"slippage_tolerance={self.slippage_tolerance:.2f}%")
    
    def _get_exchange_performance_factor(self, exchange: str) -> float:
        """Get performance factor for an exchange based on historical data"""
        if exchange not in self.exchange_performance:
            return 1.0  # Default for new exchanges
        
        perf = self.exchange_performance[exchange]
        
        # Calculate success rate
        total_executions = perf["execution_count"]
        if total_executions == 0:
            return 1.0
            
        success_rate = perf["success_count"] / total_executions
        
        # Calculate average slippage
        avg_slippage = perf["total_slippage"] / total_executions if total_executions > 0 else 0
        
        # Higher success rate = higher factor, higher slippage = lower factor
        success_component = success_rate * 1.5  # 100% success = 1.5, 50% success = 0.75
        slippage_component = 1 - (avg_slippage / 20)  # 0% slippage = 1.0, 10% slippage = 0.5
        
        # Ensure slippage component is at least 0.5
        slippage_component = max(0.5, slippage_component)
        
        # Combine components
        factor = (success_component + slippage_component) / 2
        
        # Ensure factor is between 0.5 and 1.5
        return max(0.5, min(factor, 1.5))