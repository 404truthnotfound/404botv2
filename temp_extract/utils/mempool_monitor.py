"""
Mempool Monitoring Module
Monitors pending transactions in the mempool to detect front-running risks
"""

import time
import asyncio
from web3 import Web3
from typing import Dict, List, Set, Optional, Any

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("MempoolMonitor")

class MempoolMonitor:
    """Monitors Ethereum mempool for relevant transactions"""
    
    def __init__(self):
        """Initialize mempool monitor"""
        self.w3 = None
        self.is_running = False
        self.pending_txs = {}
        self.token_txs = {}
        self.monitoring_task = None
        self.front_running_candidates = set()
        
        # Whitelisted addresses (known good actors)
        self.whitelisted_addresses = set()
        
        # Blacklisted addresses (known front-runners)
        self.blacklisted_addresses = set()
        
        # Last update time
        self.last_update = 0
    
    async def initialize(self, w3: Web3):
        """Initialize with a Web3 instance and start monitoring"""
        self.w3 = w3
        
        # Start monitoring if not already running
        if not self.is_running:
            self.is_running = True
            self.monitoring_task = asyncio.create_task(self.monitor_mempool())
    
    async def shutdown(self):
        """Stop monitoring and clean up resources"""
        self.is_running = False
        if self.monitoring_task:
            try:
                self.monitoring_task.cancel()
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
    
    async def monitor_mempool(self):
        """Monitor the mempool for pending transactions"""
        logger.info("Starting mempool monitoring")
        
        while self.is_running:
            try:
                # Get pending transactions
                pending = await asyncio.to_thread(
                    self.w3.eth.get_block, 
                    'pending', 
                    full_transactions=True
                )
                
                if not pending or not hasattr(pending, 'transactions'):
                    await asyncio.sleep(2)
                    continue
                
                # Process transactions
                await self.process_pending_transactions(pending.transactions)
                
                # Update timestamp
                self.last_update = time.time()
                
                # Sleep to avoid excessive API calls
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error monitoring mempool: {str(e)}")
                await asyncio.sleep(5)
    
    async def process_pending_transactions(self, transactions: List[Any]):
        """Process pending transactions to identify potential front-runners"""
        # Clear old data
        current_txs = {}
        current_token_txs = {}
        
        for tx in transactions:
            # Skip if no hash
            if not hasattr(tx, 'hash'):
                continue
                
            tx_hash = tx.hash.hex()
            
            # Add to current transactions
            current_txs[tx_hash] = {
                'from': tx.get('from', ''),
                'to': tx.get('to', ''),
                'value': tx.get('value', 0),
                'gas_price': tx.get('gasPrice', 0),
                'input': tx.get('input', '0x'),
                'nonce': tx.get('nonce', 0),
                'timestamp': time.time()
            }
            
            # Skip transactions with empty input
            if tx.get('input', '0x') == '0x':
                continue
            
            # Try to decode the transaction input
            # This is simplified - in production would use proper ABI decoding
            input_data = tx.get('input', '0x')
            
            # Check for token transfers or swaps
            # This is a simple heuristic - in production would decode properly
            is_token_tx = (len(input_data) >= 10 and (
                input_data.startswith('0xa9059cbb') or  # transfer
                input_data.startswith('0x23b872dd') or  # transferFrom
                input_data.startswith('0x38ed1739') or  # swapExactTokensForTokens
                input_data.startswith('0x8803dbee')     # swapTokensForExactTokens
            ))
            
            if is_token_tx:
                # Add to token transactions
                to_address = tx.get('to', '')
                if to_address and to_address.lower() != '0x0000000000000000000000000000000000000000':
                    if to_address not in current_token_txs:
                        current_token_txs[to_address] = []
                    
                    current_token_txs[to_address].append({
                        'hash': tx_hash,
                        'from': tx.get('from', ''),
                        'gas_price': tx.get('gasPrice', 0),
                        'timestamp': time.time()
                    })
        
        # Update stored data
        self.pending_txs = current_txs
        self.token_txs = current_token_txs
        
        # Detect front-running candidates
        await self.detect_front_runners()
    
    async def detect_front_runners(self):
        """Detect potential front-running transactions"""
        # Simple heuristic: addresses with multiple high-gas transactions 
        # to the same contract in a short time window
        potential_front_runners = set()
        
        for contract, txs in self.token_txs.items():
            # Group by sender
            senders = {}
            for tx in txs:
                sender = tx.get('from', '')
                if not sender:
                    continue
                
                if sender not in senders:
                    senders[sender] = []
                
                senders[sender].append(tx)
            
            # Check for addresses with multiple transactions
            for sender, sender_txs in senders.items():
                if len(sender_txs) >= 3:  # Multiple transactions to same contract
                    # Check if using above-average gas price
                    avg_gas = sum(tx.get('gas_price', 0) for tx in txs) / len(txs)
                    for tx in sender_txs:
                        if tx.get('gas_price', 0) > avg_gas * 1.5:  # 50% above average
                            potential_front_runners.add(sender)
                            break
        
        # Update front-running candidates
        self.front_running_candidates.update(potential_front_runners)
        
        # Remove candidates if they're in the whitelist
        self.front_running_candidates -= self.whitelisted_addresses
        
        # Log new front-running candidates
        new_candidates = potential_front_runners - self.front_running_candidates
        if new_candidates:
            logger.warning(f"Detected {len(new_candidates)} new potential front-runners")
    
    async def check_front_running_risk(self, token_a: str, token_b: str) -> float:
        """
        Check the front-running risk for a specific token pair
        
        Args:
            token_a: Address of first token
            token_b: Address of second token
            
        Returns:
            Risk score from 0.0 (low risk) to 1.0 (high risk)
        """
        # If no mempool data, return moderate risk
        if not self.pending_txs:
            return 0.5
        
        # Convert addresses to lowercase for consistency
        token_a = token_a.lower() if isinstance(token_a, str) else token_a
        token_b = token_b.lower() if isinstance(token_b, str) else token_b
        
        # Count relevant transactions
        token_a_tx_count = len(self.token_txs.get(token_a, []))
        token_b_tx_count = len(self.token_txs.get(token_b, []))
        
        # Check for blacklisted addresses targeting these tokens
        blacklist_activity = False
        for token in [token_a, token_b]:
            for tx in self.token_txs.get(token, []):
                if tx.get('from', '').lower() in self.blacklisted_addresses:
                    blacklist_activity = True
                    break
        
        # Calculate risk score
        risk_score = 0.0
        
        # Factor 1: Number of pending transactions
        tx_count = token_a_tx_count + token_b_tx_count
        if tx_count > 20:
            risk_score += 0.4  # High activity
        elif tx_count > 10:
            risk_score += 0.2  # Moderate activity
        elif tx_count > 5:
            risk_score += 0.1  # Some activity
        
        # Factor 2: Known front-runners
        if blacklist_activity:
            risk_score += 0.5  # Known front-runners active
        
        # Factor 3: Recent data
        data_age = time.time() - self.last_update
        if data_age > 10:
            # Old data, reduce confidence
            risk_score = max(0.3, risk_score * 0.7)
        
        # Cap at 1.0
        risk_score = min(1.0, risk_score)
        
        return risk_score
    
    def add_to_blacklist(self, address: str):
        """Add an address to the blacklist"""
        if address:
            self.blacklisted_addresses.add(address.lower())
            logger.info(f"Added {address} to front-runner blacklist")
    
    def add_to_whitelist(self, address: str):
        """Add an address to the whitelist"""
        if address:
            self.whitelisted_addresses.add(address.lower())
            
            # Remove from blacklist and candidates if present
            self.blacklisted_addresses.discard(address.lower())
            self.front_running_candidates.discard(address.lower())
            
            logger.info(f"Added {address} to whitelist")
    
    def get_pending_tx_count(self) -> int:
        """Get the number of pending transactions being monitored"""
        return len(self.pending_txs)
    
    def get_front_runner_count(self) -> int:
        """Get the number of detected front-runners"""
        return len(self.front_running_candidates) + len(self.blacklisted_addresses)