"""
Decentralized Exchange (DEX) Arbitrage Strategy
Identifies and executes arbitrage opportunities between decentralized exchanges
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

class DEXArbitrageStrategy:
    """Strategy for identifying and executing arbitrage between decentralized exchanges"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("DEXArbitrage")
        
        # Initialize web3 connection
        self.init_web3()
        
        # Initialize adaptive parameters
        self.adaptive_params = AdaptiveParameters()
        
        # Contract loader
        self.contract_loader = ContractLoader()
        
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
        self.logger.info("Initializing DEX Arbitrage Strategy")
        
        if not self.w3 or not self.w3.is_connected():
            self.logger.error("Web3 not connected, DEX arbitrage unavailable")
            return
        
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
        
        self.logger.info("DEX Arbitrage Strategy initialized")
    
    async def shutdown(self):
        """Clean up resources"""
        self.logger.info("Shutting down DEX Arbitrage Strategy")
        # No specific cleanup needed for Web3 connections
    
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
            
            # Check at least one router contract
            if not self.routers:
                self.logger.warning("No router contracts loaded")
                return False
            
            # Simple contract call test
            for dex_name, router in self.routers.items():
                if "UNISWAP" in dex_name:
                    # Try a simple call like getting the factory address
                    factory = router.functions.factory().call()
                    self.logger.debug(f"{dex_name} factory address: {factory}")
                    break
            
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
        Scan for arbitrage opportunities across decentralized exchanges
        Returns a list of ArbitrageOpportunity objects
        """
        if not self.w3 or not self.w3.is_connected():
            self.logger.warning("Web3 not connected, skipping DEX arbitrage scan")
            return []
        
        opportunities = []
        
        # Define token pairs to check
        token_pairs = [
            ("WETH", "USDT"),
            ("WBTC", "USDT"),
            ("WETH", "USDC"),
            ("WBTC", "USDC"),
            ("WETH", "DAI"),
        ]
        
        # Define DEXes to check
        dexes = []
        if "UNISWAP_ROUTER" in self.routers:
            dexes.append({
                "name": "Uniswap",
                "router": self.routers["UNISWAP_ROUTER"]
            })
        
        if "SUSHISWAP_ROUTER" in self.routers:
            dexes.append({
                "name": "SushiSwap",
                "router": self.routers["SUSHISWAP_ROUTER"]
            })
        
        # Get current minimum profit threshold
        min_profit_threshold = self.adaptive_params.get_min_profit_threshold()
        
        # Scan for arbitrage opportunities between DEXes
        for token_pair in token_pairs:
            token_in, token_out = token_pair
            
            if token_in not in self.tokens or token_out not in self.tokens:
                continue
                
            token_in_address = self.tokens[token_in]['address']
            token_out_address = self.tokens[token_out]['address']
            
            # Check arbitrage opportunities between DEX pairs
            for i, dex_1 in enumerate(dexes):
                for dex_2 in dexes[i+1:]:
                    try:
                        # Get price on DEX 1 (token_in to token_out)
                        router_1 = dex_1["router"]
                        
                        # Get price on DEX 2 (token_in to token_out)
                        router_2 = dex_2["router"]
                        
                        # Simulate price for 1 token_in (e.g., 1 ETH)
                        amount_in = 10**18  # 1 token with 18 decimals
                        
                        # Get amounts out on both DEXes
                        amount_out_1 = router_1.functions.getAmountsOut(
                            amount_in,
                            [token_in_address, token_out_address]
                        ).call()[-1]
                        
                        amount_out_2 = router_2.functions.getAmountsOut(
                            amount_in,
                            [token_in_address, token_out_address]
                        ).call()[-1]
                        
                        # Calculate prices (normalize based on token decimals)
                        token_out_decimals = self.tokens[token_out]['contract'].functions.decimals().call()
                        price_1 = amount_out_1 / (10**token_out_decimals)
                        price_2 = amount_out_2 / (10**token_out_decimals)
                        
                        # Check if arbitrage opportunity exists
                        if price_1 > price_2 * (1 + min_profit_threshold/100):
                            # Buy on DEX 2, sell on DEX 1
                            spread = (price_1 - price_2) / price_2 * 100
                            
                            # Calculate optimal trade size
                            balance = await self.get_token_balance(token_in)
                            max_trade_size = min(balance * self.config.TRADE_SIZE_PERCENTAGE, 
                                              self.config.MAX_TRADE_SIZE)
                            
                            trade_size = self.adaptive_params.calculate_position_size(
                                spread, max_trade_size, dex_2["name"], dex_1["name"]
                            )
                            
                            if trade_size > 0:
                                profit_expected = trade_size * (price_1 - price_2)
                                
                                opportunities.append(
                                    ArbitrageOpportunity(
                                        strategy="DEX Arbitrage",
                                        exchange_1=dex_2["name"],
                                        exchange_2=dex_1["name"],
                                        pair=f"{token_in}/{token_out}",
                                        price_1=price_2,
                                        price_2=price_1,
                                        spread_percentage=spread,
                                        trade_size=trade_size,
                                        profit_expected=profit_expected
                                    )
                                )
                        
                        elif price_2 > price_1 * (1 + min_profit_threshold/100):
                            # Buy on DEX 1, sell on DEX 2
                            spread = (price_2 - price_1) / price_1 * 100
                            
                            # Calculate optimal trade size
                            balance = await self.get_token_balance(token_in)
                            max_trade_size = min(balance * self.config.TRADE_SIZE_PERCENTAGE, 
                                              self.config.MAX_TRADE_SIZE)
                            
                            trade_size = self.adaptive_params.calculate_position_size(
                                spread, max_trade_size, dex_1["name"], dex_2["name"]
                            )
                            
                            if trade_size > 0:
                                profit_expected = trade_size * (price_2 - price_1)
                                
                                opportunities.append(
                                    ArbitrageOpportunity(
                                        strategy="DEX Arbitrage",
                                        exchange_1=dex_1["name"],
                                        exchange_2=dex_2["name"],
                                        pair=f"{token_in}/{token_out}",
                                        price_1=price_1,
                                        price_2=price_2,
                                        spread_percentage=spread,
                                        trade_size=trade_size,
                                        profit_expected=profit_expected
                                    )
                                )
                    
                    except Exception as e:
                        self.logger.error(f"Error checking DEX arbitrage between {dex_1['name']} and {dex_2['name']}: {str(e)}")
        
        # Sort opportunities by spread percentage
        opportunities.sort(key=lambda x: x.spread_percentage, reverse=True)
        
        # Log found opportunities
        if opportunities:
            self.logger.info(f"Found {len(opportunities)} DEX arbitrage opportunities")
            for i, opp in enumerate(opportunities[:3]):  # Log top 3
                self.logger.info(f"  #{i+1}: {opp.exchange_1}->{opp.exchange_2} {opp.pair} " 
                              f"Spread: {opp.spread_percentage:.2f}% Profit: ${opp.profit_expected:.2f}")
                
        return opportunities
    
    async def verify_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Verify if an opportunity is still valid before execution"""
        try:
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
            
            # Parse token pair
            token_in, token_out = opportunity.pair.split('/')
            token_in_address = self.tokens[token_in]['address']
            token_out_address = self.tokens[token_out]['address']
            
            # Simulate price for 1 token_in
            amount_in = 10**18  # 1 token with 18 decimals
            
            # Get amounts out on both DEXes
            amount_out_1 = router_1.functions.getAmountsOut(
                amount_in,
                [token_in_address, token_out_address]
            ).call()[-1]
            
            amount_out_2 = router_2.functions.getAmountsOut(
                amount_in,
                [token_in_address, token_out_address]
            ).call()[-1]
            
            # Calculate prices
            token_out_decimals = self.tokens[token_out]['contract'].functions.decimals().call()
            price_1 = amount_out_1 / (10**token_out_decimals)
            price_2 = amount_out_2 / (10**token_out_decimals)
            
            # Recalculate spread
            if opportunity.exchange_1 == "Uniswap" and opportunity.exchange_2 == "SushiSwap":
                current_spread = (price_2 - price_1) / price_1 * 100
            else:
                current_spread = (price_1 - price_2) / price_2 * 100
            
            # Check if spread still exceeds threshold
            min_threshold = self.adaptive_params.get_min_profit_threshold()
            is_valid = current_spread > min_threshold
            
            if not is_valid:
                self.logger.info(f"Opportunity no longer valid. Current spread: {current_spread:.2f}%, " 
                              f"Threshold: {min_threshold:.2f}%")
            
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Error verifying opportunity: {str(e)}")
            return False
    
    @measure_execution_time
    async def execute(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute a DEX arbitrage trade"""
        if not self.w3 or not self.wallet_address or not self.private_key:
            self.logger.error("Cannot execute DEX trade: missing Web3 connection or wallet credentials")
            return False
        
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
            
            # Parse token pair
            token_in, token_out = opportunity.pair.split('/')
            token_in_address = self.tokens[token_in]['address']
            token_out_address = self.tokens[token_out]['address']
            
            # Get router contracts
            router_buy = None
            router_sell = None
            
            for dex_name, router in self.routers.items():
                if opportunity.exchange_1 in dex_name:
                    router_buy = router
                if opportunity.exchange_2 in dex_name:
                    router_sell = router
            
            if not router_buy or not router_sell:
                raise Exception(f"Could not find router contracts for {opportunity.exchange_1} and {opportunity.exchange_2}")
            
            # Calculate amount to swap (convert from human-readable to token units)
            token_in_decimals = self.tokens[token_in]['contract'].functions.decimals().call()
            amount_in_raw = int(opportunity.trade_size * (10**token_in_decimals))
            
            # Get token contract
            token_contract = self.tokens[token_in]['contract']
            
            # Check allowance and approve if needed for buy exchange
            allowance = token_contract.functions.allowance(
                self.wallet_address,
                self.routers[f"{opportunity.exchange_1.upper()}_ROUTER"]
            ).call()
            
            if allowance < amount_in_raw:
                # Approve token spending
                gas_price = await get_optimal_gas_price(self.w3)
                
                approve_tx = token_contract.functions.approve(
                    self.routers[f"{opportunity.exchange_1.upper()}_ROUTER"],
                    amount_in_raw * 2  # Approve more than needed to reduce future approvals
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 200000,
                    'gasPrice': gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
                })
                
                # Sign and send transaction
                signed_tx = self.w3.eth.account.sign_transaction(approve_tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                self.logger.info(f"Approval transaction sent: {tx_hash.hex()}")
                
                # Wait for transaction confirmation
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status != 1:
                    raise Exception("Approval transaction failed")
            
            # Calculate minimum amount out (with slippage tolerance)
            amounts_out = router_buy.functions.getAmountsOut(
                amount_in_raw,
                [token_in_address, token_out_address]
            ).call()
            
            amount_out_min = int(amounts_out[1] * (1 - self.config.SLIPPAGE_TOLERANCE / 100))
            
            # Step 1: Swap tokens on first DEX
            deadline = int(time.time()) + 300  # 5 minutes
            gas_price = await get_optimal_gas_price(self.w3)
            
            # Build swap transaction
            swap_tx = router_buy.functions.swapExactTokensForTokens(
                amount_in_raw,
                amount_out_min,
                [token_in_address, token_out_address],
                self.wallet_address,
                deadline
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            self.logger.info(f"Swap transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise Exception("Swap transaction failed")
            
            # Parse swap event to get actual amount received
            token_out_contract = self.tokens[token_out]['contract']
            amount_received = token_out_contract.functions.balanceOf(self.wallet_address).call()
            
            # Step 2: Approve token_out for second DEX
            allowance = token_out_contract.functions.allowance(
                self.wallet_address,
                self.routers[f"{opportunity.exchange_2.upper()}_ROUTER"]
            ).call()
            
            if allowance < amount_received:
                # Approve token spending
                gas_price = await get_optimal_gas_price(self.w3)
                
                approve_tx = token_out_contract.functions.approve(
                    self.routers[f"{opportunity.exchange_2.upper()}_ROUTER"],
                    amount_received * 2  # Approve more than needed
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 200000,
                    'gasPrice': gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
                })
                
                # Sign and send transaction
                signed_tx = self.w3.eth.account.sign_transaction(approve_tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                self.logger.info(f"Second approval transaction sent: {tx_hash.hex()}")
                
                # Wait for transaction confirmation
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status != 1:
                    raise Exception("Second approval transaction failed")
            
            # Step 3: Swap back on second DEX
            # Calculate minimum amount out for second swap (with slippage)
            amounts_out = router_sell.functions.getAmountsOut(
                amount_received,
                [token_out_address, token_in_address]
            ).call()
            
            amount_out_min = int(amounts_out[1] * (1 - self.config.SLIPPAGE_TOLERANCE / 100))
            
            # Build second swap transaction
            gas_price = await get_optimal_gas_price(self.w3)
            
            swap_tx = router_sell.functions.swapExactTokensForTokens(
                amount_received,
                amount_out_min,
                [token_out_address, token_in_address],
                self.wallet_address,
                deadline
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            self.logger.info(f"Second swap transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise Exception("Second swap transaction failed")
            
            # Calculate gas costs
            gas_used = receipt.gasUsed
            gas_cost_wei = gas_used * gas_price
            gas_cost_eth = gas_cost_wei / 10**18

            # Convert gas cost to token equivalent for proper profit calculation
            eth_price_usd = await get_eth_price()  # Get from web3_provider
            token_price_usd = final_balance / amount_in_raw  # Approximate token price
            gas_cost_token = (gas_cost_eth * eth_price_usd) / token_price_usd

            # Calculate profit
            final_balance = token_contract.functions.balanceOf(self.wallet_address).call()
            profit_raw = final_balance - amount_in_raw
            profit_realized = (profit_raw / (10**token_in_decimals)) - gas_cost_token
            
            # Update opportunity with results
            opportunity.end_time = time.time()
            opportunity.profit_realized = profit_realized
            opportunity.order_status = "filled"
            
            # Calculate effective slippage
            expected_final = amount_in_raw * (1 + opportunity.spread_percentage/100)
            slippage = abs(final_balance - expected_final) / expected_final * 100
            opportunity.slippage = slippage
            
            # Log trade result
            self.log_trade_result(opportunity)
            
            # Update adaptive parameters
            self.adaptive_params.update_from_execution(opportunity)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error executing DEX arbitrage: {str(e)}")
            
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