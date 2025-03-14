"""
Contract Deployment Script
Deploys the FlashLoan contract to the Ethereum network
"""

import os
import json
import time
from web3 import Web3
from dotenv import load_dotenv
from pathlib import Path

# Add parent directory to path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("DeployContracts")

def load_contract_source(contract_name):
    """Load contract source and ABI"""
    contract_path = Path(__file__).resolve().parent.parent / "contracts" / f"{contract_name}.sol"
    abi_path = Path(__file__).resolve().parent.parent / "contracts" / "abi" / f"{contract_name}.json"
    
    if not contract_path.exists():
        raise FileNotFoundError(f"Contract source not found: {contract_path}")
    
    if not abi_path.exists():
        raise FileNotFoundError(f"Contract ABI not found: {abi_path}")
    
    with open(abi_path, 'r') as f:
        abi = json.load(f)
    
    with open(contract_path, 'r') as f:
        source = f.read()
    
    return source, abi

def deploy_flash_loan_contract(w3, private_key, aave_lending_pool, uniswap_router, sushiswap_router):
    """Deploy the FlashLoan contract"""
    logger.info("Deploying FlashLoan contract...")
    
    try:
        # Load contract ABI and bytecode
        _, abi = load_contract_source("FlashLoan")
        
        # Compile contract if needed (using solcx)
        # For simplicity, we assume the contract is already compiled and the bytecode is available
        # In a production environment, you would use solcx to compile the contract
        
        # For this example, we'll use a placeholder bytecode
        # In a real deployment, you would get this from the compilation output
        bytecode = "0x608060405234801561001057600080fd5b50..."  # Replace with actual bytecode
        
        # Create contract instance
        contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        
        # Get account from private key
        account = w3.eth.account.from_key(private_key)
        
        # Get transaction count
        nonce = w3.eth.get_transaction_count(account.address)
        
        # Estimate gas price
        gas_price = w3.eth.gas_price
        
        # Build deployment transaction
        tx = contract.constructor(
            aave_lending_pool,
            uniswap_router,
            sushiswap_router
        ).build_transaction({
            'from': account.address,
            'gas': 4000000,  # Gas limit
            'gasPrice': gas_price,
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        
        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        logger.info(f"Transaction sent: {tx_hash.hex()}")
        logger.info("Waiting for transaction receipt...")
        
        # Wait for transaction receipt
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        # Get contract address
        contract_address = tx_receipt.contractAddress
        
        logger.info(f"FlashLoan contract deployed at: {contract_address}")
        
        # Save contract address to .env file
        update_env_file("FLASH_LOAN_CONTRACT_ADDRESS", contract_address)
        
        return contract_address
        
    except Exception as e:
        logger.error(f"Error deploying FlashLoan contract: {str(e)}")
        return None

def update_env_file(key, value):
    """Update a key in the .env file"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    
    if not env_path.exists():
        logger.warning(".env file not found, creating one")
        env_path.touch()
    
    # Read current content
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Check if key exists
    key_exists = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_exists = True
            break
    
    # Add key if it doesn't exist
    if not key_exists:
        lines.append(f"{key}={value}\n")
    
    # Write updated content
    with open(env_path, 'w') as f:
        f.writelines(lines)
    
    logger.info(f"Updated {key} in .env file")

def main():
    """Main function"""
    # Load environment variables
    load_dotenv()
    
    # Get configuration from environment
    eth_node_url = os.getenv("ETH_NODE_URL")
    private_key = os.getenv("PRIVATE_KEY")
    aave_lending_pool = os.getenv("AAVE_LENDING_POOL")
    uniswap_router = os.getenv("UNISWAP_ROUTER")
    sushiswap_router = os.getenv("SUSHISWAP_ROUTER")
    
    # Validate configuration
    if not eth_node_url:
        logger.error("ETH_NODE_URL not set in .env file")
        return
    
    if not private_key:
        logger.error("PRIVATE_KEY not set in .env file")
        return
    
    if not aave_lending_pool:
        logger.error("AAVE_LENDING_POOL not set in .env file")
        return
    
    if not uniswap_router:
        logger.error("UNISWAP_ROUTER not set in .env file")
        return
    
    if not sushiswap_router:
        logger.error("SUSHISWAP_ROUTER not set in .env file")
        return
    
    # Connect to Ethereum node
    w3 = Web3(Web3.HTTPProvider(eth_node_url))
    
    # Check connection
    if not w3.is_connected():
        logger.error(f"Failed to connect to Ethereum node: {eth_node_url}")
        return
    
    logger.info(f"Connected to Ethereum node: {eth_node_url}")
    logger.info(f"Current block number: {w3.eth.block_number}")
    
    # Deploy contract
    contract_address = deploy_flash_loan_contract(
        w3,
        private_key,
        aave_lending_pool,
        uniswap_router,
        sushiswap_router
    )
    
    if contract_address:
        logger.info(f"Deployment successful! Contract address: {contract_address}")
    else:
        logger.error("Deployment failed!")

if __name__ == "__main__":
    main()
