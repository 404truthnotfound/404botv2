"""
Triangular Arbitrage Strategy
Identifies and executes triangular arbitrage opportunities within a single exchange
"""

import time
import asyncio
import ccxt.async_support as ccxt
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from utils.config import load_config
from utils.logger import setup_logger, log_trade
from utils.performance import measure_execution_time
from utils.adaptive_parameters import AdaptiveParameters
from utils.profitability import calculate_profitability

@dataclass
class ArbitrageOpportunity:
    """Data class for storing arbitrage opportunities"""
    strategy: str
    exchange_1: str
    exchange_2: str  # Same as exchange_1 for triangular
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

class TriangularArbitrageStrategy:
    """Strategy for identifying and executing triangular arbitrage within a single exchange"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("TriangularArbitrage")
        
        # Initialize adaptive parameters
        self.adaptive_params = AdaptiveParameters()
        
        # Exchange connections
        self.exchanges = {}
        
        # Market data cache
        self.market_data_cache = {}
        self.last_update_time = {}
        
        # Risk management
        self.failed_trades_count = {}
        self.execution_semaphore = asyncio.Semaphore(5)  # Limit concurrent executions
        
        # Dynamically discovered triangular paths
        self.exchange_paths = {}
    
    async def initialize(self):
        """Initialize the strategy and connect to exchanges"""
        self.logger.info("Initializing Triangular Arbitrage Strategy")
        
        # Initialize exchange connections
        await self.init_exchanges()
        
        # Initialize market data
        await self.init_market_data()
        
        self.logger.info("Triangular Arbitrage Strategy initialized")
    
    async def shutdown(self):
        """Clean up resources"""
        self.logger.info("Shutting down Triangular Arbitrage Strategy")
        
        # Close exchange connections
        for exchange_id, exchange in self.exchanges.items():
            try:
                await exchange.close()
            except Exception as e:
                self.logger.error(f"Error closing {exchange_id} connection: {str(e)}")
    
    async def init_exchanges(self):
        """Initialize exchange connections with API credentials"""
        exchange_ids = ["binance", "bybit", "okx"]  # Focus on major exchanges
        
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
    
    async def init_market_data(self):
        """Dynamically discover all triangular arbitrage paths"""
        for exchange_id, exchange in self.exchanges.items():
            symbols = list(exchange.markets.keys())
            currency_pairs = {symbol.split('/')[0]: [] for symbol in symbols}
            
            for symbol in symbols:
                base, quote = symbol.split('/')
                currency_pairs[base].append(quote)
                currency_pairs[quote].append(base)
            
            self.exchange_paths[exchange_id] = [
                [f"{start}/{second}", f"{second}/{third}", f"{third}/{start}"]
                for start in currency_pairs for second in currency_pairs[start]
                for third in currency_pairs[second] if third in currency_pairs and start in currency_pairs[third]
            ]
    
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
        Scan for triangular arbitrage opportunities within exchanges
        Returns a list of ArbitrageOpportunity objects
        """
        opportunities = []
        
        # Get current minimum profit threshold
        min_profit_threshold = self.adaptive_params.get_min_profit_threshold()
        
        for exchange_id, exchange in self.exchanges.items():
            # Define triangular paths to check
            # Each path is a list of trading pairs that form a cycle
            triangular_paths = self.exchange_paths[exchange_id]
            
            for path in triangular_paths:
                try:
                    # Check if all pairs in the path are available on this exchange
                    if not all(symbol in exchange.markets for symbol in path):
                        continue
                    
                    # Get ticker data for all pairs in the path
                    ticker_1 = await self.fetch_ticker(exchange_id, path[0])
                    ticker_2 = await self.fetch_ticker(exchange_id, path[1])
                    ticker_3 = await self.fetch_ticker(exchange_id, path[2])
                    
                    if not all([ticker_1, ticker_2, ticker_3]):
                        continue
                    
                    # Extract prices for the path
                    # For BTC/USDT -> ETH/USDT -> ETH/BTC:
                    # 1. Convert BTC to USDT (sell BTC)
                    # 2. Convert USDT to ETH (buy ETH)
                    # 3. Convert ETH to BTC (sell ETH)
                    
                    # 1. Sell BTC for USDT
                    price_1 = ticker_1.get('bid')  # BTC/USDT bid (sell) price
                    
                    # 2. Buy ETH with USDT
                    price_2 = ticker_2.get('ask')  # ETH/USDT ask (buy) price
                    
                    # 3. Sell ETH for BTC
                    price_3 = ticker_3.get('bid')  # ETH/BTC bid (sell) price
                    
                    # Check for valid prices
                    if not all([price_1, price_2, price_3]):
                        continue
                    
                    # Calculate conversion rates
                    # Path example: BTC -> USDT -> ETH -> BTC
                    btc_to_usdt = price_1                  # 1 BTC -> X USDT
                    usdt_to_eth = 1 / price_2              # 1 USDT -> Y ETH
                    eth_to_btc = price_3                   # 1 ETH -> Z BTC
                    
                    # Calculate final arbitrage rate (how much BTC we get back from 1 BTC)
                    final_btc = btc_to_usdt * usdt_to_eth * eth_to_btc
                    
                    # Calculate profit percentage
                    profit_percentage = (final_btc - 1) * 100
                    
                    if profit_percentage > min_profit_threshold:
                        # Determine trade size
                        base_currency = path[0].split('/')[0]  # BTC
                        balance = await self.get_account_balance(exchange_id, base_currency)
                        max_trade_size = min(balance * self.config.TRADE_SIZE_PERCENTAGE, 
                                          self.config.MAX_TRADE_SIZE)
                        
                        # Calculate optimal trade size based on profitability
                        trade_size = self.adaptive_params.calculate_position_size(
                            profit_percentage, max_trade_size, exchange_id, exchange_id
                        )
                        
                        if trade_size > 0:
                            profit_expected = trade_size * (final_btc - 1)
                            
                            opportunities.append(
                                ArbitrageOpportunity(
                                    strategy="Triangular Arbitrage",
                                    exchange_1=exchange_id,
                                    exchange_2=exchange_id,  # Same exchange
                                    pair=f"{path[0]}->{path[1]}->{path[2]}",
                                    price_1=1.0,  # Starting with 1 unit
                                    price_2=final_btc,  # Final return
                                    spread_percentage=profit_percentage,
                                    trade_size=trade_size,
                                    profit_expected=profit_expected
                                )
                            )
                
                except Exception as e:
                    self.logger.error(f"Error checking triangular arbitrage on {exchange_id}, path {path}: {str(e)}")
        
        # Sort opportunities by profit percentage
        opportunities.sort(key=lambda x: x.spread_percentage, reverse=True)
        
        # Log found opportunities
        if opportunities:
            self.logger.info(f"Found {len(opportunities)} triangular arbitrage opportunities")
            for i, opp in enumerate(opportunities[:3]):  # Log top 3
                self.logger.info(f"  #{i+1}: {opp.exchange_1} {opp.pair} " 
                              f"Profit: {opp.spread_percentage:.2f}% Expected: ${opp.profit_expected:.2f}")
                
        return opportunities
    
    async def verify_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Verify if a triangular opportunity is still valid before execution"""
        try:
            exchange_id = opportunity.exchange_1
            path = opportunity.pair.split("->")
            
            # Get current ticker data
            ticker_1 = await self.fetch_ticker(exchange_id, path[0])
            ticker_2 = await self.fetch_ticker(exchange_id, path[1])
            ticker_3 = await self.fetch_ticker(exchange_id, path[2])
            
            if not all([ticker_1, ticker_2, ticker_3]):
                return False
            
            # Extract current prices
            price_1 = ticker_1.get('bid')  # First pair bid (sell) price
            price_2 = ticker_2.get('ask')  # Second pair ask (buy) price
            price_3 = ticker_3.get('bid')  # Third pair bid (sell) price
            
            if not all([price_1, price_2, price_3]):
                return False
            
            # Calculate current conversion rates
            # Example: BTC -> USDT -> ETH -> BTC
            rate_1 = price_1                  # 1 BTC -> X USDT
            rate_2 = 1 / price_2              # 1 USDT -> Y ETH
            rate_3 = price_3                  # 1 ETH -> Z BTC
            
            # Calculate current arbitrage rate
            current_final = rate_1 * rate_2 * rate_3
            
            # Calculate current profit percentage
            current_profit = (current_final - 1) * 100
            
            # Check if still profitable
            min_threshold = self.adaptive_params.get_min_profit_threshold()
            is_valid = current_profit > min_threshold
            
            if not is_valid:
                self.logger.info(f"Triangular opportunity no longer valid. Current profit: {current_profit:.2f}%, " 
                              f"Threshold: {min_threshold:.2f}%")
            
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Error verifying triangular opportunity: {str(e)}")
            return False
    
    @measure_execution_time
    async def execute(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute a triangular arbitrage trade"""
        try:
            opportunity.start_time = time.time()
            
            # Verify opportunity is still valid
            is_still_valid = await asyncio.wait_for(
                self.verify_opportunity(opportunity), 
                timeout=1.0
            )
            
            if not is_still_valid:
                opportunity.order_status = "canceled"
                self.log_trade_result(opportunity)
                return False
            
            # Parse the triangular path
            path = opportunity.pair.split("->")
            exchange_id = opportunity.exchange_1
            exchange = self.exchanges[exchange_id]
            
            # Extract pairs from path
            pair_1 = path[0]
            pair_2 = path[1]
            pair_3 = path[2]
            
            # Parse trading pairs
            base_1, quote_1 = pair_1.split('/')
            base_2, quote_2 = pair_2.split('/')
            base_3, quote_3 = pair_3.split('/')
            
            # Verify we have the necessary balances
            balance = await self.get_account_balance(exchange_id, base_1)
            if balance < opportunity.trade_size:
                self.logger.warning(f"Insufficient balance: {balance} {base_1}, needed {opportunity.trade_size}")
                opportunity.order_status = "canceled"
                self.log_trade_result(opportunity)
                return False
            
            # Step 1: Execute first trade (e.g., BTC -> USDT)
            self.logger.info(f"Executing triangular arbitrage step 1: {pair_1}")
            order_1 = await exchange.create_market_sell_order(
                pair_1,
                opportunity.trade_size
            )
            
            # Wait for order to complete and verify
            order_1_status = await exchange.fetch_order(order_1['id'])
            if order_1_status['status'] != 'closed':
                raise Exception(f"First order not filled: {order_1_status['status']}")
            
            # Calculate amount received from first trade
            amount_received_1 = order_1_status['cost']  # Total quote currency received
            
            # Step 2: Execute second trade (e.g., USDT -> ETH)
            self.logger.info(f"Executing triangular arbitrage step 2: {pair_2}")
            order_2 = await exchange.create_market_buy_order(
                pair_2,
                amount_received_1,
                {'quoteOrderQty': True}  # Use quote currency amount for order
            )
            
            # Wait for order to complete and verify
            order_2_status = await exchange.fetch_order(order_2['id'])
            if order_2_status['status'] != 'closed':
                raise Exception(f"Second order not filled: {order_2_status['status']}")
            
            # Calculate amount received from second trade
            amount_received_2 = order_2_status['amount']  # Total base currency received
            
            # Step 3: Execute third trade (e.g., ETH -> BTC)
            self.logger.info(f"Executing triangular arbitrage step 3: {pair_3}")
            order_3 = await exchange.create_market_sell_order(
                pair_3,
                amount_received_2
            )
            
            # Wait for order to complete and verify
            order_3_status = await exchange.fetch_order(order_3['id'])
            if order_3_status['status'] != 'closed':
                raise Exception(f"Third order not filled: {order_3_status['status']}")
            
            # Calculate final amount received
            final_amount = order_3_status['amount']  # Total base currency received
            
            # Calculate profit
            profit_realized = final_amount - opportunity.trade_size
            profit_percentage = (profit_realized / opportunity.trade_size) * 100
            
            # Update opportunity with results
            opportunity.end_time = time.time()
            opportunity.profit_realized = profit_realized
            opportunity.order_status = "filled"
            
            # Calculate effective slippage
            expected_final = opportunity.trade_size * (1 + opportunity.spread_percentage/100)
            slippage = abs(final_amount - expected_final) / expected_final * 100
            opportunity.slippage = slippage
            
            # Log result
            self.logger.info(f"Triangular arbitrage executed successfully: {profit_realized} {base_1} profit ({profit_percentage:.2f}%)")
            self.log_trade_result(opportunity)
            
            # Update adaptive parameters
            self.adaptive_params.update_from_execution(opportunity)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error executing triangular arbitrage: {str(e)}")
            
            # Increment failed trades counter
            self.failed_trades_count[opportunity.exchange_1] = self.failed_trades_count.get(opportunity.exchange_1, 0) + 1
            
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