"""
Contract Loader Module
Handles loading and managing Ethereum smart contracts
"""

import json
import os
from web3 import Web3
from typing import Dict, Any, Optional

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("ContractLoader")

# ABI cache to avoid loading the same ABI multiple times
abi_cache = {}

class ContractLoader:
    """Utility class for loading and managing Ethereum contracts"""
    
    def __init__(self, abis_dir: str = "abis"):
        """
        Initialize the contract loader
        
        Args:
            abis_dir: Directory containing contract ABI files
        """
        self.abis_dir = abis_dir
        self.contract_cache = {}
        
        # Ensure the ABI directory exists
        if not os.path.exists(abis_dir):
            os.makedirs(abis_dir)
            logger.info(f"Created ABIs directory: {abis_dir}")
    
    def load_contract(self, w3: Web3, address: str, contract_name: str) -> Any:
        """
        Load a contract by address and name
        
        Args:
            w3: Web3 instance
            address: Contract address
            contract_name: Name of the contract (used to find ABI file)
            
        Returns:
            Contract instance
        """
        cache_key = f"{address}_{contract_name}"
        if cache_key in self.contract_cache:
            return self.contract_cache[cache_key]
        
        # Load ABI
        abi = self.load_abi(contract_name)
        if not abi:
            logger.error(f"Failed to load ABI for {contract_name}")
            return None
        
        # Create contract instance
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
        
        # Cache contract
        self.contract_cache[cache_key] = contract
        
        return contract
    
    def load_abi(self, contract_name: str) -> Optional[list]:
        """
        Load contract ABI from file
        
        Args:
            contract_name: Name of the contract
            
        Returns:
            Contract ABI as list
        """
        # Check cache first
        if contract_name in abi_cache:
            return abi_cache[contract_name]
        
        # Find ABI file
        abi_path = os.path.join(self.abis_dir, f"{contract_name}.json")
        
        try:
            if os.path.exists(abi_path):
                with open(abi_path, 'r') as f:
                    abi = json.load(f)
                
                # Cache ABI
                abi_cache[contract_name] = abi
                
                return abi
            else:
                logger.error(f"ABI file not found: {abi_path}")
                return None
        except Exception as e:
            logger.error(f"Error loading ABI for {contract_name}: {str(e)}")
            return None
    
    def load_erc20_token(self, w3: Web3, token_address: str) -> Any:
        """
        Load an ERC20 token contract
        
        Args:
            w3: Web3 instance
            token_address: Token contract address
            
        Returns:
            ERC20 token contract instance
        """
        return self.load_contract(w3, token_address, "ERC20")
    
    def get_contract_events(self, contract: Any, event_name: str, from_block: int, to_block: int = 'latest') -> list:
        """
        Get events from a contract
        
        Args:
            contract: Contract instance
            event_name: Name of the event to get
            from_block: Starting block
            to_block: Ending block
            
        Returns:
            List of events
        """
        try:
            event_filter = contract.events[event_name].create_filter(
                fromBlock=from_block,
                toBlock=to_block
            )
            return event_filter.get_all_entries()
        except Exception as e:
            logger.error(f"Error getting events {event_name} from contract: {str(e)}")
            return []
