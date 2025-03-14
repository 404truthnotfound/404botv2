"""
Flash Loan Arbitrage Scanner
Identifies and executes flash loan arbitrage opportunities across DeFi platforms
"""

import time
import asyncio
import json
from web3 import Web3
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from utils.config import load_config
from utils.logger import setup_logger, log_trade
from utils.performance import measure_execution_time
from utils.adaptive_parameters import AdaptiveParameters
from utils.contract_loader import ContractLoader
from utils.gas_price import get_optimal_gas_price
from utils.mempool_monitor import MempoolMonitor
from utils.profitability import calculate_profitability

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

class FlashLoanScanner:
    """Strategy for identifying and executing flash loan arbitrage"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("FlashLoanScanner")
        
        # Initialize web3 connection
        self.init_web3()
        
        # Initialize adaptive parameters
        self.adaptive_params = AdaptiveParameters()
        
        # Contract loader
        self.contract_loader = ContractLoader()
        
        # Mempool monitor for front-running protection
        self.mempool_monitor = MempoolMonitor()
        
        # Flash loan contracts
        self.lending_pools = {}
        
        # DEX router contracts
        self.routers = {}
        
        # Token contracts
        self.tokens = {}
    
    def init_web3(self):
        """Initialize Web3 connection"""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.config.WEB3_PROVIDER_URL))
            self.logger.info(f"Connected to Ethereum node: {self.w3.is_connected()}")
            
            # Set up account
            self.wallet_address = self.config.WALLET_ADDRESS
            if not self.wallet_address:
                self.logger.warning("No wallet address configured, using read-only mode")
            
            self.private_key = self.config.PRIVATE_KEY
            if not self.private_key and self.wallet_address:
                self.logger.warning("No private key configured, using read-only mode")
            
        except Exception as e:
            self.logger.error(f"Error initializing web3: {str(e)}")
            self.w3 = None
    
    async def initialize(self):
        """Initialize the strategy and load contracts"""
        self.logger.info("Initializing Flash Loan Scanner")
        
        if not self.w3 or not self.w3.is_connected():
            self.logger.error("Web3 not connected, flash loan scanning unavailable")
            return
        
        # Load lending pool contracts
        self.lending_pools["AAVE"] = self.contract_loader.load_contract(
            self.w3, 
            self.config.CONTRACT_ADDRESSES["AAVE_LENDING_POOL"],
            "AAVE_LENDING_POOL"
        )
        
        # Load router contracts
        for dex_name, router_address in self.config.CONTRACT_ADDRESSES.items():
            if "ROUTER" in dex_name:
                try:
                    router_contract = self.contract_loader.load_router_contract(
                        self.w3, router_address
                    )
                    self.routers[dex_name] = router_contract
                    self.logger.info(f"Loaded {dex_name} router contract")
                except Exception as e:
                    self.logger.error(f"Error loading {dex_name} contract: {str(e)}")
        
        # Load token contracts
        for token_name, token_address in self.config.TOKEN_ADDRESSES.items():
            try:
                token_contract = self.contract_loader.load_token_contract(
                    self.w3, token_address
                )
                self.tokens[token_name] = {
                    'address': token_address,
                    'contract': token_contract
                }
                self.logger.info(f"Loaded {token_name} token contract")
            except Exception as e:
                self.logger.error(f"Error loading {token_name} token contract: {str(e)}")
        
        # Initialize mempool monitor
        await self.mempool_monitor.initialize(self.w3)
        
        self.logger.info("Flash Loan Scanner initialized")
    
    async def shutdown(self):
        """Clean up resources"""
        self.logger.info("Shutting down Flash Loan Scanner")
        
        # Shutdown mempool monitor
        await self.mempool_monitor.shutdown()
    
    async def check_health(self) -> bool:
        """Check health of blockchain connection and contracts"""
        if not self.w3:
            return False
        
        try:
            # Check if connected to Ethereum node
            if not self.w3.is_connected():
                self.logger.warning("Web3 not connected")
                return False
            
            # Check block number to verify sync
            block_number = self.w3.eth.block_number
            self.logger.info(f"Current block number: {block_number}")
            
            # Check lending pool contract
            if not self.lending_pools:
                self.logger.warning("No lending pool contracts loaded")
                return False
            
            # Simple contract call test
            if "AAVE" in self.lending_pools:
                # Try a simple call
                provider = self.lending_pools["AAVE"].functions.getAddressesProvider().call()
                self.logger.debug(f"AAVE provider address: {provider}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            return False
    
    async def get_token_balance(self, token_name: str) -> float:
        """Get token balance for the configured wallet"""
        if not self.wallet_address or token_name not in self.tokens:
            return 0
        
        try:
            token_data = self.tokens[token_name]
            token_contract = token_data['contract']
            
            # Get raw balance
            raw_balance = token_contract.functions.balanceOf(self.wallet_address).call()
            
            # Get decimals
            decimals = token_contract.functions.decimals().call()
            
            # Convert to human-readable format
            balance = raw_balance / (10 ** decimals)
            return balance
            
        except Exception as e:
            self.logger.error(f"Error getting {token_name} balance: {str(e)}")
            return 0
    
    @measure_execution_time
    async def scan_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Scan for flash loan arbitrage opportunities across DeFi platforms
        Returns a list of ArbitrageOpportunity objects
        """
        if not self.w3 or not self.w3.is_connected():
            self.logger.warning("Web3 not connected, skipping flash loan scan")
            return []
        
        opportunities = []
        
        # Define tokens to check for flash loan arbitrage
        flash_loan_tokens = ["WETH", "WBTC", "USDT", "USDC", "DAI"]
        
        # Define DEX pairs for arbitrage
        dex_pairs = {
            "Uniswap": self.routers.get("UNISWAP_ROUTER"),
            "SushiSwap": self.routers.get("SUSHISWAP_ROUTER"),
            "Curve": self.routers.get("CURVE_ROUTER")
        }
        
        # Check for price differences across DEXes that could be exploited with flash loans
        for token_name in flash_loan_tokens:
            if token_name not in self.tokens:
                continue
                
            token_address = self.tokens[token_name]['address']
            
            # Scan for arbitrage between DEX pairs
            for dex_1_name, router_1 in dex_pairs.items():
                for dex_2_name, router_2 in dex_pairs.items():
                    if dex_1_name == dex_2_name or not router_1 or not router_2:
                        continue
                    
                    # For each token, check prices across different trading pairs
                    # We'll focus on stablecoin pairs for this example
                    stable_tokens = ["USDT", "USDC", "DAI"]
                    
                    for stable in stable_tokens:
                        if stable == token_name or stable not in self.tokens:
                            continue
                            
                        stable_address = self.tokens[stable]['address']
                        
                        try:
                            # Get price on DEX 1 
                            amount_in = 10**18  # 1 token with 18 decimals
                            
                            # Skip if either router doesn't have the required function
                            if not hasattr(router_1.functions, 'getAmountsOut') or not hasattr(router_2.functions, 'getAmountsOut'):
                                continue
                            
                            # Get amounts out on both DEXes
                            amount_out_1 = router_1.functions.getAmountsOut(
                                amount_in,
                                [token_address, stable_address]
                            ).call()[-1]
                            
                            amount_out_2 = router_2.functions.getAmountsOut(
                                amount_in,
                                [token_address, stable_address]
                            ).call()[-1]
                            
                            # Get reverse prices
                            amount_in_stable = 10**(self.tokens[stable]['contract'].functions.decimals().call())
                            
                            amount_out_1_reverse = router_1.functions.getAmountsOut(
                                amount_in_stable,
                                [stable_address, token_address]
                            ).call()[-1]
                            
                            amount_out_2_reverse = router_2.functions.getAmountsOut(
                                amount_in_stable,
                                [stable_address, token_address]
                            ).call()[-1]
                            
                            # Calculate prices (normalize based on token decimals)
                            stable_decimals = self.tokens[stable]['contract'].functions.decimals().call()
                            token_decimals = self.tokens[token_name]['contract'].functions.decimals().call()
                            
                            # Forward prices: token -> stable
                            price_1 = amount_out_1 / (10**stable_decimals)
                            price_2 = amount_out_2 / (10**stable_decimals)
                            
                            # Reverse prices: stable -> token
                            price_1_reverse = amount_out_1_reverse / (10**token_decimals)
                            price_2_reverse = amount_out_2_reverse / (10**token_decimals)
                            
                            # Calculate potential arbitrage opportunities
                            
                            # Scenario 1: Borrow token, sell on DEX 1, buy back on DEX 2
                            if price_1 > price_2:
                                # Calculate how much we get after selling on DEX 1
                                stable_amount = price_1
                                
                                # Calculate how much token we can buy back with that stable amount
                                token_amount_back = stable_amount * price_2_reverse
                                
                                # Calculate profit percentage (accounting for flash loan fee)
                                profit_percentage = (token_amount_back - 1 - self.config.FLASH_LOAN_FEE/100) * 100
                                
                                # Check if profitable after fees
                                min_threshold = self.adaptive_params.get_min_profit_threshold()
                                if profit_percentage > min_threshold:
                                    # Determine trade size (consider gas costs, etc.)
                                    max_flash_loan = 100  # Example: 100 ETH max flash loan
                                    
                                    trade_size = self.adaptive_params.calculate_flash_loan_size(
                                        profit_percentage, max_flash_loan, token_name
                                    )
                                    
                                    if trade_size > 0:
                                        profit_expected = trade_size * (profit_percentage / 100)
                                        
                                        opportunities.append(
                                            ArbitrageOpportunity(
                                                strategy="Flash Loan",
                                                exchange_1=dex_1_name,
                                                exchange_2=dex_2_name,
                                                pair=f"{token_name}/{stable} (FL)",
                                                price_1=price_1,
                                                price_2=price_2,
                                                spread_percentage=profit_percentage,
                                                trade_size=trade_size,
                                                profit_expected=profit_expected
                                            )
                                        )
                            
                            # Scenario 2: Borrow token, sell on DEX 2, buy back on DEX 1
                            elif price_2 > price_1:
                                # Calculate how much we get after selling on DEX 2
                                stable_amount = price_2
                                
                                # Calculate how much token we can buy back with that stable amount
                                token_amount_back = stable_amount * price_1_reverse
                                
                                # Calculate profit percentage (accounting for flash loan fee)
                                profit_percentage = (token_amount_back - 1 - self.config.FLASH_LOAN_FEE/100) * 100
                                
                                # Check if profitable after fees
                                min_threshold = self.adaptive_params.get_min_profit_threshold()
                                if profit_percentage > min_threshold:
                                    # Determine trade size (consider gas costs, etc.)
                                    max_flash_loan = 100  # Example: 100 ETH max flash loan
                                    
                                    trade_size = self.adaptive_params.calculate_flash_loan_size(
                                        profit_percentage, max_flash_loan, token_name
                                    )
                                    
                                    if trade_size > 0:
                                        profit_expected = trade_size * (profit_percentage / 100)
                                        
                                        opportunities.append(
                                            ArbitrageOpportunity(
                                                strategy="Flash Loan",
                                                exchange_1=dex_2_name,
                                                exchange_2=dex_1_name,
                                                pair=f"{token_name}/{stable} (FL)",
                                                price_1=price_2,
                                                price_2=price_1,
                                                spread_percentage=profit_percentage,
                                                trade_size=trade_size,
                                                profit_expected=profit_expected
                                            )
                                        )
                        
                        except Exception as e:
                            self.logger.error(f"Error checking flash loan arbitrage for {token_name}/{stable}: {str(e)}")
        
        # Sort opportunities by profit percentage
        opportunities.sort(key=lambda x: x.spread_percentage, reverse=True)
        
        # Log found opportunities
        if opportunities:
            self.logger.info(f"Found {len(opportunities)} flash loan arbitrage opportunities")
            for i, opp in enumerate(opportunities[:3]):  # Log top 3
                self.logger.info(f"  #{i+1}: {opp.exchange_1}->{opp.exchange_2} {opp.pair} " 
                              f"Profit: {opp.spread_percentage:.2f}% Expected: ${opp.profit_expected:.2f}")
                
        return opportunities
    
    async def verify_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Verify if a flash loan opportunity is still valid before execution"""
        try:
            # Parse token pair
            token_info = opportunity.pair.split('/')[0].split(' ')[0]  # Extract token name
            stable = opportunity.pair.split('/')[1].split(' ')[0]  # Extract stable name
            
            if token_info not in self.tokens or stable not in self.tokens:
                return False
                
            token_address = self.tokens[token_info]['address']
            stable_address = self.tokens[stable]['address']
            
            # Get router contracts
            router_1 = None
            router_2 = None
            
            for dex_name, router in self.routers.items():
                if opportunity.exchange_1 in dex_name:
                    router_1 = router
                if opportunity.exchange_2 in dex_name:
                    router_2 = router
            
            if not router_1 or not router_2:
                return False
            
            # Check current prices
            amount_in = 10**18  # 1 token with 18 decimals
            
            # Get amounts out on both DEXes
            amount_out_1 = router_1.functions.getAmountsOut(
                amount_in,
                [token_address, stable_address]
            ).call()[-1]
            
            amount_out_2 = router_2.functions.getAmountsOut(
                amount_in,
                [token_address, stable_address]
            ).call()[-1]
            
            # Get reverse prices
            amount_in_stable = 10**(self.tokens[stable]['contract'].functions.decimals().call())
            
            amount_out_1_reverse = router_1.functions.getAmountsOut(
                amount_in_stable,
                [stable_address, token_address]
            ).call()[-1]
            
            amount_out_2_reverse = router_2.functions.getAmountsOut(
                amount_in_stable,
                [stable_address, token_address]
            ).call()[-1]
            
            # Calculate current prices
            stable_decimals = self.tokens[stable]['contract'].functions.decimals().call()
            token_decimals = self.tokens[token_info]['contract'].functions.decimals().call()
            
            # Forward prices: token -> stable
            current_price_1 = amount_out_1 / (10**stable_decimals)
            current_price_2 = amount_out_2 / (10**stable_decimals)
            
            # Reverse prices: stable -> token
            current_price_1_reverse = amount_out_1_reverse / (10**token_decimals)
            current_price_2_reverse = amount_out_2_reverse / (10**token_decimals)
            
            # Recalculate profit based on current prices
            if opportunity.exchange_1 == opportunity.exchange_2.split("_")[0]:
                # Scenario 1: sell on DEX 1, buy on DEX 2
                stable_amount = current_price_1
                token_amount_back = stable_amount * current_price_2_reverse
            else:
                # Scenario 2: sell on DEX 2, buy on DEX 1
                stable_amount = current_price_2
                token_amount_back = stable_amount * current_price_1_reverse
            
            # Calculate current profit percentage
            current_profit = (token_amount_back - 1 - self.config.FLASH_LOAN_FEE/100) * 100
            
            # Check if still profitable after fees
            min_threshold = self.adaptive_params.get_min_profit_threshold()
            is_valid = current_profit > min_threshold
            
            # Check front-running risk
            front_running_risk = await self.mempool_monitor.check_front_running_risk(
                token_address, stable_address
            )
            
            if front_running_risk > 0.5:  # High risk of front-running
                self.logger.warning(f"High front-running risk detected: {front_running_risk:.2f}")
                return False
            
            if not is_valid:
                self.logger.info(f"Flash loan opportunity no longer valid. Current profit: {current_profit:.2f}%, " 
                              f"Threshold: {min_threshold:.2f}%")
            
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Error verifying flash loan opportunity: {str(e)}")
            return False
    
    @measure_execution_time
    async def execute(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute a flash loan arbitrage trade"""
        if not self.w3 or not self.wallet_address or not self.private_key:
            self.logger.error("Cannot execute flash loan: missing Web3 connection or wallet credentials")
            return False
        
        try:
            opportunity.start_time = time.time()
            
            # Verify opportunity is still valid
            is_still_valid = await self.verify_opportunity(opportunity)
            if not is_still_valid:
                opportunity.order_status = "canceled"
                self.log_trade_result(opportunity)
                return False
            
            # Parse token pair
            token_info = opportunity.pair.split('/')[0].split(' ')[0]  # Extract token name
            token_address = self.tokens[token_info]['address']
            
            # Calculate amount to borrow (convert from human-readable to token units)
            token_decimals = self.tokens[token_info]['contract'].functions.decimals().call()
            amount_in_raw = int(opportunity.trade_size * (10**token_decimals))
            
            # Get optimal gas price
            gas_price = await get_optimal_gas_price(self.w3)
            
            # Get contract addresses for routers
            source_router_address = self.config.CONTRACT_ADDRESSES[f"{opportunity.exchange_1.upper()}_ROUTER"]
            target_router_address = self.config.CONTRACT_ADDRESSES[f"{opportunity.exchange_2.upper()}_ROUTER"]
            
            # Get intermediate token from the opportunity
            stable_coin = opportunity.pair.split('/')[1].split(' ')[0]
            intermediate_token_address = self.tokens[stable_coin]['address']
            
            # Create path
            path = [token_address, intermediate_token_address, token_address]
            
            # Get flash loan contract
            flash_loan_contract_address = self.config.CONTRACT_ADDRESSES.get("FLASH_LOAN_CONTRACT")
            if not flash_loan_contract_address:
                self.logger.error("Flash loan contract address not configured")
                return False
            
            flash_loan_contract = self.contract_loader.load_contract(
                self.w3,
                flash_loan_contract_address,
                "FlashLoanArbitrage"
            )
            
            if not flash_loan_contract:
                self.logger.error("Could not load flash loan contract")
                return False
            
            # Check front-running risk
            front_running_risk = await self.mempool_monitor.check_front_running_risk(
                token_address, intermediate_token_address
            )
            
            if front_running_risk > 0.5:  # High risk of front-running
                self.logger.warning(f"Skipping execution due to high front-running risk: {front_running_risk:.2f}")
                opportunity.order_status = "canceled"
                self.log_trade_result(opportunity)
                return False
            
            # Build transaction to call executeFlashLoanWithPath
            tx = flash_loan_contract.functions.executeFlashLoanWithPath(
                token_address,
                amount_in_raw,
                source_router_address,
                target_router_address,
                path
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 1500000,  # Higher gas limit for flash loans
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            self.logger.info(f"Flash loan transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)  # Longer timeout for complex txs
            
            if receipt.status != 1:
                raise Exception("Flash loan transaction failed")
            
            # Parse ProfitGenerated event to get actual profit
            profit_events = flash_loan_contract.events.ProfitGenerated().process_receipt(receipt)
            if profit_events:
                profit_event = profit_events[0]
                profit_realized = profit_event.args.profit / (10**token_decimals)
            else:
                # Fallback if event not found
                profit_realized = opportunity.profit_expected * 0.95  # Estimate
            
            # Calculate gas cost
            gas_used = receipt.gasUsed
            gas_cost_wei = gas_used * gas_price
            gas_cost_eth = gas_cost_wei / 10**18
            
            # Get current ETH price
            provider = await get_web3_provider()
            eth_price_usd = await provider.get_eth_price()
            gas_cost_usd = gas_cost_eth * eth_price_usd
            
            # Adjust profit by gas cost
            net_profit = profit_realized - gas_cost_usd
            
            # Update opportunity with results
            opportunity.end_time = time.time()
            opportunity.profit_realized = net_profit
            opportunity.order_status = "filled"
            opportunity.slippage = (opportunity.profit_expected - profit_realized) / opportunity.profit_expected * 100
            
            # Log trade result
            self.log_trade_result(opportunity)
            
            # Update adaptive parameters
            self.adaptive_params.update_from_execution(opportunity)
            
            return True
        except Exception as e:
            self.logger.error(f"Error executing flash loan: {str(e)}")
            
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