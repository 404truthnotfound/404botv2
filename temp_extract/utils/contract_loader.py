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
        
        try:
            # Load ABI
            abi = self._load_abi(contract_name)
            
            if not abi:
                logger.error(f"Could not load ABI for {contract_name}")
                return None
            
            # Create contract instance
            checksum_address = w3.to_checksum_address(address)
            contract = w3.eth.contract(address=checksum_address, abi=abi)
            
            # Cache for future use
            self.contract_cache[cache_key] = contract
            
            logger.info(f"Loaded contract {contract_name} at {address}")
            return contract
            
        except Exception as e:
            logger.error(f"Error loading contract {contract_name} at {address}: {str(e)}")
            return None
    
    def load_token_contract(self, w3: Web3, address: str) -> Any:
        """
        Load an ERC20 token contract
        
        Args:
            w3: Web3 instance
            address: Token contract address
            
        Returns:
            Token contract instance
        """
        return self.load_contract(w3, address, "erc20")
    
    def load_router_contract(self, w3: Web3, address: str) -> Any:
        """
        Load a DEX router contract
        
        Args:
            w3: Web3 instance
            address: Router contract address
            
        Returns:
            Router contract instance
        """
        return self.load_contract(w3, address, "uniswap_router")
    
    def _load_abi(self, contract_name: str) -> Optional[Dict]:
        """
        Load an ABI from file or use cached version
        
        Args:
            contract_name: Name of the contract
            
        Returns:
            Contract ABI as a dictionary
        """
        # Check cache first
        if contract_name in abi_cache:
            return abi_cache[contract_name]
        
        # Standard ABI file path
        abi_path = os.path.join(self.abis_dir, f"{contract_name.lower()}.json")
        
        try:
            if os.path.exists(abi_path):
                with open(abi_path, 'r') as f:
                    abi = json.load(f)
                
                # Cache for future use
                abi_cache[contract_name] = abi
                return abi
            else:
                # If file doesn't exist, use hardcoded ABIs for common contracts
                if contract_name.lower() == "erc20":
                    abi = self._get_erc20_abi()
                    abi_cache[contract_name] = abi
                    
                    # Save for future use
                    with open(abi_path, 'w') as f:
                        json.dump(abi, f, indent=2)
                    
                    return abi
                elif contract_name.lower() == "uniswap_router":
                    abi = self._get_uniswap_router_abi()
                    abi_cache[contract_name] = abi
                    
                    # Save for future use
                    with open(abi_path, 'w') as f:
                        json.dump(abi, f, indent=2)
                    
                    return abi
                else:
                    logger.error(f"ABI file not found: {abi_path}")
                    return None
                
        except Exception as e:
            logger.error(f"Error loading ABI {contract_name}: {str(e)}")
            return None
    
    def _get_erc20_abi(self) -> Dict:
        """Get the standard ERC20 ABI"""
        return [
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "totalSupply",
                "outputs": [{"name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"}, 
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"}, 
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"}, 
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_from", "type": "address"}, 
                    {"name": "_to", "type": "address"}, 
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transferFrom",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
    
    def _get_uniswap_router_abi(self) -> Dict:
        """Get the Uniswap Router ABI (simplified version)"""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountInMax", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapTokensForExactTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForETH",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsIn",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "factory",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]