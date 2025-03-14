"""
Token Utilities Module
Provides utilities for working with ERC20 tokens
"""

import asyncio
from web3 import Web3
from typing import Dict, List, Optional, Any, Tuple

from utils.logger import setup_logger
from utils.contract_loader import ContractLoader

# Initialize logger
logger = setup_logger("TokenUtils")

async def get_token_info(w3: Web3, token_address: str) -> Dict[str, Any]:
    """
    Get token information from a token contract
    
    Args:
        w3: Web3 instance
        token_address: Token contract address
        
    Returns:
        Dictionary with token information
    """
    try:
        # Load token contract
        contract_loader = ContractLoader()
        token_contract = contract_loader.load_token_contract(w3, token_address)
        
        if not token_contract:
            logger.error(f"Could not load token contract at {token_address}")
            return {}
        
        # Get token information
        token_info = {}
        
        # Get token name
        try:
            token_info['name'] = token_contract.functions.name().call()
        except Exception as e:
            logger.warning(f"Could not get token name: {str(e)}")
            token_info['name'] = "Unknown Token"
        
        # Get token symbol
        try:
            token_info['symbol'] = token_contract.functions.symbol().call()
        except Exception as e:
            logger.warning(f"Could not get token symbol: {str(e)}")
            token_info['symbol'] = "???"
        
        # Get token decimals
        try:
            token_info['decimals'] = token_contract.functions.decimals().call()
        except Exception as e:
            logger.warning(f"Could not get token decimals: {str(e)}")
            token_info['decimals'] = 18  # Default to 18 decimals
        
        # Get token total supply
        try:
            token_info['totalSupply'] = token_contract.functions.totalSupply().call()
            token_info['totalSupplyFormatted'] = token_info['totalSupply'] / (10 ** token_info['decimals'])
        except Exception as e:
            logger.warning(f"Could not get token totalSupply: {str(e)}")
            token_info['totalSupply'] = 0
            token_info['totalSupplyFormatted'] = 0
        
        return token_info
        
    except Exception as e:
        logger.error(f"Error getting token info for {token_address}: {str(e)}")
        return {}

async def get_token_balance(w3: Web3, token_address: str, wallet_address: str) -> Tuple[int, float]:
    """
    Get token balance for a wallet
    
    Args:
        w3: Web3 instance
        token_address: Token contract address
        wallet_address: Wallet address
        
    Returns:
        Tuple of (raw_balance, formatted_balance)
    """
    try:
        # Load token contract
        contract_loader = ContractLoader()
        token_contract = contract_loader.load_token_contract(w3, token_address)
        
        if not token_contract:
            logger.error(f"Could not load token contract at {token_address}")
            return 0, 0.0
        
        # Get token decimals
        try:
            decimals = token_contract.functions.decimals().call()
        except Exception as e:
            logger.warning(f"Could not get token decimals: {str(e)}")
            decimals = 18  # Default to 18 decimals
        
        # Get token balance
        raw_balance = token_contract.functions.balanceOf(wallet_address).call()
        formatted_balance = raw_balance / (10 ** decimals)
        
        return raw_balance, formatted_balance
        
    except Exception as e:
        logger.error(f"Error getting token balance for {wallet_address}: {str(e)}")
        return 0, 0.0

async def get_token_allowance(w3: Web3, token_address: str, owner_address: str, spender_address: str) -> Tuple[int, float]:
    """
    Get token allowance for a spender
    
    Args:
        w3: Web3 instance
        token_address: Token contract address
        owner_address: Token owner address
        spender_address: Spender address
        
    Returns:
        Tuple of (raw_allowance, formatted_allowance)
    """
    try:
        # Load token contract
        contract_loader = ContractLoader()
        token_contract = contract_loader.load_token_contract(w3, token_address)
        
        if not token_contract:
            logger.error(f"Could not load token contract at {token_address}")
            return 0, 0.0
        
        # Get token decimals
        try:
            decimals = token_contract.functions.decimals().call()
        except Exception as e:
            logger.warning(f"Could not get token decimals: {str(e)}")
            decimals = 18  # Default to 18 decimals
        
        # Get token allowance
        raw_allowance = token_contract.functions.allowance(owner_address, spender_address).call()
        formatted_allowance = raw_allowance / (10 ** decimals)
        
        return raw_allowance, formatted_allowance
        
    except Exception as e:
        logger.error(f"Error getting token allowance for {owner_address} -> {spender_address}: {str(e)}")
        return 0, 0.0

async def approve_token(
    w3: Web3,
    token_address: str,
    spender_address: str,
    amount: int,
    private_key: str,
    gas_price: Optional[int] = None
) -> Optional[str]:
    """
    Approve a spender to spend tokens
    
    Args:
        w3: Web3 instance
        token_address: Token contract address
        spender_address: Spender address
        amount: Amount to approve (in token's smallest unit)
        private_key: Private key for signing
        gas_price: Optional gas price in wei
        
    Returns:
        Transaction hash if successful, None otherwise
    """
    try:
        # Load token contract
        contract_loader = ContractLoader()
        token_contract = contract_loader.load_token_contract(w3, token_address)
        
        if not token_contract:
            logger.error(f"Could not load token contract at {token_address}")
            return None
        
        # Get wallet address from private key
        account = w3.eth.account.from_key(private_key)
        wallet_address = account.address
        
        # Build approval transaction
        if gas_price is None:
            gas_price = w3.eth.gas_price
        
        nonce = w3.eth.get_transaction_count(wallet_address)
        
        tx = token_contract.functions.approve(
            spender_address,
            amount
        ).build_transaction({
            'from': wallet_address,
            'gas': 100000,  # 100k gas should be enough for approve
            'gasPrice': gas_price,
            'nonce': nonce
        })
        
        # Sign and send transaction
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        logger.info(f"Sent approval transaction: {tx_hash.hex()}")
        return tx_hash.hex()
        
    except Exception as e:
        logger.error(f"Error approving tokens: {str(e)}")
        return None

def to_wei(amount: float, decimals: int = 18) -> int:
    """
    Convert a decimal amount to wei
    
    Args:
        amount: Amount in decimal
        decimals: Number of decimals
        
    Returns:
        Amount in wei
    """
    return int(amount * (10 ** decimals))

def from_wei(amount: int, decimals: int = 18) -> float:
    """
    Convert a wei amount to decimal
    
    Args:
        amount: Amount in wei
        decimals: Number of decimals
        
    Returns:
        Amount in decimal
    """
    return amount / (10 ** decimals)

def is_valid_token_address(w3: Web3, address: str) -> bool:
    """
    Check if an address is a valid token contract
    
    Args:
        w3: Web3 instance
        address: Address to check
        
    Returns:
        True if valid token contract, False otherwise
    """
    try:
        # Check if address is valid
        if not w3.is_address(address):
            return False
        
        # Check if address has code
        code = w3.eth.get_code(address)
        if code == b'':  # Empty bytecode means not a contract
            return False
        
        # Load token contract
        contract_loader = ContractLoader()
        token_contract = contract_loader.load_token_contract(w3, address)
        
        if not token_contract:
            return False
        
        # Try to call basic ERC20 functions
        try:
            symbol = token_contract.functions.symbol().call()
            decimals = token_contract.functions.decimals().call()
            total_supply = token_contract.functions.totalSupply().call()
            
            # All calls succeeded, likely a valid token
            return True
        except Exception:
            return False
            
    except Exception:
        return False

def generate_token_hash(token_symbol: str, token_address: str) -> str:
    """
    Generate a unique hash for a token
    
    Args:
        token_symbol: Token symbol
        token_address: Token contract address
        
    Returns:
        Unique token hash
    """
    import hashlib
    
    # Normalize inputs
    symbol = token_symbol.upper() if token_symbol else ""
    address = token_address.lower() if token_address else ""
    
    # Generate hash
    token_string = f"{symbol}:{address}"
    return hashlib.md5(token_string.encode()).hexdigest()

def calculate_tokens_out(amount_in: int, reserve_in: int, reserve_out: int, fee: int = 3) -> int:
    """
    Calculate the output amount for a Uniswap-style swap
    
    Args:
        amount_in: Input amount
        reserve_in: Reserve of input token
        reserve_out: Reserve of output token
        fee: Fee in basis points (e.g. 3 for 0.3%)
        
    Returns:
        Output amount
    """
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    
    # Apply fee
    amount_in_with_fee = amount_in * (10000 - fee)
    
    # Calculate output amount
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 10000 + amount_in_with_fee
    
    return numerator // denominator