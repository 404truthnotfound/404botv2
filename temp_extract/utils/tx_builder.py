"""
Transaction Builder Module
Provides utilities for building, signing, and sending Ethereum transactions
"""

import time
import asyncio
from web3 import Web3
from typing import Dict, Optional, Any, Tuple

from utils.logger import setup_logger
from utils.gas_price import get_optimal_gas_price
from utils.web3_provider import get_web3

# Initialize logger
logger = setup_logger("TxBuilder")

async def build_transaction(
    w3: Web3,
    to_address: str,
    value: int = 0,
    data: str = "0x",
    gas_price: Optional[int] = None,
    gas_limit: Optional[int] = None,
    nonce: Optional[int] = None,
    from_address: Optional[str] = None,
    gas_strategy: str = "balanced"
) -> Dict[str, Any]:
    """
    Build an Ethereum transaction
    
    Args:
        w3: Web3 instance
        to_address: Recipient address
        value: Transaction value in wei
        data: Transaction data
        gas_price: Gas price in wei
        gas_limit: Gas limit
        nonce: Transaction nonce
        from_address: Sender address
        gas_strategy: Gas price strategy ("fast", "balanced", "economic")
        
    Returns:
        Transaction dictionary
    """
    # Ensure to_address is checksum
    to_address = w3.to_checksum_address(to_address)
    
    # If from_address not provided, try to get from w3.eth.defaultAccount
    if not from_address:
        from_address = w3.eth.default_account
        if not from_address:
            raise ValueError("from_address not provided and defaultAccount not set")
    else:
        from_address = w3.to_checksum_address(from_address)
    
    # Get optimal gas price if not provided
    if not gas_price:
        gas_price = await get_optimal_gas_price(w3, gas_strategy)
    
    # Get nonce if not provided
    if nonce is None:
        nonce = w3.eth.get_transaction_count(from_address)
    
    # Build transaction
    tx = {
        'from': from_address,
        'to': to_address,
        'value': value,
        'nonce': nonce,
        'gasPrice': gas_price,
    }
    
    # Add data if provided
    if data and data != "0x":
        tx['data'] = data
    
    # Estimate gas if not provided
    if not gas_limit:
        try:
            gas_limit = w3.eth.estimate_gas(tx)
            # Add 10% buffer
            gas_limit = int(gas_limit * 1.1)
        except Exception as e:
            logger.warning(f"Error estimating gas: {str(e)}")
            gas_limit = 100000  # Default gas limit
    
    tx['gas'] = gas_limit
    
    return tx

async def sign_and_send_transaction(
    w3: Web3,
    tx: Dict[str, Any],
    private_key: str
) -> Tuple[str, Dict[str, Any]]:
    """
    Sign and send a transaction
    
    Args:
        w3: Web3 instance
        tx: Transaction dictionary
        private_key: Private key for signing
        
    Returns:
        Tuple of (transaction hash, transaction receipt)
    """
    try:
        # Sign transaction
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        
        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        
        logger.info(f"Transaction sent: {tx_hash_hex}")
        
        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        # Check if successful
        if receipt['status'] == 1:
            logger.info(f"Transaction successful: {tx_hash_hex}")
        else:
            logger.warning(f"Transaction failed: {tx_hash_hex}")
        
        return tx_hash_hex, receipt
        
    except Exception as e:
        logger.error(f"Error sending transaction: {str(e)}")
        raise

async def wait_for_transaction_confirmation(
    w3: Web3,
    tx_hash: str,
    confirmations: int = 1,
    timeout: int = 120
) -> Optional[Dict[str, Any]]:
    """
    Wait for a transaction to be confirmed
    
    Args:
        w3: Web3 instance
        tx_hash: Transaction hash
        confirmations: Number of confirmations to wait for
        timeout: Timeout in seconds
        
    Returns:
        Transaction receipt or None if timeout
    """
    start_time = time.time()
    
    # Convert string hash to bytes if needed
    if isinstance(tx_hash, str) and tx_hash.startswith('0x'):
        tx_hash = w3.to_bytes(hexstr=tx_hash)
    
    while time.time() - start_time < timeout:
        try:
            # Get transaction receipt
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            
            if receipt is None:
                # Transaction not yet mined
                await asyncio.sleep(1)
                continue
            
            # Get current block number
            current_block = w3.eth.block_number
            
            # Check confirmations
            if receipt['blockNumber'] + confirmations <= current_block:
                return receipt
            
            # Wait for next block
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.warning(f"Error checking transaction receipt: {str(e)}")
            await asyncio.sleep(1)
    
    logger.warning(f"Timeout waiting for transaction confirmation: {tx_hash.hex()}")
    return None

async def simulate_transaction(
    w3: Web3,
    tx: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Simulate a transaction to check if it would succeed
    
    Args:
        w3: Web3 instance
        tx: Transaction dictionary
        
    Returns:
        Tuple of (success, error message)
    """
    try:
        # Clone transaction to avoid modifying the original
        sim_tx = tx.copy()
        
        # Make sure gas estimation doesn't fail
        if 'gas' not in sim_tx:
            sim_tx['gas'] = 2000000  # High default for simulation
        
        # Call the transaction
        result = w3.eth.call(sim_tx, 'latest')
        
        # If we get here, the transaction should succeed
        return True, "Transaction simulation successful"
        
    except Exception as e:
        error_msg = str(e)
        
        # Try to parse error message
        if "revert" in error_msg.lower():
            # Extract revert reason if possible
            reason = "Unknown revert reason"
            if "revert:" in error_msg:
                reason = error_msg.split("revert:")[1].strip()
            
            logger.warning(f"Transaction would revert: {reason}")
            return False, f"Transaction would revert: {reason}"
        
        logger.warning(f"Transaction simulation failed: {error_msg}")
        return False, f"Transaction simulation failed: {error_msg}"

async def build_contract_transaction(
    contract,
    function_name: str,
    *args,
    gas_price: Optional[int] = None,
    gas_limit: Optional[int] = None,
    nonce: Optional[int] = None,
    from_address: Optional[str] = None,
    value: int = 0,
    gas_strategy: str = "balanced"
) -> Dict[str, Any]:
    """
    Build a contract function transaction
    
    Args:
        contract: Web3 contract instance
        function_name: Contract function name
        *args: Function arguments
        gas_price: Gas price in wei
        gas_limit: Gas limit
        nonce: Transaction nonce
        from_address: Sender address
        value: Transaction value in wei
        gas_strategy: Gas price strategy
        
    Returns:
        Transaction dictionary
    """
    # Get Web3 instance from contract
    w3 = contract.web3
    
    # Get function
    if not hasattr(contract.functions, function_name):
        raise ValueError(f"Function {function_name} not found in contract")
    
    contract_function = getattr(contract.functions, function_name)
    
    # Build function call
    function_call = contract_function(*args)
    
    # Get from_address if not provided
    if not from_address:
        from_address = w3.eth.default_account
        if not from_address:
            raise ValueError("from_address not provided and defaultAccount not set")
    else:
        from_address = w3.to_checksum_address(from_address)
    
    # Get optimal gas price if not provided
    if not gas_price:
        gas_price = await get_optimal_gas_price(w3, gas_strategy)
    
    # Get nonce if not provided
    if nonce is None:
        nonce = w3.eth.get_transaction_count(from_address)
    
    # Build transaction
    tx_params = {
        'from': from_address,
        'gasPrice': gas_price,
        'nonce': nonce,
        'value': value
    }
    
    # Add gas limit if provided
    if gas_limit:
        tx_params['gas'] = gas_limit
    
    # Build transaction
    return function_call.build_transaction(tx_params)