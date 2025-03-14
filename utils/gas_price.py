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
                for tx in block['transactions']:
                    if isinstance(tx, dict) and 'gasPrice' in tx:
                        gas_prices.append(tx['gasPrice'])
            except Exception as e:
                logger.debug(f"Error getting block {block_num}: {str(e)}")
                continue
        
        # If we have enough data, calculate optimal gas price
        if gas_prices:
            # Sort gas prices
            gas_prices.sort()
            
            # Calculate percentiles
            if strategy == "fast":
                # 90th percentile for fast transactions
                optimal_gas = int(statistics.quantiles(gas_prices, n=10)[8])
                # Add 10% buffer for fast transactions
                optimal_gas = int(optimal_gas * 1.1)
            elif strategy == "economic":
                # 30th percentile for economic transactions
                optimal_gas = int(statistics.quantiles(gas_prices, n=10)[2])
            else:  # balanced
                # 50th percentile (median) for balanced transactions
                optimal_gas = int(statistics.median(gas_prices))
            
            # Ensure gas price is not too low
            if optimal_gas < gas_price:
                optimal_gas = gas_price
            
            # Update cache
            last_gas_price = optimal_gas
            last_gas_update = current_time
            
            return optimal_gas
        else:
            # If no data, use current gas price
            last_gas_price = gas_price
            last_gas_update = current_time
            return gas_price
            
    except Exception as e:
        logger.error(f"Error getting optimal gas price: {str(e)}")
        # Fallback to current gas price
        return w3.eth.gas_price

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
        
        # Get gas price
        gas_price = tx_params.get('gasPrice', await get_optimal_gas_price(w3))
        
        # Calculate cost in wei
        cost_wei = gas_estimate * gas_price
        
        # Convert to ETH
        cost_eth = w3.from_wei(cost_wei, 'ether')
        
        return float(cost_eth)
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
    
    # Apply safety margin (20%)
    cost_with_margin = cost_eth * 1.2
    
    # Check if profitable
    is_profitable = expected_profit_eth > cost_with_margin
    
    if is_profitable:
        logger.info(
            f"Transaction is profitable: "
            f"Expected profit: {expected_profit_eth:.6f} ETH, "
            f"Gas cost: {cost_eth:.6f} ETH, "
            f"Net profit: {expected_profit_eth - cost_eth:.6f} ETH"
        )
    else:
        logger.info(
            f"Transaction is not profitable: "
            f"Expected profit: {expected_profit_eth:.6f} ETH, "
            f"Gas cost: {cost_eth:.6f} ETH"
        )
    
    return is_profitable
