"""
404Bot v2 - Mempool Monitor
High-performance mempool monitoring for MEV opportunities
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Set, Optional, Any, Callable
from web3 import Web3
from web3.exceptions import TransactionNotFound
import websockets

from core.event_bus import EventBus

class MempoolMonitor:
    """
    High-performance mempool monitor for detecting arbitrage opportunities
    Uses websocket subscription for minimal latency
    """
    
    def __init__(self, web3_provider: str, private_key: str, event_bus: EventBus):
        """
        Initialize the mempool monitor
        
        Args:
            web3_provider: WebSocket URL for Ethereum node
            private_key: Private key for transaction signing
            event_bus: Event bus for publishing events
        """
        self.logger = logging.getLogger("MempoolMonitor")
        self.web3_provider = web3_provider
        self.private_key = private_key
        self.event_bus = event_bus
        
        # Initialize Web3
        self.web3 = Web3(Web3.WebsocketProvider(web3_provider))
        self.account = self.web3.eth.account.from_key(private_key)
        self.address = self.account.address
        
        # Websocket connection
        self.ws = None
        
        # Transaction tracking
        self.pending_txs = {}
        self.processed_txs = set()
        self.interesting_addresses = set()
        self.interesting_methods = {}
        
        # Running state
        self.running = False
        self.tasks = []
        
        # Performance metrics
        self.tx_count = 0
        self.interesting_tx_count = 0
        self.start_time = None
        
        self.logger.info("Mempool Monitor initialized")
    
    def register_interesting_address(self, address: str):
        """
        Register an address to monitor in the mempool
        
        Args:
            address: Ethereum address to monitor
        """
        self.interesting_addresses.add(Web3.to_checksum_address(address))
    
    def register_interesting_method(self, contract_address: str, method_signature: str, callback: Callable):
        """
        Register a method signature to monitor in the mempool
        
        Args:
            contract_address: Contract address
            method_signature: Method signature (e.g., "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)")
            callback: Function to call when method is detected
        """
        contract_address = Web3.to_checksum_address(contract_address)
        
        # Calculate method ID (first 4 bytes of keccak hash of method signature)
        method_id = self.web3.keccak(text=method_signature).hex()[:10]
        
        if contract_address not in self.interesting_methods:
            self.interesting_methods[contract_address] = {}
        
        self.interesting_methods[contract_address][method_id] = {
            "signature": method_signature,
            "callback": callback
        }
        
        self.logger.debug(f"Registered method {method_signature} ({method_id}) for contract {contract_address}")
    
    async def start(self):
        """Start mempool monitoring"""
        if self.running:
            return
        
        self.logger.info("Starting Mempool Monitor...")
        self.running = True
        self.start_time = time.time()
        
        # Start websocket connection
        self.tasks.append(asyncio.create_task(self._connect_and_subscribe()))
        
        # Start transaction processing
        self.tasks.append(asyncio.create_task(self._process_pending_transactions()))
        
        # Start metrics logging
        self.tasks.append(asyncio.create_task(self._log_metrics()))
        
        self.logger.info("Mempool Monitor started")
    
    async def stop(self):
        """Stop mempool monitoring"""
        if not self.running:
            return
        
        self.logger.info("Stopping Mempool Monitor...")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close websocket connection
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        self.logger.info("Mempool Monitor stopped")
    
    async def _connect_and_subscribe(self):
        """Connect to websocket and subscribe to pending transactions"""
        retry_count = 0
        max_retries = 10
        retry_delay = 5
        
        while self.running:
            try:
                # Close existing connection if any
                if self.ws:
                    await self.ws.close()
                
                # Connect to websocket
                self.logger.info(f"Connecting to {self.web3_provider}...")
                self.ws = await websockets.connect(self.web3_provider)
                
                # Subscribe to pending transactions
                subscribe_message = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"]
                }
                
                await self.ws.send(json.dumps(subscribe_message))
                response = await self.ws.recv()
                response_json = json.loads(response)
                
                if "result" in response_json:
                    subscription_id = response_json["result"]
                    self.logger.info(f"Subscribed to pending transactions with ID: {subscription_id}")
                    
                    # Reset retry count on successful connection
                    retry_count = 0
                    
                    # Process incoming messages
                    while self.running:
                        try:
                            message = await asyncio.wait_for(self.ws.recv(), timeout=30)
                            await self._handle_websocket_message(message)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            pong_waiter = await self.ws.ping()
                            await asyncio.wait_for(pong_waiter, timeout=10)
                        except websockets.exceptions.ConnectionClosed:
                            self.logger.warning("Websocket connection closed")
                            break
                else:
                    self.logger.error(f"Failed to subscribe: {response_json}")
            
            except (websockets.exceptions.ConnectionClosed, 
                    websockets.exceptions.InvalidStatusCode,
                    ConnectionRefusedError) as e:
                retry_count += 1
                if retry_count > max_retries:
                    self.logger.error(f"Max retries ({max_retries}) exceeded. Stopping mempool monitor.")
                    self.running = False
                    break
                
                self.logger.warning(f"Connection error: {str(e)}. Retrying in {retry_delay} seconds... ({retry_count}/{max_retries})")
                await asyncio.sleep(retry_delay)
                
                # Increase delay for next retry (exponential backoff)
                retry_delay = min(retry_delay * 2, 60)
            
            except Exception as e:
                self.logger.error(f"Unexpected error in websocket connection: {str(e)}")
                await asyncio.sleep(retry_delay)
    
    async def _handle_websocket_message(self, message: str):
        """
        Handle incoming websocket message
        
        Args:
            message: JSON message from websocket
        """
        try:
            message_json = json.loads(message)
            
            # Check if this is a subscription message
            if "method" in message_json and message_json["method"] == "eth_subscription":
                params = message_json.get("params", {})
                if "result" in params:
                    tx_hash = params["result"]
                    
                    # Skip if already processed
                    if tx_hash in self.processed_txs:
                        return
                    
                    # Add to pending transactions
                    self.pending_txs[tx_hash] = time.time()
                    self.tx_count += 1
        
        except json.JSONDecodeError:
            self.logger.warning(f"Invalid JSON message: {message}")
        except Exception as e:
            self.logger.error(f"Error handling websocket message: {str(e)}")
    
    async def _process_pending_transactions(self):
        """Process pending transactions from the mempool"""
        while self.running:
            try:
                # Process up to 20 transactions per batch
                tx_hashes = list(self.pending_txs.keys())[:20]
                
                if not tx_hashes:
                    await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning
                    continue
                
                # Process transactions in parallel
                tasks = [self._process_transaction(tx_hash) for tx_hash in tx_hashes]
                await asyncio.gather(*tasks)
                
                # Remove processed transactions
                for tx_hash in tx_hashes:
                    self.pending_txs.pop(tx_hash, None)
                    self.processed_txs.add(tx_hash)
                
                # Limit size of processed transactions set
                if len(self.processed_txs) > 10000:
                    self.processed_txs = set(list(self.processed_txs)[-5000:])
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing pending transactions: {str(e)}")
                await asyncio.sleep(1)
    
    async def _process_transaction(self, tx_hash: str):
        """
        Process a single transaction from the mempool
        
        Args:
            tx_hash: Transaction hash
        """
        try:
            # Get transaction details
            tx = await asyncio.to_thread(self._get_transaction, tx_hash)
            
            if not tx:
                return
            
            # Check if transaction is interesting
            is_interesting = await self._is_interesting_transaction(tx)
            
            if is_interesting:
                self.interesting_tx_count += 1
                
                # Publish event
                await self.event_bus.publish_async("interesting_transaction", {
                    "tx_hash": tx_hash,
                    "tx": tx
                })
        
        except TransactionNotFound:
            # Transaction no longer in mempool
            pass
        except Exception as e:
            self.logger.error(f"Error processing transaction {tx_hash}: {str(e)}")
    
    def _get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """
        Get transaction details from the mempool
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            Transaction details or None if not found
        """
        try:
            return self.web3.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error getting transaction {tx_hash}: {str(e)}")
            return None
    
    async def _is_interesting_transaction(self, tx: Dict) -> bool:
        """
        Check if a transaction is interesting for arbitrage
        
        Args:
            tx: Transaction details
            
        Returns:
            True if transaction is interesting, False otherwise
        """
        # Skip transactions with empty input data (simple ETH transfers)
        if not tx.get("input") or tx["input"] == "0x":
            return False
        
        # Check if transaction is to an interesting address
        to_address = tx.get("to")
        if to_address and to_address in self.interesting_addresses:
            return True
        
        # Check if transaction calls an interesting method
        if to_address and to_address in self.interesting_methods:
            input_data = tx.get("input", "0x")
            if len(input_data) >= 10:
                method_id = input_data[:10]
                if method_id in self.interesting_methods[to_address]:
                    method_info = self.interesting_methods[to_address][method_id]
                    
                    # Call the registered callback
                    try:
                        callback = method_info["callback"]
                        if asyncio.iscoroutinefunction(callback):
                            result = await callback(tx)
                        else:
                            result = callback(tx)
                        
                        return result
                    except Exception as e:
                        self.logger.error(f"Error in method callback: {str(e)}")
        
        return False
    
    async def _log_metrics(self):
        """Log performance metrics periodically"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Log every minute
                
                if not self.start_time:
                    continue
                
                runtime = time.time() - self.start_time
                tx_per_second = self.tx_count / max(1, runtime)
                interesting_percentage = (self.interesting_tx_count / max(1, self.tx_count)) * 100
                
                self.logger.info(f"Mempool metrics: {self.tx_count} transactions processed "
                                f"({tx_per_second:.2f}/s), {self.interesting_tx_count} interesting "
                                f"({interesting_percentage:.2f}%)")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error logging metrics: {str(e)}")
                await asyncio.sleep(60)
