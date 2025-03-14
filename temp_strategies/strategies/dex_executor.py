"""
DEX Executor Module
Handles the execution of trades on decentralized exchanges
"""

import time
import asyncio
from web3 import Web3
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from utils.config import load_config
from utils.logger import setup_logger, log_trade
from utils.contract_loader import ContractLoader
from utils.gas_price import get_optimal_gas_price
from utils.mempool_monitor import MempoolMonitor

class DEXExecutor:
    """Executor for trades on decentralized exchanges"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Set up logging
        self.logger = setup_logger("DEXExecutor")
        
        # Initialize web3 connection
        self.init_web3()
        
        # Contract loader
        self.contract_loader = ContractLoader()
        
        # Mempool monitor
        self.mempool_monitor = MempoolMonitor()
        
        # Router contracts
        self.routers = {}
    
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
        """Initialize the executor and load contracts"""
        self.logger.info("Initializing DEX Executor")
        
        if not self.w3 or not self.w3.is_connected():
            self.logger.error("Web3 not connected, DEX execution unavailable")
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
        
        # Initialize mempool monitor
        await self.mempool_monitor.initialize(self.w3)
        
        self.logger.info("DEX Executor initialized")
    
    async def approve_token(self, token_contract, router_address, amount):
        """Approve token spending for a router"""
        gas_price = await get_optimal_gas_price(self.w3)
        
        approve_tx = token_contract.functions.approve(
            router_address,
            amount
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
        
        return receipt
    
    async def swap_exact_tokens_for_tokens(self, 
                                          router_name: str, 
                                          amount_in: int, 
                                          amount_out_min: int,
                                          path: List[str],
                                          deadline: int = None):
        """Execute a token swap on a DEX"""
        if not deadline:
            deadline = int(time.time()) + 300  # 5 minutes from now
        
        try:
            router = self.routers.get(router_name)
            if not router:
                raise Exception(f"Router not found: {router_name}")
            
            # Check front-running risk
            front_running_risk = await self.mempool_monitor.check_front_running_risk(
                path[0], path[-1]
            )
            
            if front_running_risk > 0.5:  # High risk of front-running
                self.logger.warning(f"High front-running risk detected: {front_running_risk:.2f}")
                return None
            
            # Get optimal gas price
            gas_price = await get_optimal_gas_price(self.w3)
            
            # Build swap transaction
            swap_tx = router.functions.swapExactTokensForTokens(
                amount_in,
                amount_out_min,
                path,
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
            
            return receipt
            
        except Exception as e:
            self.logger.error(f"Error executing swap on {router_name}: {str(e)}")
            return None
    
    async def swap_exact_eth_for_tokens(self, 
                                       router_name: str, 
                                       amount_in: int, 
                                       amount_out_min: int,
                                       path: List[str],
                                       deadline: int = None):
        """Execute an ETH to token swap on a DEX"""
        if not deadline:
            deadline = int(time.time()) + 300  # 5 minutes from now
        
        try:
            router = self.routers.get(router_name)
            if not router:
                raise Exception(f"Router not found: {router_name}")
            
            # Check front-running risk
            front_running_risk = await self.mempool_monitor.check_front_running_risk(
                path[0], path[-1]
            )
            
            if front_running_risk > 0.5:  # High risk of front-running
                self.logger.warning(f"High front-running risk detected: {front_running_risk:.2f}")
                return None
            
            # Get optimal gas price
            gas_price = await get_optimal_gas_price(self.w3)
            
            # Build swap transaction
            swap_tx = router.functions.swapExactETHForTokens(
                amount_out_min,
                path,
                self.wallet_address,
                deadline
            ).build_transaction({
                'from': self.wallet_address,
                'value': amount_in,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            self.logger.info(f"ETH Swap transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise Exception("ETH Swap transaction failed")
            
            return receipt
            
        except Exception as e:
            self.logger.error(f"Error executing ETH swap on {router_name}: {str(e)}")
            return None
    
    async def swap_exact_tokens_for_eth(self, 
                                       router_name: str, 
                                       amount_in: int, 
                                       amount_out_min: int,
                                       path: List[str],
                                       deadline: int = None):
        """Execute a token to ETH swap on a DEX"""
        if not deadline:
            deadline = int(time.time()) + 300  # 5 minutes from now
        
        try:
            router = self.routers.get(router_name)
            if not router:
                raise Exception(f"Router not found: {router_name}")
            
            # Check front-running risk
            front_running_risk = await self.mempool_monitor.check_front_running_risk(
                path[0], path[-1]
            )
            
            if front_running_risk > 0.5:  # High risk of front-running
                self.logger.warning(f"High front-running risk detected: {front_running_risk:.2f}")
                return None
            
            # Get optimal gas price
            gas_price = await get_optimal_gas_price(self.w3)
            
            # Build swap transaction
            swap_tx = router.functions.swapExactTokensForETH(
                amount_in,
                amount_out_min,
                path,
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
            self.logger.info(f"Token to ETH Swap transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise Exception("Token to ETH Swap transaction failed")
            
            return receipt
            
        except Exception as e:
            self.logger.error(f"Error executing token to ETH swap on {router_name}: {str(e)}")
            return None
    
    async def get_amounts_out(self, router_name: str, amount_in: int, path: List[str]) -> Optional[List[int]]:
        """Get expected output amounts for a swap"""
        try:
            router = self.routers.get(router_name)
            if not router:
                raise Exception(f"Router not found: {router_name}")
            
            amounts_out = router.functions.getAmountsOut(amount_in, path).call()
            return amounts_out
            
        except Exception as e:
            self.logger.error(f"Error getting amounts out on {router_name}: {str(e)}")
            return None
    
    async def get_amounts_in(self, router_name: str, amount_out: int, path: List[str]) -> Optional[List[int]]:
        """Get required input amounts for a swap"""
        try:
            router = self.routers.get(router_name)
            if not router:
                raise Exception(f"Router not found: {router_name}")
            
            amounts_in = router.functions.getAmountsIn(amount_out, path).call()
            return amounts_in
            
        except Exception as e:
            self.logger.error(f"Error getting amounts in on {router_name}: {str(e)}")
            return None