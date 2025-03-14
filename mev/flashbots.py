"""
404Bot v2 - Flashbots Integration
Handles private transaction bundling and submission through Flashbots
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any
from web3 import Web3
from eth_account.account import Account
from eth_account.signers.local import LocalAccount
import httpx

from core.event_bus import EventBus

class FlashbotsManager:
    """
    Manages Flashbots integration for private transaction submission
    Supports both Flashbots and Eden Network for optimal MEV extraction
    """
    
    def __init__(self, web3_provider: str, private_key: str, event_bus: EventBus):
        """
        Initialize Flashbots manager
        
        Args:
            web3_provider: URL for Ethereum node
            private_key: Private key for transaction signing
            event_bus: Event bus for publishing events
        """
        self.logger = logging.getLogger("FlashbotsManager")
        self.web3_provider = web3_provider
        self.private_key = private_key
        self.event_bus = event_bus
        
        # Initialize Web3
        self.web3 = Web3(Web3.HTTPProvider(web3_provider))
        self.account = self.web3.eth.account.from_key(private_key)
        self.address = self.account.address
        
        # Flashbots configuration
        self.flashbots_endpoint = "https://relay.flashbots.net"
        self.eden_endpoint = "https://api.edennetwork.io/v1/bundle"
        
        # Create a new account for Flashbots authentication
        self.flashbots_auth_key = Account.create()
        
        # HTTP client for API requests
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
        # Running state
        self.running = False
        self.tasks = []
        
        # Performance metrics
        self.bundles_submitted = 0
        self.bundles_included = 0
        
        self.logger.info(f"Flashbots Manager initialized with auth address: {self.flashbots_auth_key.address}")
    
    async def start(self):
        """Start Flashbots manager"""
        if self.running:
            return
        
        self.logger.info("Starting Flashbots Manager...")
        self.running = True
        
        # Register event handlers
        self.event_bus.subscribe("submit_bundle", self.submit_bundle)
        
        # Start metrics logging
        self.tasks.append(asyncio.create_task(self._log_metrics()))
        
        self.logger.info("Flashbots Manager started")
    
    async def stop(self):
        """Stop Flashbots manager"""
        if not self.running:
            return
        
        self.logger.info("Stopping Flashbots Manager...")
        self.running = False
        
        # Unregister event handlers
        self.event_bus.unsubscribe("submit_bundle", self.submit_bundle)
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close HTTP client
        await self.http_client.aclose()
        
        self.logger.info("Flashbots Manager stopped")
    
    async def submit_bundle(self, data: Dict):
        """
        Submit a transaction bundle to Flashbots
        
        Args:
            data: Bundle data containing transactions and target block
        """
        try:
            transactions = data.get("transactions", [])
            target_block = data.get("target_block")
            
            if not transactions or not target_block:
                self.logger.error("Missing transactions or target block in bundle submission")
                return
            
            # Submit to both Flashbots and Eden Network for maximum inclusion chance
            flashbots_task = self._submit_to_flashbots(transactions, target_block)
            eden_task = self._submit_to_eden(transactions, target_block)
            
            # Wait for both submissions to complete
            results = await asyncio.gather(flashbots_task, eden_task, return_exceptions=True)
            
            # Check results
            flashbots_result, eden_result = results
            
            # Log results
            if isinstance(flashbots_result, Exception):
                self.logger.error(f"Flashbots submission error: {str(flashbots_result)}")
            else:
                self.logger.info(f"Flashbots submission result: {flashbots_result}")
            
            if isinstance(eden_result, Exception):
                self.logger.error(f"Eden Network submission error: {str(eden_result)}")
            else:
                self.logger.info(f"Eden Network submission result: {eden_result}")
            
            # Increment counter
            self.bundles_submitted += 1
            
            # Publish event
            await self.event_bus.publish_async("bundle_submitted", {
                "flashbots_result": flashbots_result if not isinstance(flashbots_result, Exception) else None,
                "eden_result": eden_result if not isinstance(eden_result, Exception) else None,
                "target_block": target_block
            })
        
        except Exception as e:
            self.logger.error(f"Error submitting bundle: {str(e)}")
    
    async def _submit_to_flashbots(self, transactions: List[Dict], target_block: int) -> Dict:
        """
        Submit a bundle to Flashbots relay
        
        Args:
            transactions: List of signed transaction objects
            target_block: Target block number for inclusion
            
        Returns:
            Response from Flashbots relay
        """
        # Convert transactions to hex strings if they aren't already
        tx_list = []
        for tx in transactions:
            if isinstance(tx, dict) and "rawTransaction" in tx:
                tx_list.append(tx["rawTransaction"].hex() if not isinstance(tx["rawTransaction"], str) else tx["rawTransaction"])
            elif isinstance(tx, str):
                tx_list.append(tx)
            else:
                raise ValueError(f"Unsupported transaction format: {type(tx)}")
        
        # Prepare request payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_sendBundle",
            "params": [{
                "txs": tx_list,
                "blockNumber": hex(target_block),
                "minTimestamp": 0,
                "maxTimestamp": 2**32 - 1,
                "revertingTxHashes": []
            }]
        }
        
        # Sign the request with Flashbots auth key
        signature = self._sign_flashbots_request(json.dumps(payload), self.flashbots_auth_key)
        
        # Send request to Flashbots relay
        headers = {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self.flashbots_auth_key.address}:{signature.hex()}"
        }
        
        async with self.http_client.stream("POST", self.flashbots_endpoint, json=payload, headers=headers) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise ValueError(f"Flashbots submission failed with status {response.status_code}: {error_text.decode()}")
            
            response_json = await response.json()
            return response_json
    
    async def _submit_to_eden(self, transactions: List[Dict], target_block: int) -> Dict:
        """
        Submit a bundle to Eden Network
        
        Args:
            transactions: List of signed transaction objects
            target_block: Target block number for inclusion
            
        Returns:
            Response from Eden Network
        """
        # Convert transactions to hex strings if they aren't already
        tx_list = []
        for tx in transactions:
            if isinstance(tx, dict) and "rawTransaction" in tx:
                tx_list.append(tx["rawTransaction"].hex() if not isinstance(tx["rawTransaction"], str) else tx["rawTransaction"])
            elif isinstance(tx, str):
                tx_list.append(tx)
            else:
                raise ValueError(f"Unsupported transaction format: {type(tx)}")
        
        # Prepare request payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_sendBundle",
            "params": [{
                "txs": tx_list,
                "blockNumber": hex(target_block),
                "minTimestamp": 0,
                "maxTimestamp": 2**32 - 1
            }]
        }
        
        # Sign the request with Flashbots auth key (Eden uses same format)
        signature = self._sign_flashbots_request(json.dumps(payload), self.flashbots_auth_key)
        
        # Send request to Eden Network
        headers = {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self.flashbots_auth_key.address}:{signature.hex()}"
        }
        
        async with self.http_client.stream("POST", self.eden_endpoint, json=payload, headers=headers) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise ValueError(f"Eden Network submission failed with status {response.status_code}: {error_text.decode()}")
            
            response_json = await response.json()
            return response_json
    
    def _sign_flashbots_request(self, payload: str, account: LocalAccount) -> bytes:
        """
        Sign a Flashbots request with the specified account
        
        Args:
            payload: Request payload as a string
            account: Account to sign with
            
        Returns:
            Signature bytes
        """
        message = Web3.keccak(text=payload)
        signed_message = account.sign_message(message)
        return signed_message.signature
    
    async def simulate_bundle(self, transactions: List[Dict], block_number: Optional[int] = None) -> Dict:
        """
        Simulate a bundle execution using Flashbots
        
        Args:
            transactions: List of signed transaction objects
            block_number: Block number to simulate at (default: latest)
            
        Returns:
            Simulation results
        """
        # Convert transactions to hex strings if they aren't already
        tx_list = []
        for tx in transactions:
            if isinstance(tx, dict) and "rawTransaction" in tx:
                tx_list.append(tx["rawTransaction"].hex() if not isinstance(tx["rawTransaction"], str) else tx["rawTransaction"])
            elif isinstance(tx, str):
                tx_list.append(tx)
            else:
                raise ValueError(f"Unsupported transaction format: {type(tx)}")
        
        # Get block number if not provided
        if block_number is None:
            block_number = await asyncio.to_thread(lambda: self.web3.eth.block_number)
        
        # Prepare request payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_callBundle",
            "params": [{
                "txs": tx_list,
                "blockNumber": hex(block_number),
                "stateBlockNumber": "latest"
            }]
        }
        
        # Sign the request with Flashbots auth key
        signature = self._sign_flashbots_request(json.dumps(payload), self.flashbots_auth_key)
        
        # Send request to Flashbots relay
        headers = {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self.flashbots_auth_key.address}:{signature.hex()}"
        }
        
        async with self.http_client.stream("POST", f"{self.flashbots_endpoint}", json=payload, headers=headers) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise ValueError(f"Flashbots simulation failed with status {response.status_code}: {error_text.decode()}")
            
            response_json = await response.json()
            return response_json
    
    async def _log_metrics(self):
        """Log performance metrics periodically"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Log every 5 minutes
                
                success_rate = (self.bundles_included / max(1, self.bundles_submitted)) * 100
                
                self.logger.info(f"Flashbots metrics: {self.bundles_submitted} bundles submitted, "
                                f"{self.bundles_included} included ({success_rate:.2f}%)")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error logging metrics: {str(e)}")
                await asyncio.sleep(60)
