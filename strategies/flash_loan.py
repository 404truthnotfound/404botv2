#!/usr/bin/env python3
"""
404Bot v2 - Flash Loan Arbitrage Strategy
Implements flash loan arbitrage between different DEXes
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
import json

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError, TransactionNotFound

from core.event_bus import EventBus
from utils.gas import GasOptimizer
from utils.prediction import LiquidityPredictor

# ABI for the flash loan contract
with open("contracts/abi/FlashLoan.json", "r") as f:
    FLASH_LOAN_ABI = json.load(f)

# Common token addresses (Ethereum mainnet)
TOKENS = {
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
}

# DEX router addresses (Ethereum mainnet)
DEX_ROUTERS = {
    "uniswap": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "sushiswap": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"
}

class FlashLoanStrategy:
    """
    Flash loan arbitrage strategy implementation
    Executes flash loans to profit from price differences between DEXes
    """
    
    def __init__(
        self,
        web3_provider: str,
        private_key: str,
        contract_address: str,
        event_bus: EventBus,
        gas_optimizer: GasOptimizer,
        liquidity_predictor: LiquidityPredictor
    ):
        """
        Initialize the flash loan strategy
        
        Args:
            web3_provider: Web3 provider URL
            private_key: Private key for transaction signing
            contract_address: Flash loan contract address
            event_bus: Event bus for communication
            gas_optimizer: Gas optimization utility
            liquidity_predictor: Liquidity prediction utility
        """
        self.logger = logging.getLogger("FlashLoanStrategy")
        self.web3_provider = web3_provider
        self.private_key = private_key
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.event_bus = event_bus
        self.gas_optimizer = gas_optimizer
        self.liquidity_predictor = liquidity_predictor
        
        # Initialize Web3
        self.web3 = Web3(Web3.HTTPProvider(web3_provider))
        self.account = self.web3.eth.account.from_key(private_key)
        self.address = self.account.address
        
        # Initialize contract
        self.contract = self.web3.eth.contract(
            address=self.contract_address,
            abi=FLASH_LOAN_ABI
        )
        
        # Strategy state
        self.running = False
        self.tasks = []
        
        # Performance metrics
        self.executions = 0
        self.successful_executions = 0
        self.total_profit = Decimal('0')
        self.start_time = None
        
        # Minimum profit threshold in base token units
        self.min_profit_threshold = {
            TOKENS["WETH"]: Decimal('0.005'),  # 0.005 ETH
            TOKENS["USDC"]: Decimal('10'),     # 10 USDC
            TOKENS["USDT"]: Decimal('10'),     # 10 USDT
            TOKENS["DAI"]: Decimal('10'),      # 10 DAI
            TOKENS["WBTC"]: Decimal('0.0003')  # 0.0003 BTC
        }
        
        # Default flash loan amounts
        self.default_loan_amounts = {
            TOKENS["WETH"]: Decimal('10'),     # 10 ETH
            TOKENS["USDC"]: Decimal('20000'),  # 20,000 USDC
            TOKENS["USDT"]: Decimal('20000'),  # 20,000 USDT
            TOKENS["DAI"]: Decimal('20000'),   # 20,000 DAI
            TOKENS["WBTC"]: Decimal('0.5')     # 0.5 BTC
        }
        
        self.logger.info("Flash Loan Strategy initialized")
    
    async def start(self):
        """Start the flash loan strategy"""
        if self.running:
            return
        
        self.logger.info("Starting Flash Loan Strategy...")
        self.running = True
        self.start_time = time.time()
        
        # Register event handlers
        self.event_bus.subscribe("opportunity_found", self._on_opportunity_found)
        
        # Start monitoring tasks
        self.tasks.append(asyncio.create_task(self._monitor_opportunities()))
        
        self.logger.info("Flash Loan Strategy started")
    
    async def stop(self):
        """Stop the flash loan strategy"""
        if not self.running:
            return
        
        self.logger.info("Stopping Flash Loan Strategy...")
        self.running = False
        
        # Unregister event handlers
        self.event_bus.unsubscribe("opportunity_found", self._on_opportunity_found)
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.logger.info("Flash Loan Strategy stopped")
    
    async def _monitor_opportunities(self):
        """Monitor for arbitrage opportunities"""
        while self.running:
            try:
                # Periodically scan for opportunities
                await self._scan_for_opportunities()
                
                # Wait before next scan
                await asyncio.sleep(5)  # 5 seconds between scans
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in opportunity monitoring: {str(e)}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _scan_for_opportunities(self):
        """Scan for arbitrage opportunities between DEXes"""
        for token_symbol, token_address in TOKENS.items():
            # Skip tokens with low liquidity based on prediction
            liquidity_score = await self.liquidity_predictor.predict_liquidity(token_address)
            if liquidity_score < 0.7:  # Skip if liquidity score is below 70%
                continue
            
            # Get loan amount for this token
            loan_amount = self.default_loan_amounts.get(token_address)
            if not loan_amount:
                continue
            
            # Convert to token units
            token_contract = self.web3.eth.contract(
                address=token_address,
                abi=[{
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "payable": False,
                    "stateMutability": "view",
                    "type": "function"
                }]
            )
            
            try:
                decimals = token_contract.functions.decimals().call()
                loan_amount_wei = int(loan_amount * (10 ** decimals))
                
                # Find the best arbitrage route
                best_route = await self._find_best_arbitrage_route(token_address, loan_amount_wei)
                
                if best_route:
                    source_router, target_router, intermediate_token, profit = best_route
                    
                    # Convert profit to human-readable format
                    profit_decimal = Decimal(profit) / (10 ** decimals)
                    
                    # Check if profit exceeds threshold
                    min_profit = self.min_profit_threshold.get(token_address, Decimal('0'))
                    
                    if profit_decimal > min_profit:
                        self.logger.info(f"Found profitable arbitrage opportunity: {token_symbol} -> "
                                         f"{intermediate_token} -> {token_symbol}, profit: {profit_decimal} {token_symbol}")
                        
                        # Execute the arbitrage
                        await self._execute_arbitrage(token_address, loan_amount_wei, source_router, target_router, intermediate_token)
            except Exception as e:
                self.logger.error(f"Error scanning {token_symbol} for opportunities: {str(e)}")
    
    async def _find_best_arbitrage_route(
        self, 
        token_address: str, 
        amount: int
    ) -> Optional[Tuple[str, str, str, int]]:
        """
        Find the best arbitrage route for a token
        
        Args:
            token_address: Address of the token to borrow
            amount: Amount to borrow in wei
            
        Returns:
            Tuple of (source_router, target_router, intermediate_token, profit) or None if no profitable route
        """
        best_profit = 0
        best_route = None
        
        # Get intermediate tokens (excluding the token itself)
        intermediate_tokens = [addr for addr in TOKENS.values() if addr != token_address]
        
        # Check all DEX combinations
        for source_name, source_router in DEX_ROUTERS.items():
            for target_name, target_router in DEX_ROUTERS.items():
                if source_name == target_name:
                    continue  # Skip same DEX
                
                for intermediate_token in intermediate_tokens:
                    try:
                        # Simulate the arbitrage using the contract's view function
                        profit = await self._simulate_arbitrage(
                            token_address,
                            amount,
                            source_router,
                            target_router,
                            intermediate_token
                        )
                        
                        if profit > best_profit:
                            best_profit = profit
                            best_route = (source_router, target_router, intermediate_token, profit)
                    except Exception as e:
                        # Skip this route if simulation fails
                        continue
        
        return best_route
    
    async def _simulate_arbitrage(
        self,
        token_address: str,
        amount: int,
        source_router: str,
        target_router: str,
        intermediate_token: str
    ) -> int:
        """
        Simulate an arbitrage to calculate potential profit
        
        Args:
            token_address: Address of the token to borrow
            amount: Amount to borrow in wei
            source_router: Address of the source DEX router
            target_router: Address of the target DEX router
            intermediate_token: Address of the intermediate token
            
        Returns:
            Potential profit in wei
        """
        # Create path arrays
        path1 = [token_address, intermediate_token]
        path2 = [intermediate_token, token_address]
        
        # Get UniswapV2Router02 ABI for the relevant functions
        router_abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [
                    {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        # Initialize router contracts
        source_contract = self.web3.eth.contract(address=source_router, abi=router_abi)
        target_contract = self.web3.eth.contract(address=target_router, abi=router_abi)
        
        # Simulate first swap
        amounts_out = source_contract.functions.getAmountsOut(amount, path1).call()
        intermediate_amount = amounts_out[1]
        
        # Simulate second swap
        amounts_out2 = target_contract.functions.getAmountsOut(intermediate_amount, path2).call()
        final_amount = amounts_out2[1]
        
        # Calculate profit
        if final_amount > amount:
            # Estimate flash loan fee (0.09% for Aave)
            flash_loan_fee = int(amount * 0.0009)
            
            # Calculate net profit after fee
            net_profit = final_amount - amount - flash_loan_fee
            
            return net_profit
        
        return 0
    
    async def _execute_arbitrage(
        self,
        token_address: str,
        amount: int,
        source_router: str,
        target_router: str,
        intermediate_token: str
    ):
        """
        Execute an arbitrage opportunity
        
        Args:
            token_address: Address of the token to borrow
            amount: Amount to borrow in wei
            source_router: Address of the source DEX router
            target_router: Address of the target DEX router
            intermediate_token: Address of the intermediate token
        """
        try:
            # Create the path for the arbitrage
            path = [token_address, intermediate_token, token_address]
            
            # Get optimal gas price
            gas_price = await self.gas_optimizer.get_optimal_gas_price()
            
            # Build transaction
            tx = self.contract.functions.executeFlashLoanWithPath(
                token_address,
                amount,
                source_router,
                target_router,
                path
            ).build_transaction({
                'from': self.address,
                'gas': 1000000,  # Gas limit
                'gasPrice': gas_price,
                'nonce': self.web3.eth.get_transaction_count(self.address),
            })
            
            # Sign transaction
            signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
            
            # Send transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            self.logger.info(f"Arbitrage transaction sent: {tx_hash.hex()}")
            self.executions += 1
            
            # Wait for transaction receipt
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            if receipt.status == 1:
                # Transaction successful
                self.successful_executions += 1
                
                # Get profit from event logs
                for log in receipt.logs:
                    if log.address.lower() == self.contract_address.lower():
                        # Try to decode as ProfitGenerated event
                        try:
                            event = self.contract.events.ProfitGenerated().process_log(log)
                            profit_wei = event.args.profit
                            
                            # Get token decimals
                            token_contract = self.web3.eth.contract(
                                address=token_address,
                                abi=[{
                                    "constant": True,
                                    "inputs": [],
                                    "name": "decimals",
                                    "outputs": [{"name": "", "type": "uint8"}],
                                    "payable": False,
                                    "stateMutability": "view",
                                    "type": "function"
                                }]
                            )
                            decimals = token_contract.functions.decimals().call()
                            
                            # Convert profit to human-readable format
                            profit_decimal = Decimal(profit_wei) / (10 ** decimals)
                            self.total_profit += profit_decimal
                            
                            self.logger.info(f"Arbitrage successful! Profit: {profit_decimal}")
                            
                            # Publish event
                            self.event_bus.publish("trade_executed", {
                                "strategy": "flash_loan",
                                "token": token_address,
                                "profit": float(profit_decimal),
                                "tx_hash": tx_hash.hex()
                            })
                            
                            break
                        except Exception as e:
                            self.logger.error(f"Error decoding event log: {str(e)}")
            else:
                self.logger.error(f"Arbitrage transaction failed: {tx_hash.hex()}")
        except Exception as e:
            self.logger.error(f"Error executing arbitrage: {str(e)}")
    
    def _on_opportunity_found(self, data: Dict[str, Any]):
        """
        Handle opportunity found event
        
        Args:
            data: Event data
        """
        # Check if the opportunity is relevant to this strategy
        if data.get("type") == "price_difference" and data.get("source") == "mempool":
            token_address = data.get("token")
            source_router = data.get("source_router")
            target_router = data.get("target_router")
            amount = data.get("amount")
            
            if token_address and source_router and target_router and amount:
                # Schedule arbitrage execution
                asyncio.create_task(self._execute_arbitrage(
                    token_address,
                    amount,
                    source_router,
                    target_router,
                    data.get("intermediate_token", TOKENS["USDC"])  # Default to USDC if not specified
                ))
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for this strategy
        
        Returns:
            Dictionary of performance metrics
        """
        runtime = time.time() - self.start_time if self.start_time else 0
        hours = runtime / 3600
        
        return {
            "strategy": "flash_loan",
            "executions": self.executions,
            "successful_executions": self.successful_executions,
            "success_rate": (self.successful_executions / self.executions) if self.executions > 0 else 0,
            "total_profit": float(self.total_profit),
            "profit_per_hour": float(self.total_profit / hours) if hours > 0 else 0,
            "runtime_hours": hours
        }
