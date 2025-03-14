"""
Profitability Analysis Module
Calculates and analyzes trade profitability considering all costs
"""

import asyncio
from typing import Dict, Any, Optional, Tuple
from web3 import Web3

from utils.logger import setup_logger
from utils.gas_price import estimate_transaction_cost, get_optimal_gas_price
from utils.web3_provider import get_web3, get_web3_provider

# Initialize logger
logger = setup_logger("Profitability")

async def calculate_profitability(
    w3: Web3,
    buy_price: float,
    sell_price: float,
    quantity: float,
    tx_params: Optional[Dict[str, Any]] = None,
    gas_cost_eth: Optional[float] = None,
    flash_loan_fee_percentage: float = 0.09,
    is_flash_loan: bool = False
) -> Tuple[float, float, bool]:
    """
    Calculate profitability of a trade considering all costs
    
    Args:
        w3: Web3 instance
        buy_price: Price to buy the asset
        sell_price: Price to sell the asset
        quantity: Quantity to trade
        tx_params: Transaction parameters (for gas estimation)
        gas_cost_eth: Optional pre-calculated gas cost in ETH
        flash_loan_fee_percentage: Flash loan fee as a percentage
        is_flash_loan: Whether this is a flash loan trade
        
    Returns:
        Tuple of (profit_usd, profit_percentage, is_profitable)
    """
    # Calculate raw profit
    raw_profit = (sell_price - buy_price) * quantity
    
    # Calculate transaction costs
    total_cost = 0.0
    
    # Flash loan fee if applicable
    if is_flash_loan:
        flash_loan_fee = (buy_price * quantity) * (flash_loan_fee_percentage / 100)
        total_cost += flash_loan_fee
    
    # Gas cost if provided or can be estimated
    if gas_cost_eth is not None:
        # Convert ETH gas cost to USD using a price oracle
        provider = await get_web3_provider()
        eth_price_usd = await provider.get_eth_price()
        gas_cost_usd = gas_cost_eth * eth_price_usd
        total_cost += gas_cost_usd
    elif tx_params is not None and w3 is not None:
        # Estimate gas cost
        try:
            gas_cost_eth = await estimate_transaction_cost(w3, tx_params)
            provider = await get_web3_provider()
            eth_price_usd = await provider.get_eth_price()
            gas_cost_usd = gas_cost_eth * eth_price_usd
            total_cost += gas_cost_usd
        except Exception as e:
            logger.warning(f"Could not estimate gas cost: {str(e)}")
    
    # Calculate net profit
    net_profit = raw_profit - total_cost
    
    # Calculate profit percentage based on investment
    investment = buy_price * quantity
    profit_percentage = (net_profit / investment) * 100 if investment > 0 else 0
    
    # Determine if profitable
    is_profitable = net_profit > 0
    
    logger.debug(f"Profitability: Raw profit=${raw_profit:.2f}, Costs=${total_cost:.2f}, " 
              f"Net profit=${net_profit:.2f} ({profit_percentage:.2f}%)")
    
    return net_profit, profit_percentage, is_profitable

def estimate_slippage_impact(
    order_size: float,
    market_liquidity: float,
    order_book_depth: Optional[Dict[str, Any]] = None
) -> float:
    """
    Estimate the impact of slippage on a trade
    
    Args:
        order_size: Size of the order
        market_liquidity: Measure of market liquidity
        order_book_depth: Optional order book depth data
        
    Returns:
        Estimated slippage percentage
    """
    # Simple model: slippage increases with order size and decreases with liquidity
    if market_liquidity <= 0:
        return 5.0  # Default high slippage if liquidity measure is invalid
    
    # Base slippage calculation
    base_slippage = (order_size / market_liquidity) * 100
    
    # If we have order book data, refine the estimate
    if order_book_depth:
        try:
            # More sophisticated slippage model using order book depth
            total_asks_volume = sum(ask[1] for ask in order_book_depth.get('asks', []))
            total_bids_volume = sum(bid[1] for bid in order_book_depth.get('bids', []))
            
            # Calculate volume ratio (order size to available liquidity)
            volume_ratio = order_size / min(total_asks_volume, total_bids_volume) if min(total_asks_volume, total_bids_volume) > 0 else 1
            
            # Adjust slippage based on volume ratio
            if volume_ratio < 0.01:  # Small order (<1% of liquidity)
                adjusted_slippage = base_slippage * 0.5
            elif volume_ratio < 0.05:  # Medium order (<5% of liquidity)
                adjusted_slippage = base_slippage * 0.8
            elif volume_ratio < 0.2:  # Large order (<20% of liquidity)
                adjusted_slippage = base_slippage * 1.2
            else:  # Very large order (>20% of liquidity)
                adjusted_slippage = base_slippage * 2.0
            
            # Use adjusted slippage
            base_slippage = adjusted_slippage
            
        except Exception as e:
            logger.warning(f"Error calculating slippage from order book: {str(e)}")
    
    # Cap slippage at reasonable values
    slippage = min(10.0, base_slippage)  # Maximum 10% slippage
    
    return max(0.05, slippage)  # Minimum 0.05% slippage

def calculate_optimal_trade_size(
    spread_percentage: float,
    available_capital: float,
    slippage_model: Optional[Dict[str, Any]] = None,
    risk_tolerance: float = 1.0  # 0.0 to 2.0, with 1.0 being neutral
) -> float:
    """
    Calculate the optimal trade size based on spread and risk factors
    
    Args:
        spread_percentage: Percentage spread between buy and sell prices
        available_capital: Available capital for the trade
        slippage_model: Optional model parameters for slippage estimation
        risk_tolerance: Risk tolerance factor (0.0 to 2.0)
        
    Returns:
        Optimal trade size
    """
    # Base calculation: trade size increases with spread
    if spread_percentage <= 0:
        return 0  # No trade if no spread
    
    # Exponential model that increases allocation with spread
    # At 0.1% spread: ~10% of capital
    # At 0.5% spread: ~40% of capital
    # At 1.0% spread: ~63% of capital
    # At 2.0% spread: ~86% of capital
    import math
    base_allocation = 1 - math.exp(-spread_percentage)
    
    # Apply risk tolerance factor
    adjusted_allocation = base_allocation * risk_tolerance
    
    # If we have a slippage model, adjust for estimated slippage
    if slippage_model:
        # Calculate estimated slippage for different trade sizes
        try:
            # Test sizes from 10% to 100% of capital
            test_sizes = [available_capital * i/10 for i in range(1, 11)]
            
            # Get market liquidity from model
            market_liquidity = slippage_model.get('market_liquidity', available_capital * 20)
            
            # Calculate slippage for each size
            slippages = [estimate_slippage_impact(size, market_liquidity, 
                                             slippage_model.get('order_book_depth'))
                       for size in test_sizes]
            
            # Find optimal size where spread > 2*slippage
            optimal_idx = 0
            for i, (size, slippage) in enumerate(zip(test_sizes, slippages)):
                if spread_percentage > slippage * 2:
                    optimal_idx = i
                else:
                    break
            
            # Set allocation based on optimal index
            if optimal_idx > 0:
                optimal_allocation = (optimal_idx + 1) / 10
                adjusted_allocation = min(adjusted_allocation, optimal_allocation)
                
        except Exception as e:
            logger.warning(f"Error optimizing trade size with slippage model: {str(e)}")
    
    # Cap at reasonable values
    final_allocation = min(0.95, adjusted_allocation)  # Maximum 95% of capital
    
    # Ensure minimum viable trade size (at least 5% of capital if any trade)
    if final_allocation > 0:
        final_allocation = max(0.05, final_allocation)
    
    # Calculate trade size
    trade_size = available_capital * final_allocation
    
    return trade_size

def is_arbitrage_opportunity(
    buy_price: float,
    sell_price: float,
    min_spread_percentage: float = 0.1,
    fees_percentage: float = 0.2
) -> Tuple[bool, float]:
    """
    Determine if a price difference is an arbitrage opportunity
    
    Args:
        buy_price: Price to buy the asset
        sell_price: Price to sell the asset
        min_spread_percentage: Minimum spread percentage to be considered an opportunity
        fees_percentage: Total fees as a percentage
        
    Returns:
        Tuple of (is_opportunity, spread_percentage)
    """
    if buy_price <= 0 or sell_price <= 0:
        return False, 0
    
    # Calculate spread percentage
    spread_percentage = ((sell_price - buy_price) / buy_price) * 100
    
    # Check if spread exceeds minimum threshold plus fees
    is_opportunity = spread_percentage > (min_spread_percentage + fees_percentage)
    
    return is_opportunity, spread_percentage