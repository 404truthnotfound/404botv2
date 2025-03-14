"""
Gas Price Optimization Module
Provides functions for optimizing gas prices for Ethereum transactions
"""

import time
import asyncio
import statistics
from web3 import Web3
from typing import Dict, List, Optional, Any

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("GasPrice")

# Gas price cache
last_gas_price = None
last_gas_update = 0
GAS_PRICE_CACHE_TTL = 30  # Cache gas price for 30 seconds

async def get_optimal_gas_price(w3: Web3, strategy: str = "balanced") -> int:
    """
    Get an optimal gas price based on current network conditions
    
    Args:
        w3: Web3 instance
        strategy: Gas price strategy ("fast", "balanced", "economic")
        
    Returns:
        Gas price in wei
    """
    global last_gas_price, last_gas_update
    
    # Check cache first
    current_time = time.time()
    if last_gas_price and (current_time - last_gas_update) < GAS_PRICE_CACHE_TTL:
        return last_gas_price
    
    try:
        # Get current gas price
        gas_price = w3.eth.gas_price
        
        # Get recent blocks to analyze gas prices
        latest_block = w3.eth.block_number
        gas_prices = []
        
        # Analyze last 10 blocks
        for block_num in range(latest_block - 10, latest_block):
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if hasattr(tx, 'gasPrice'):
                        gas_prices.append(tx.gasPrice)
            except Exception as e:
                logger.warning(f"Error getting block {block_num}: {str(e)}")
        
        # If we have enough data, use statistical analysis
        if len(gas_prices) >= 10:
            gas_prices.sort()
            
            # Different strategies
            if strategy == "fast":
                # 90th percentile for fast confirmation
                optimal_gas_price = gas_prices[int(len(gas_prices) * 0.9)]
            elif strategy == "economic":
                # 25th percentile for economic but slower confirmation
                optimal_gas_price = gas_prices[int(len(gas_prices) * 0.25)]
            else:  # balanced
                # Median (50th percentile) for balanced approach
                optimal_gas_price = statistics.median(gas_prices)
                
            # Add a small buffer (5%)
            optimal_gas_price = int(optimal_gas_price * 1.05)
        else:
            # Not enough data, use current gas price with adjustments
            if strategy == "fast":
                optimal_gas_price = int(gas_price * 1.2)  # 20% higher than current
            elif strategy == "economic":
                optimal_gas_price = int(gas_price * 0.9)  # 10% lower than current
            else:  # balanced
                optimal_gas_price = gas_price
        
        # Ensure minimum gas price
        min_gas_price = 1 * 10**9  # 1 Gwei
        optimal_gas_price = max(optimal_gas_price, min_gas_price)
        
        # Update cache
        last_gas_price = optimal_gas_price
        last_gas_update = current_time
        
        logger.info(f"Optimal gas price ({strategy}): {optimal_gas_price / 10**9:.2f} Gwei")
        return optimal_gas_price
        
    except Exception as e:
        logger.error(f"Error getting optimal gas price: {str(e)}")
        
        # Fallback to standard gas price
        standard_gas_price = 20 * 10**9  # 20 Gwei
        logger.warning(f"Using fallback gas price: {standard_gas_price / 10**9:.2f} Gwei")
        return standard_gas_price

async def estimate_transaction_cost(w3: Web3, tx_params: Dict[str, Any]) -> float:
    """
    Estimate the cost of a transaction in ETH
    
    Args:
        w3: Web3 instance
        tx_params: Transaction parameters
        
    Returns:
        Estimated cost in ETH
    """
    try:
        # Estimate gas
        gas_estimate = w3.eth.estimate_gas(tx_params)
        
        # Get gas price if not specified
        gas_price = tx_params.get('gasPrice')
        if not gas_price:
            gas_price = await get_optimal_gas_price(w3)
        
        # Calculate cost in wei
        cost_wei = gas_estimate * gas_price
        
        # Convert to ETH
        cost_eth = w3.from_wei(cost_wei, 'ether')
        
        logger.debug(f"Estimated transaction cost: {cost_eth:.6f} ETH (gas: {gas_estimate}, price: {gas_price / 10**9:.2f} Gwei)")
        return cost_eth
        
    except Exception as e:
        logger.error(f"Error estimating transaction cost: {str(e)}")
        return 0.0

async def is_transaction_profitable(w3: Web3, tx_params: Dict[str, Any], expected_profit_eth: float) -> bool:
    """
    Determine if a transaction is profitable after gas costs
    
    Args:
        w3: Web3 instance
        tx_params: Transaction parameters
        expected_profit_eth: Expected profit in ETH
        
    Returns:
        True if transaction is profitable, False otherwise
    """
    # Estimate transaction cost
    cost_eth = await estimate_transaction_cost(w3, tx_params)
    
    # Add a safety margin (20%)
    cost_with_margin = cost_eth * 1.2
    
    # Check if profitable
    is_profitable = expected_profit_eth > cost_with_margin
    
    if is_profitable:
        logger.info(f"Transaction is profitable: {expected_profit_eth:.6f} ETH profit, {cost_eth:.6f} ETH cost")
    else:
        logger.warning(f"Transaction is NOT profitable: {expected_profit_eth:.6f} ETH profit, {cost_eth:.6f} ETH cost")
    
    return is_profitable