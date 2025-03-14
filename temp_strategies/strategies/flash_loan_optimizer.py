"""
Flash Loan Optimizer
Optimizes flash loan execution for maximum efficiency and minimal gas costs
"""

import time
import asyncio
from web3 import Web3
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from dataclasses import dataclass

from utils.config import load_config
from utils.logger import setup_logger
from utils.performance import measure_execution_time
from utils.gas_price import get_optimal_gas_price, estimate_gas_cost
from utils.mempool_monitor import MempoolMonitor

@dataclass
class OptimizationResult:
    """Data class for optimization results"""
    optimal_amount: float
    estimated_profit: float
    estimated_gas_cost: float
    net_profit: float
    execution_path: List[str]
    confidence_score: float
    execution_time_estimate_ms: int
    slippage_estimate: float
    priority_fee: int
    max_fee_per_gas: int

class FlashLoanOptimizer:
    """
    Optimizes flash loan parameters for maximum profitability
    - Determines optimal loan amount
    - Calculates gas costs and net profitability
    - Optimizes execution path
    - Estimates slippage based on historical data
    - Provides optimal gas settings for competitive MEV
    """
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("FlashLoanOptimizer")
        
        # Initialize web3 connection
        self.w3 = Web3(Web3.HTTPProvider(self.config.WEB3_PROVIDER_URL))
        
        # Historical slippage data for prediction
        self.historical_slippage = {}
        
        # Gas price history for prediction
        self.gas_price_history = []
        
        # Mempool monitor for competitive gas pricing
        self.mempool_monitor = None
        
        # Performance metrics
        self.execution_time_history = {}
        
        # Optimization parameters
        self.min_confidence_threshold = 0.85
        self.max_slippage_tolerance = 0.03  # 3%
        self.gas_price_buffer = 1.15  # 15% buffer for competitive gas pricing
        
        self.logger.info("Flash Loan Optimizer initialized")
    
    async def initialize(self):
        """Initialize the optimizer with necessary connections"""
        self.logger.info("Initializing Flash Loan Optimizer")
        
        # Initialize mempool monitor for gas price optimization
        self.mempool_monitor = MempoolMonitor(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            private_key=self.config.PRIVATE_KEY
        )
        
        # Load historical data if available
        self._load_historical_data()
        
        self.logger.info("Flash Loan Optimizer initialized successfully")
    
    async def shutdown(self):
        """Clean up resources"""
        self.logger.info("Shutting down Flash Loan Optimizer")
        
        # Save historical data for future use
        self._save_historical_data()
        
        # Shutdown mempool monitor if initialized
        if self.mempool_monitor:
            await self.mempool_monitor.shutdown()
    
    def _load_historical_data(self):
        """Load historical data for optimization"""
        try:
            # Implementation to load historical slippage and gas data
            # This would typically load from a database or file
            pass
        except Exception as e:
            self.logger.error(f"Error loading historical data: {str(e)}")
    
    def _save_historical_data(self):
        """Save historical data for future use"""
        try:
            # Implementation to save historical data
            pass
        except Exception as e:
            self.logger.error(f"Error saving historical data: {str(e)}")
    
    @measure_execution_time
    async def optimize_flash_loan(
        self,
        token_address: str,
        source_dex: str,
        target_dex: str,
        path: List[str],
        price_difference: float,
        max_loan_amount: float
    ) -> OptimizationResult:
        """
        Optimize flash loan parameters for maximum profitability
        
        Args:
            token_address: Address of token to borrow
            source_dex: DEX to buy from
            target_dex: DEX to sell to
            path: Token swap path
            price_difference: Percentage price difference between DEXes
            max_loan_amount: Maximum loan amount to consider
            
        Returns:
            OptimizationResult with optimal parameters
        """
        self.logger.info(f"Optimizing flash loan for {token_address}")
        
        # Get current gas prices
        base_fee, priority_fee = await self._get_competitive_gas_price()
        
        # Calculate optimal loan amount based on price difference and gas costs
        optimal_amount = await self._calculate_optimal_amount(
            token_address,
            source_dex,
            target_dex,
            path,
            price_difference,
            max_loan_amount,
            base_fee,
            priority_fee
        )
        
        # Estimate gas cost
        gas_limit = self._estimate_gas_limit(path)
        gas_cost_wei = gas_limit * (base_fee + priority_fee)
        gas_cost_eth = self.w3.from_wei(gas_cost_wei, 'ether')
        
        # Get ETH price to convert gas cost to USD
        eth_price_usd = await self._get_eth_price_usd()
        gas_cost_usd = gas_cost_eth * eth_price_usd
        
        # Calculate expected profit
        loan_fee = optimal_amount * 0.0009  # 0.09% Aave flash loan fee
        expected_profit_before_gas = optimal_amount * price_difference / 100 - loan_fee
        net_profit = expected_profit_before_gas - gas_cost_usd
        
        # Estimate slippage based on amount and historical data
        estimated_slippage = self._estimate_slippage(token_address, optimal_amount)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            price_difference,
            estimated_slippage,
            net_profit,
            gas_cost_usd
        )
        
        # Estimate execution time
        execution_time_ms = self._estimate_execution_time(path)
        
        # Create optimization result
        result = OptimizationResult(
            optimal_amount=optimal_amount,
            estimated_profit=expected_profit_before_gas,
            estimated_gas_cost=gas_cost_usd,
            net_profit=net_profit,
            execution_path=path,
            confidence_score=confidence_score,
            execution_time_estimate_ms=execution_time_ms,
            slippage_estimate=estimated_slippage,
            priority_fee=priority_fee,
            max_fee_per_gas=base_fee + priority_fee
        )
        
        self.logger.info(f"Optimization result: {result}")
        return result
    
    async def _get_competitive_gas_price(self) -> Tuple[int, int]:
        """
        Get competitive gas price for MEV transactions
        
        Returns:
            Tuple of (base_fee, priority_fee) in wei
        """
        try:
            # Get current base fee
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            # Analyze mempool for competitive priority fee
            priority_fee = await self._analyze_mempool_for_priority_fee()
            
            # Ensure minimum priority fee
            min_priority_fee = self.w3.to_wei(1, 'gwei')
            if priority_fee < min_priority_fee:
                priority_fee = min_priority_fee
            
            return base_fee, priority_fee
            
        except Exception as e:
            self.logger.error(f"Error getting competitive gas price: {str(e)}")
            # Fallback to default values
            return self.w3.to_wei(50, 'gwei'), self.w3.to_wei(2, 'gwei')
    
    async def _analyze_mempool_for_priority_fee(self) -> int:
        """
        Analyze mempool to determine competitive priority fee
        
        Returns:
            Priority fee in wei
        """
        try:
            if not self.mempool_monitor:
                return self.w3.to_wei(2, 'gwei')
            
            # Get pending transactions
            pending_txs = await self.mempool_monitor.get_pending_transactions(limit=50)
            
            if not pending_txs:
                return self.w3.to_wei(2, 'gwei')
            
            # Extract priority fees from pending transactions
            priority_fees = []
            for tx in pending_txs:
                if 'maxPriorityFeePerGas' in tx:
                    priority_fees.append(tx['maxPriorityFeePerGas'])
            
            if not priority_fees:
                return self.w3.to_wei(2, 'gwei')
            
            # Calculate 75th percentile for competitive edge
            competitive_fee = np.percentile(priority_fees, 75)
            
            # Add buffer for higher chance of inclusion
            return int(competitive_fee * self.gas_price_buffer)
            
        except Exception as e:
            self.logger.error(f"Error analyzing mempool: {str(e)}")
            return self.w3.to_wei(2, 'gwei')
    
    async def _calculate_optimal_amount(
        self,
        token_address: str,
        source_dex: str,
        target_dex: str,
        path: List[str],
        price_difference: float,
        max_loan_amount: float,
        base_fee: int,
        priority_fee: int
    ) -> float:
        """
        Calculate optimal loan amount based on price difference and gas costs
        
        Returns:
            Optimal loan amount
        """
        # Simple optimization for now - can be expanded with more sophisticated models
        # Start with maximum and reduce if necessary
        optimal_amount = max_loan_amount
        
        # Calculate minimum profitable amount based on gas cost
        gas_limit = self._estimate_gas_limit(path)
        gas_cost_wei = gas_limit * (base_fee + priority_fee)
        gas_cost_eth = self.w3.from_wei(gas_cost_wei, 'ether')
        eth_price_usd = await self._get_eth_price_usd()
        gas_cost_usd = gas_cost_eth * eth_price_usd
        
        # Calculate minimum amount where profit exceeds gas cost with buffer
        min_profitable_amount = (gas_cost_usd * 3) / (price_difference / 100 - 0.0009)
        
        if min_profitable_amount > max_loan_amount:
            self.logger.warning(f"No profitable amount possible. Min required: {min_profitable_amount}, Max available: {max_loan_amount}")
            return 0
        
        # Check for liquidity constraints
        liquidity_limit = await self._check_liquidity_constraints(token_address, source_dex, target_dex, path)
        
        if liquidity_limit < min_profitable_amount:
            self.logger.warning(f"Insufficient liquidity. Required: {min_profitable_amount}, Available: {liquidity_limit}")
            return 0
        
        # Return the minimum of max loan amount and liquidity limit
        return min(max_loan_amount, liquidity_limit)
    
    async def _check_liquidity_constraints(
        self,
        token_address: str,
        source_dex: str,
        target_dex: str,
        path: List[str]
    ) -> float:
        """
        Check liquidity constraints on both DEXes
        
        Returns:
            Maximum amount that can be traded given liquidity
        """
        # This would typically query DEX contracts for liquidity
        # For now, return a conservative estimate
        return 1000000  # $1M as default limit
    
    def _estimate_gas_limit(self, path: List[str]) -> int:
        """
        Estimate gas limit based on path complexity
        
        Returns:
            Estimated gas limit
        """
        # Base gas for flash loan operations
        base_gas = 300000
        
        # Additional gas per swap
        swap_gas = 100000
        
        # Calculate total gas estimate
        total_gas = base_gas + (len(path) - 1) * swap_gas
        
        # Add safety buffer
        return int(total_gas * 1.2)
    
    async def _get_eth_price_usd(self) -> float:
        """
        Get current ETH price in USD
        
        Returns:
            ETH price in USD
        """
        # This would typically query an oracle or API
        # For now, return a fixed value
        return 3000.0
    
    def _estimate_slippage(self, token_address: str, amount: float) -> float:
        """
        Estimate slippage based on amount and historical data
        
        Returns:
            Estimated slippage as a percentage
        """
        # Base slippage estimate
        base_slippage = 0.005  # 0.5%
        
        # Adjust based on amount (larger amounts have higher slippage)
        amount_factor = min(1.0, amount / 1000000)  # Cap at 1.0 for amounts over $1M
        
        # Check historical slippage data if available
        token_history = self.historical_slippage.get(token_address, [])
        
        if token_history:
            # Use historical data to refine estimate
            historical_avg = sum(token_history) / len(token_history)
            return (base_slippage + amount_factor * 0.01) * (historical_avg / 0.005)
        else:
            # No historical data, use conservative estimate
            return base_slippage + amount_factor * 0.01
    
    def _calculate_confidence_score(
        self,
        price_difference: float,
        estimated_slippage: float,
        net_profit: float,
        gas_cost: float
    ) -> float:
        """
        Calculate confidence score for the arbitrage opportunity
        
        Returns:
            Confidence score between 0 and 1
        """
        # Factors affecting confidence
        slippage_factor = max(0, 1 - (estimated_slippage / (price_difference / 100)))
        profit_factor = min(1, net_profit / (gas_cost * 5))  # Profit should be at least 5x gas cost for high confidence
        
        # Combined confidence score
        confidence = (slippage_factor * 0.7) + (profit_factor * 0.3)
        
        return min(1.0, max(0.0, confidence))
    
    def _estimate_execution_time(self, path: List[str]) -> int:
        """
        Estimate execution time in milliseconds
        
        Returns:
            Estimated execution time in milliseconds
        """
        # Base execution time
        base_time = 200  # ms
        
        # Additional time per swap
        swap_time = 50  # ms
        
        # Calculate total time estimate
        total_time = base_time + (len(path) - 1) * swap_time
        
        return total_time
    
    def update_historical_data(self, token_address: str, actual_slippage: float, execution_time_ms: int):
        """
        Update historical data with actual execution results
        
        Args:
            token_address: Address of token
            actual_slippage: Actual slippage experienced
            execution_time_ms: Actual execution time in milliseconds
        """
        # Update slippage history
        if token_address not in self.historical_slippage:
            self.historical_slippage[token_address] = []
        
        # Keep last 100 data points
        if len(self.historical_slippage[token_address]) >= 100:
            self.historical_slippage[token_address].pop(0)
        
        self.historical_slippage[token_address].append(actual_slippage)
        
        # Update execution time history
        path_key = token_address
        if path_key not in self.execution_time_history:
            self.execution_time_history[path_key] = []
        
        # Keep last 100 data points
        if len(self.execution_time_history[path_key]) >= 100:
            self.execution_time_history[path_key].pop(0)
        
        self.execution_time_history[path_key].append(execution_time_ms)
