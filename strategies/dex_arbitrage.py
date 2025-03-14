"""
DEX Arbitrage Strategy Module
Implements arbitrage strategies between different decentralized exchanges
"""

import asyncio
import time
from typing import Dict, List, Tuple, Optional, Any
from decimal import Decimal
from web3 import Web3
import json
import os

# Import utility modules
from utils.logger import setup_logger
from utils.gas_price import get_optimal_gas_price, is_transaction_profitable
from utils.profit_predictor import ProfitPredictor
from utils.contract_loader import ContractLoader
from utils.performance import PerformanceTracker

# Initialize logger
logger = setup_logger("DEXArbitrage")

class DEXArbitrageStrategy:
    """
    Implements arbitrage strategies between different decentralized exchanges
    """
    
    def __init__(self, w3: Web3, config: Dict[str, Any], event_bus: Any):
        """
        Initialize DEX arbitrage strategy
        
        Args:
            w3: Web3 instance
            config: Configuration dictionary
            event_bus: Event bus for publishing events
        """
        self.w3 = w3
        self.config = config
        self.event_bus = event_bus
        self.running = False
        self.performance = PerformanceTracker("DEXArbitrage")
        
        # Load contract ABIs
        self.contract_loader = ContractLoader(abis_dir=os.path.join("contracts", "abi"))
        
        # Initialize profit predictor
        self.profit_predictor = ProfitPredictor()
        
        # Load DEX router contracts
        self.routers = {}
        self._load_dex_routers()
        
        # Token price cache
        self.token_prices = {}
        self.last_price_update = 0
        self.PRICE_CACHE_TTL = 30  # 30 seconds
        
        logger.info("DEX Arbitrage Strategy initialized")
    
    def _load_dex_routers(self):
        """Load DEX router contracts"""
        try:
            for dex_name, dex_info in self.config['dexes'].items():
                router_address = dex_info['router_address']
                self.routers[dex_name] = self.contract_loader.load_contract(
                    self.w3, 
                    router_address, 
                    "UniswapRouter"  # Using Uniswap-compatible router ABI
                )
                logger.info(f"Loaded {dex_name} router at {router_address}")
        except Exception as e:
            logger.error(f"Error loading DEX routers: {str(e)}")
    
    async def start(self):
        """Start the DEX arbitrage strategy"""
        if self.running:
            logger.warning("DEX arbitrage strategy already running")
            return
        
        self.running = True
        logger.info("Starting DEX arbitrage strategy")
        
        # Start monitoring loop
        asyncio.create_task(self._monitor_arbitrage_opportunities())
    
    async def stop(self):
        """Stop the DEX arbitrage strategy"""
        self.running = False
        logger.info("Stopping DEX arbitrage strategy")
    
    async def _monitor_arbitrage_opportunities(self):
        """Monitor for arbitrage opportunities between DEXes"""
        logger.info("Starting arbitrage opportunity monitoring")
        
        while self.running:
            try:
                with self.performance.measure("scan_opportunities"):
                    # Scan for arbitrage opportunities across configured DEXes
                    opportunities = await self._scan_arbitrage_opportunities()
                    
                    # Process opportunities
                    if opportunities:
                        for opportunity in opportunities:
                            # Validate and execute opportunity
                            await self._process_opportunity(opportunity)
                    
                # Sleep to avoid excessive CPU usage
                await asyncio.sleep(self.config.get('scan_interval', 1.0))
                
            except Exception as e:
                logger.error(f"Error in arbitrage monitoring: {str(e)}")
                await asyncio.sleep(5)  # Sleep longer on error
    
    async def _scan_arbitrage_opportunities(self) -> List[Dict[str, Any]]:
        """
        Scan for arbitrage opportunities between DEXes
        
        Returns:
            List of arbitrage opportunities
        """
        opportunities = []
        
        # Get tokens to monitor from config
        tokens_to_monitor = self.config.get('tokens_to_monitor', [])
        
        # For each token pair, check price differences between DEXes
        for token_address in tokens_to_monitor:
            # Get token details
            token_contract = self.contract_loader.load_erc20_token(self.w3, token_address)
            token_symbol = token_contract.functions.symbol().call()
            token_decimals = token_contract.functions.decimals().call()
            
            # Check price on each DEX pair
            for source_dex, target_dex in self._get_dex_pairs():
                # Skip if same DEX
                if source_dex == target_dex:
                    continue
                
                # Get prices on both DEXes
                source_price = await self._get_token_price(token_address, source_dex)
                target_price = await self._get_token_price(token_address, target_dex)
                
                if not source_price or not target_price:
                    continue
                
                # Calculate price difference
                price_diff = (target_price - source_price) / source_price
                
                # If price difference exceeds threshold, record opportunity
                min_profit_threshold = self.config.get('min_profit_threshold', 0.005)  # 0.5%
                
                if abs(price_diff) > min_profit_threshold:
                    # Determine direction
                    if price_diff > 0:
                        buy_dex, sell_dex = source_dex, target_dex
                        buy_price, sell_price = source_price, target_price
                    else:
                        buy_dex, sell_dex = target_dex, source_dex
                        buy_price, sell_price = target_price, source_price
                        price_diff = abs(price_diff)
                    
                    # Calculate potential profit
                    trade_amount = self.config.get('default_trade_amount', 1)  # In ETH
                    potential_profit = trade_amount * price_diff
                    
                    # Create opportunity object
                    opportunity = {
                        'token_address': token_address,
                        'token_symbol': token_symbol,
                        'token_decimals': token_decimals,
                        'buy_dex': buy_dex,
                        'sell_dex': sell_dex,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'price_diff_percent': price_diff * 100,
                        'trade_amount': trade_amount,
                        'potential_profit': potential_profit,
                        'timestamp': time.time()
                    }
                    
                    # Add to opportunities list
                    opportunities.append(opportunity)
                    
                    logger.info(
                        f"Found arbitrage opportunity: {token_symbol} "
                        f"Buy on {buy_dex} at {buy_price:.6f}, "
                        f"Sell on {sell_dex} at {sell_price:.6f}, "
                        f"Diff: {price_diff*100:.2f}%, "
                        f"Potential profit: {potential_profit:.6f} ETH"
                    )
        
        # Sort opportunities by potential profit (descending)
        opportunities.sort(key=lambda x: x['potential_profit'], reverse=True)
        
        return opportunities
    
    async def _process_opportunity(self, opportunity: Dict[str, Any]):
        """
        Process and potentially execute an arbitrage opportunity
        
        Args:
            opportunity: Arbitrage opportunity details
        """
        # Check if opportunity is still valid
        is_valid = await self._validate_opportunity(opportunity)
        if not is_valid:
            logger.info(f"Opportunity for {opportunity['token_symbol']} is no longer valid")
            return
        
        # Check if opportunity is profitable after gas costs
        is_profitable = await self._check_profitability(opportunity)
        if not is_profitable:
            logger.info(f"Opportunity for {opportunity['token_symbol']} is not profitable after gas costs")
            return
        
        # Execute the arbitrage
        success = await self._execute_arbitrage(opportunity)
        if success:
            # Publish successful arbitrage event
            self.event_bus.publish(
                'arbitrage_executed',
                {
                    'strategy': 'dex_arbitrage',
                    'opportunity': opportunity,
                    'timestamp': time.time()
                }
            )
    
    async def _validate_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """
        Validate if an arbitrage opportunity is still valid
        
        Args:
            opportunity: Arbitrage opportunity details
            
        Returns:
            True if opportunity is still valid, False otherwise
        """
        # Get current prices
        token_address = opportunity['token_address']
        buy_dex = opportunity['buy_dex']
        sell_dex = opportunity['sell_dex']
        
        current_buy_price = await self._get_token_price(token_address, buy_dex, force_refresh=True)
        current_sell_price = await self._get_token_price(token_address, sell_dex, force_refresh=True)
        
        if not current_buy_price or not current_sell_price:
            return False
        
        # Calculate current price difference
        current_price_diff = (current_sell_price - current_buy_price) / current_buy_price
        
        # Check if still profitable
        min_profit_threshold = self.config.get('min_profit_threshold', 0.005)  # 0.5%
        
        return current_price_diff > min_profit_threshold
    
    async def _check_profitability(self, opportunity: Dict[str, Any]) -> bool:
        """
        Check if an arbitrage opportunity is profitable after gas costs
        
        Args:
            opportunity: Arbitrage opportunity details
            
        Returns:
            True if opportunity is profitable, False otherwise
        """
        # Get optimal gas price
        gas_price = await get_optimal_gas_price(self.w3, strategy="fast")
        
        # Estimate gas cost for the arbitrage transaction
        estimated_gas = self.config.get('estimated_gas_arbitrage', 300000)  # Default estimate
        
        # Calculate gas cost in ETH
        gas_cost_wei = gas_price * estimated_gas
        gas_cost_eth = self.w3.from_wei(gas_cost_wei, 'ether')
        
        # Get potential profit
        potential_profit = opportunity['potential_profit']
        
        # Apply safety margin
        safety_margin = self.config.get('profit_safety_margin', 1.2)  # 20% safety margin
        adjusted_gas_cost = float(gas_cost_eth) * safety_margin
        
        # Check if profitable
        is_profitable = potential_profit > adjusted_gas_cost
        
        if is_profitable:
            logger.info(
                f"Opportunity is profitable: "
                f"Potential profit: {potential_profit:.6f} ETH, "
                f"Gas cost: {gas_cost_eth:.6f} ETH, "
                f"Net profit: {potential_profit - float(gas_cost_eth):.6f} ETH"
            )
        else:
            logger.info(
                f"Opportunity is not profitable: "
                f"Potential profit: {potential_profit:.6f} ETH, "
                f"Gas cost: {gas_cost_eth:.6f} ETH"
            )
        
        return is_profitable
    
    async def _execute_arbitrage(self, opportunity: Dict[str, Any]) -> bool:
        """
        Execute an arbitrage opportunity
        
        Args:
            opportunity: Arbitrage opportunity details
            
        Returns:
            True if arbitrage was successful, False otherwise
        """
        logger.info(f"Executing arbitrage for {opportunity['token_symbol']}")
        
        try:
            # Get contract addresses
            token_address = opportunity['token_address']
            buy_dex = opportunity['buy_dex']
            sell_dex = opportunity['sell_dex']
            
            # Get router contracts
            buy_router = self.routers[buy_dex]
            sell_router = self.routers[sell_dex]
            
            # Get trade amount in wei
            trade_amount_eth = opportunity['trade_amount']
            trade_amount_wei = self.w3.to_wei(trade_amount_eth, 'ether')
            
            # Get optimal gas price
            gas_price = await get_optimal_gas_price(self.w3, strategy="fast")
            
            # Get account
            account = self.w3.eth.account.from_key(self.config['private_key'])
            
            # Check if we have enough ETH
            eth_balance = self.w3.eth.get_balance(account.address)
            if eth_balance < trade_amount_wei:
                logger.error(f"Insufficient ETH balance for trade: {self.w3.from_wei(eth_balance, 'ether')} ETH")
                return False
            
            # Execute flash loan arbitrage instead of direct trade for better capital efficiency
            # This will use the flash loan contract we've already implemented
            
            # Get flash loan contract
            flash_loan_address = self.config.get('flash_loan_contract_address')
            flash_loan_contract = self.contract_loader.load_contract(
                self.w3,
                flash_loan_address,
                "FlashLoan"
            )
            
            # Prepare transaction
            # We'll use the executeFlashLoanWithPath function from our contract
            path = [self.w3.to_checksum_address(self.config['weth_address']), token_address]
            
            # Build transaction
            tx = flash_loan_contract.functions.executeFlashLoanWithPath(
                token_address,
                trade_amount_wei,
                buy_router.address,
                sell_router.address,
                path
            ).build_transaction({
                'from': account.address,
                'gas': self.config.get('gas_limit_arbitrage', 500000),
                'gasPrice': gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
            })
            
            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.config['private_key'])
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Arbitrage transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                logger.info(f"Arbitrage transaction successful: {tx_hash.hex()}")
                return True
            else:
                logger.error(f"Arbitrage transaction failed: {tx_hash.hex()}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing arbitrage: {str(e)}")
            return False
    
    async def _get_token_price(self, token_address: str, dex_name: str, force_refresh: bool = False) -> Optional[float]:
        """
        Get token price on a specific DEX
        
        Args:
            token_address: Token address
            dex_name: DEX name
            force_refresh: Force refresh price cache
            
        Returns:
            Token price in ETH
        """
        cache_key = f"{token_address}_{dex_name}"
        current_time = time.time()
        
        # Check cache first
        if not force_refresh and cache_key in self.token_prices:
            price_data = self.token_prices[cache_key]
            if current_time - price_data['timestamp'] < self.PRICE_CACHE_TTL:
                return price_data['price']
        
        try:
            # Get router contract
            router = self.routers[dex_name]
            
            # Get WETH address
            weth_address = self.w3.to_checksum_address(self.config['weth_address'])
            
            # Get token contract
            token_contract = self.contract_loader.load_erc20_token(self.w3, token_address)
            token_decimals = token_contract.functions.decimals().call()
            
            # Amount to query (1 token)
            amount_in = 10 ** token_decimals
            
            # Get price path
            path = [self.w3.to_checksum_address(token_address), weth_address]
            
            # Get amounts out
            amounts_out = router.functions.getAmountsOut(amount_in, path).call()
            
            # Calculate price in ETH
            eth_amount = amounts_out[1]
            price = self.w3.from_wei(eth_amount, 'ether')
            
            # Cache price
            self.token_prices[cache_key] = {
                'price': float(price),
                'timestamp': current_time
            }
            
            return float(price)
            
        except Exception as e:
            logger.error(f"Error getting token price on {dex_name}: {str(e)}")
            return None
    
    def _get_dex_pairs(self) -> List[Tuple[str, str]]:
        """
        Get all possible DEX pairs for arbitrage
        
        Returns:
            List of (source_dex, target_dex) pairs
        """
        dexes = list(self.routers.keys())
        pairs = []
        
        for i in range(len(dexes)):
            for j in range(len(dexes)):
                if i != j:
                    pairs.append((dexes[i], dexes[j]))
        
        return pairs
