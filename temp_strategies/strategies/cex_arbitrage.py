"""
Centralized Exchange (CEX) Arbitrage Strategy
Identifies and executes arbitrage opportunities between centralized exchanges
"""

import time
import asyncio
import ccxt.async_support as ccxt
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from utils.config import load_config
from utils.logger import setup_logger, log_trade
from utils.performance import measure_execution_time
from utils.adaptive_parameters import AdaptiveParameters
from utils.profitability import calculate_profitability
from utils.gas_price import get_optimal_gas_price

@dataclass
class ArbitrageOpportunity:
    """Data class for storing arbitrage opportunities"""
    strategy: str
    exchange_1: str
    exchange_2: str
    pair: str
    price_1: float
    price_2: float
    spread_percentage: float
    trade_size: float
    profit_expected: float
    start_time: float = 0
    end_time: float = 0
    profit_realized: float = 0
    order_status: str = "pending"
    slippage: float = 0

class CEXArbitrageStrategy:
    """Strategy for identifying and executing arbitrage between centralized exchanges"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("CEXArbitrage")
        
        # Initialize adaptive parameters
        self.adaptive_params = AdaptiveParameters()
        
        # Exchange connections
        self.exchanges = {}
        
        # Market data cache
        self.market_data_cache = {}
        self.last_update_time = {}
        
        # Risk management
        self.failed_trades_count = {}
        self.execution_semaphore = asyncio.Semaphore(10)  # Limit concurrent executions
    
    async def initialize(self):
        """Initialize the strategy and connect to exchanges"""
        self.logger.info("Initializing CEX Arbitrage Strategy")
        
        # Initialize exchange connections
        await self.init_exchanges()
        
        # Initialize websocket connections for real-time data
        await self.init_websockets()
        
        self.logger.info("CEX Arbitrage Strategy initialized")
    
    async def shutdown(self):
        """Clean up resources"""
        self.logger.info("Shutting down CEX Arbitrage Strategy")
        
        # Close exchange connections
        for exchange_id, exchange in self.exchanges.items():
            try:
                await exchange.close()
            except Exception as e:
                self.logger.error(f"Error closing {exchange_id} connection: {str(e)}")
    
    async def init_exchanges(self):
        """Initialize exchange connections with API credentials"""
        exchange_ids = ["binance", "bybit", "okx", "kucoin", "huobi"]
        
        for exchange_id in exchange_ids:
            try:
                exchange_class = getattr(ccxt, exchange_id)
                credentials = self.config.EXCHANGE_CREDENTIALS.get(exchange_id, {})
                
                # Set optimal parameters for high-frequency trading
                exchange_options = {
                    'enableRateLimit': True,
                    'rateLimit': 50,  # More aggressive rate limit
                    'timeout': 10000,  # 10 seconds timeout
                    'adjustForTimeDifference': True,
                }
                
                self.exchanges[exchange_id] = exchange_class({**credentials, **exchange_options})
                
                # Initialize failed trades counter
                self.failed_trades_count[exchange_id] = 0
                
                # Load markets
                await self.exchanges[exchange_id].load_markets()
                self.logger.info(f"Initialized {exchange_id} connection")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize {exchange_id}: {str(e)}")
    
    async def init_websockets(self):
        """Initialize websocket connections for real-time market data"""
        # This would be implementation-specific for each exchange's websocket API
        # For simplicity, we'll use REST API polling in this implementation
        self.logger.info("Using REST API polling for market data")
    
    async def check_health(self) -> bool:
        """Check health of exchange connections"""
        healthy_count = 0
        total_count = 0
        
        for exchange_id, exchange in self.exchanges.items():
            try:
                total_count += 1
                # Simple ping test
                await exchange.fetch_ticker(self.config.TRADING_PAIRS[0])
                healthy_count += 1
            except Exception as e:
                self.logger.warning(f"Health check failed for {exchange_id}: {str(e)}")
        
        health_percentage = (healthy_count / total_count * 100) if total_count > 0 else 0
        self.logger.info(f"Exchange health: {health_percentage:.1f}%")
        
        return health_percentage >= 50  # At least 50% of exchanges must be healthy
    
    async def fetch_ticker(self, exchange_id: str, symbol: str) -> Optional[Dict]:
        """Fetch ticker data for a specific trading pair on an exchange"""
        # Check cache first
        cache_key = f"{exchange_id}_{symbol}"
        current_time = time.time()
        
        if (
            cache_key in self.market_data_cache and 
            cache_key in self.last_update_time and
            current_time - self.last_update_time[cache_key] < self.config.MARKET_DATA_TTL
        ):
            return self.market_data_cache[cache_key]
        
        # Cache miss or expired, fetch from exchange API
        try:
            async with self.execution_semaphore:
                exchange = self.exchanges[exchange_id]
                ticker = await exchange.fetch_ticker(symbol)
                
                # Update cache
                self.market_data_cache[cache_key] = ticker
                self.last_update_time[cache_key] = current_time
                
                return ticker
        except Exception as e:
            self.logger.error(f"Error fetching ticker for {symbol} on {exchange_id}: {str(e)}")
            return None
    
    async def get_account_balance(self, exchange_id: str, currency: str) -> float:
        """Get available balance for a specific currency on an exchange"""
        try:
            exchange = self.exchanges[exchange_id]
            balance = await exchange.fetch_balance()
            return float(balance.get(currency, {}).get('free', 0))
        except Exception as e:
            self.logger.error(f"Error fetching {currency} balance on {exchange_id}: {str(e)}")
            return 0
    
    @measure_execution_time
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Scan for arbitrage opportunities across centralized exchanges
        Returns a list of ArbitrageOpportunity objects
        """
        opportunities = []
        exchange_ids = list(self.exchanges.keys())
        
        # Get current minimum profit threshold (may be adjusted adaptively)
        min_profit_threshold = self.adaptive_params.get_min_profit_threshold()
        
        for pair in self.config.TRADING_PAIRS:
            base_currency = pair.split('/')[0]
            
            for i, exchange_1 in enumerate(exchange_ids):
                for exchange_2 in exchange_ids[i+1:]:
                    ticker_1 = await self.fetch_ticker(exchange_1, pair)
                    ticker_2 = await self.fetch_ticker(exchange_2, pair)
                    
                    if not ticker_1 or not ticker_2:
                        continue
                    
                    # Get bid and ask prices
                    buy_price = ticker_1.get('ask')
                    sell_price = ticker_2.get('bid')
                    
                    # Check if sell price is higher than buy price (arbitrage opportunity)
                    if sell_price > buy_price:
                        spread = (sell_price - buy_price) / buy_price * 100
                        
                        # Check if spread exceeds minimum threshold
                        if spread > min_profit_threshold:
                            balance = await self.get_account_balance(exchange_1, base_currency)
                            max_trade_size = min(balance * self.config.TRADE_SIZE_PERCENTAGE, 
                                              self.config.MAX_TRADE_SIZE)
                            
                            # Calculate optimal trade size based on spread
                            trade_size = self.adaptive_params.calculate_position_size(
                                spread, max_trade_size, exchange_1, exchange_2
                            )
                            
                            if trade_size > 0:
                                profit_expected = trade_size * (sell_price - buy_price)
                                
                                opportunities.append(
                                    ArbitrageOpportunity(
                                        strategy="CEX Arbitrage",
                                        exchange_1=exchange_1,
                                        exchange_2=exchange_2,
                                        pair=pair,
                                        price_1=buy_price,
                                        price_2=sell_price,
                                        spread_percentage=spread,
                                        trade_size=trade_size,
                                        profit_expected=profit_expected
                                    )
                                )
                    
                    # Check reverse direction
                    buy_price = ticker_2.get('ask')
                    sell_price = ticker_1.get('bid')
                    
                    if sell_price > buy_price:
                        spread = (sell_price - buy_price) / buy_price * 100
                        
                        if spread > min_profit_threshold:
                            balance = await self.get_account_balance(exchange_2, base_currency)
                            max_trade_size = min(balance * self.config.TRADE_SIZE_PERCENTAGE, 
                                            self.config.MAX_TRADE_SIZE)
                            
                            trade_size = self.adaptive_params.calculate_position_size(
                                spread, max_trade_size, exchange_2, exchange_1
                            )
                            
                            if trade_size > 0:
                                profit_expected = trade_size * (sell_price - buy_price)
                                
                                opportunities.append(
                                    ArbitrageOpportunity(
                                        strategy="CEX Arbitrage",
                                        exchange_1=exchange_2,
                                        exchange_2=exchange_1,
                                        pair=pair,
                                        price_1=buy_price,
                                        price_2=sell_price,
                                        spread_percentage=spread,
                                        trade_size=trade_size,
                                        profit_expected=profit_expected
                                    )
                                )
        
        # Sort opportunities by spread percentage (highest first)
        opportunities.sort(key=lambda x: x.spread_percentage, reverse=True)
        
        # Log found opportunities
        if opportunities:
            self.logger.info(f"Found {len(opportunities)} CEX arbitrage opportunities")
            for i, opp in enumerate(opportunities[:3]):  # Log top 3
                self.logger.info(f"  #{i+1}: {opp.exchange_1}->{opp.exchange_2} {opp.pair} " 
                              f"Spread: {opp.spread_percentage:.2f}% Profit: ${opp.profit_expected:.2f}")
        
        return opportunities
    
    async def verify_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Verify if an opportunity is still valid before execution"""
        # Re-fetch latest prices
        ticker_1 = await self.fetch_ticker(opportunity.exchange_1, opportunity.pair)
        ticker_2 = await self.fetch_ticker(opportunity.exchange_2, opportunity.pair)
        
        if not ticker_1 or not ticker_2:
            return False
        
        current_buy_price = ticker_1.get('ask')
        current_sell_price = ticker_2.get('bid')
        
        # Check if spread still exceeds threshold
        if current_sell_price > current_buy_price:
            current_spread = (current_sell_price - current_buy_price) / current_buy_price * 100
            min_threshold = self.adaptive_params.get_min_profit_threshold()
            return current_spread > min_threshold
        
        return False
    
    async def simulate_transfer(self, from_exchange: str, to_exchange: str, currency: str, amount: float):
        """Simulate transfer between exchanges (in production, implement actual transfer)"""
        # In a real implementation, you would:
        # 1. Initiate withdrawal from from_exchange
        # 2. Wait for confirmation
        # 3. Verify deposit on to_exchange
        await asyncio.sleep(0.1)  # Simulate minimal latency
        self.logger.info(f"Simulated transfer of {amount} {currency} from {from_exchange} to {to_exchange}")
    
    @measure_execution_time
    async def execute(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute a CEX arbitrage trade with advanced risk management and speed optimization"""
        # Check if circuit breaker is active for either exchange
        if (self.failed_trades_count.get(opportunity.exchange_1, 0) >= self.config.CIRCUIT_BREAKER_THRESHOLD or
            self.failed_trades_count.get(opportunity.exchange_2, 0) >= self.config.CIRCUIT_BREAKER_THRESHOLD):
            self.logger.warning(f"Circuit breaker active, skipping trade")
            return False
        
        try:
            opportunity.start_time = time.time()
            
            # Split pair into base and quote currencies
            base_currency, quote_currency = opportunity.pair.split('/')
            
            # Use asyncio.gather for parallel execution when possible
            tasks = []
            
            # Double-check current prices before execution (latency optimization)
            is_still_valid = await asyncio.wait_for(
                self.verify_opportunity(opportunity), 
                timeout=1.0
            )
            
            if not is_still_valid:
                self.logger.warning(f"Opportunity no longer valid, spread has changed")
                opportunity.order_status = "canceled"
                self.log_trade_result(opportunity)
                return False
            
            # Use execution timeout to prevent hanging trades
            try:
                # Place buy order on first exchange with optimal parameters
                exchange_1 = self.exchanges[opportunity.exchange_1]
                buy_params = {
                    'symbol': opportunity.pair,
                    'type': 'market',
                    'side': 'buy',
                    'amount': opportunity.trade_size,
                    'params': {
                        'timeInForce': 'IOC',  # Immediate-or-Cancel for lower latency
                    }
                }
                
                # Execute buy order with timeout
                buy_order = await asyncio.wait_for(
                    exchange_1.create_order(**buy_params),
                    timeout=self.config.EXECUTION_TIMEOUT
                )
                
                self.logger.info(f"Placed buy order on {opportunity.exchange_1}: {buy_order['id']}")
                
                # Verify order status
                order_status_task = asyncio.create_task(exchange_1.fetch_order(buy_order['id']))
                order_status = await asyncio.wait_for(order_status_task, timeout=self.config.EXECUTION_TIMEOUT)
                
                if order_status['status'] != 'closed':
                    self.logger.warning(f"Buy order not filled completely: {order_status['status']}")
                    # Handle partial fills
                    if order_status['filled'] == 0:
                        raise Exception("Buy order not filled")
                
                # Calculate actual filled amount and price
                actual_buy_price = order_status['price'] if order_status['price'] else opportunity.price_1
                amount_bought = order_status['filled']
                
                # Calculate buy slippage
                buy_slippage = abs(actual_buy_price - opportunity.price_1) / opportunity.price_1 * 100
                
                # Transfer funds if needed (concurrent process)
                transfer_task = None
                if opportunity.exchange_1 != opportunity.exchange_2:
                    self.logger.info(f"Transferring {amount_bought} {base_currency} between exchanges")
                    # In production, implement actual transfer logic
                    transfer_task = asyncio.create_task(self.simulate_transfer(
                        opportunity.exchange_1, 
                        opportunity.exchange_2,
                        base_currency,
                        amount_bought
                    ))
                
                # Wait for transfer if needed
                if transfer_task:
                    await asyncio.wait_for(transfer_task, timeout=self.config.EXECUTION_TIMEOUT)
                
                # Place sell order on second exchange
                exchange_2 = self.exchanges[opportunity.exchange_2]
                sell_params = {
                    'symbol': opportunity.pair,
                    'type': 'market',
                    'side': 'sell',
                    'amount': amount_bought,
                    'params': {
                        'timeInForce': 'IOC',
                    }
                }
                
                # Execute sell order with timeout
                sell_order = await asyncio.wait_for(
                    exchange_2.create_order(**sell_params),
                    timeout=self.config.EXECUTION_TIMEOUT
                )
                
                self.logger.info(f"Placed sell order on {opportunity.exchange_2}: {sell_order['id']}")
                
                # Verify sell order status
                sell_status_task = asyncio.create_task(exchange_2.fetch_order(sell_order['id']))
                sell_status = await asyncio.wait_for(sell_status_task, timeout=self.config.EXECUTION_TIMEOUT)
                
                if sell_status['status'] != 'closed':
                    self.logger.warning(f"Sell order not filled completely: {sell_status['status']}")
                    if sell_status['filled'] == 0:
                        raise Exception("Sell order not filled")
                
                # Calculate actual sell price and amount
                actual_sell_price = sell_status['price'] if sell_status['price'] else opportunity.price_2
                amount_sold = sell_status['filled']
                
                # Calculate sell slippage
                sell_slippage = abs(actual_sell_price - opportunity.price_2) / opportunity.price_2 * 100
                total_slippage = (buy_slippage + sell_slippage) / 2
                
                # Calculate realized profit
                profit_realized = amount_sold * actual_sell_price - amount_bought * actual_buy_price
                
                # Reset failed trades counter on success
                self.failed_trades_count[opportunity.exchange_1] = 0
                self.failed_trades_count[opportunity.exchange_2] = 0
                
                # Update opportunity with results
                opportunity.end_time = time.time()
                opportunity.profit_realized = profit_realized
                opportunity.order_status = "filled"
                opportunity.slippage = total_slippage
                
                # Log trade result
                self.log_trade_result(opportunity)
                
                # Update adaptive parameters based on execution
                self.adaptive_params.update_from_execution(opportunity)
                
                return True
                
            except asyncio.TimeoutError:
                self.logger.error(f"Execution timeout for CEX arbitrage trade")
                opportunity.order_status = "timeout"
                raise Exception("Execution timeout")
        
        except Exception as e:
            self.logger.error(f"Error executing CEX arbitrage: {str(e)}")
            
            # Increment failed trades counter
            self.failed_trades_count[opportunity.exchange_1] = self.failed_trades_count.get(opportunity.exchange_1, 0) + 1
            self.failed_trades_count[opportunity.exchange_2] = self.failed_trades_count.get(opportunity.exchange_2, 0) + 1
            
            opportunity.end_time = time.time()
            opportunity.order_status = "failed"
            opportunity.slippage = 0
            
            # Log trade result
            self.log_trade_result(opportunity)
            
            return False
    
    def log_trade_result(self, opportunity: ArbitrageOpportunity):
        """Log trade result in standardized format"""
        execution_time_ms = int((opportunity.end_time - opportunity.start_time) * 1000)
        
        log_data = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "strategy": opportunity.strategy,
            "exchange_1": opportunity.exchange_1,
            "exchange_2": opportunity.exchange_2,
            "pair": opportunity.pair,
            "price_1": opportunity.price_1,
            "price_2": opportunity.price_2,
            "spread_percentage": opportunity.spread_percentage,
            "trade_size": opportunity.trade_size,
            "profit_expected": opportunity.profit_expected,
            "profit_realized": opportunity.profit_realized,
            "execution_time_ms": execution_time_ms,
            "order_status": opportunity.order_status,
            "slippage": opportunity.slippage
        }
        
        # Use the standard logging format from logger.py
        log_trade(log_data)