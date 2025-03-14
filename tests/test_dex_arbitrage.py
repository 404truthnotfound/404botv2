"""
Test DEX Arbitrage Strategy
Tests the functionality of the DEX arbitrage strategy
"""

import os
import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from strategies.dex_arbitrage import DEXArbitrageStrategy
from utils.logger import setup_logger

# Set up logger
logger = setup_logger("TestDEXArbitrage")

class TestDEXArbitrageStrategy(unittest.TestCase):
    """Test cases for DEX arbitrage strategy"""
    
    def setUp(self):
        """Set up test environment"""
        # Load environment variables
        load_dotenv()
        
        # Mock dependencies
        self.web3_provider = "http://localhost:8545"  # Use local node for testing
        self.private_key = os.getenv("TEST_PRIVATE_KEY", "0x0000000000000000000000000000000000000000000000000000000000000001")
        self.event_bus = MagicMock()
        self.gas_price_optimizer = MagicMock()
        self.profit_predictor = MagicMock()
        self.contract_loader = MagicMock()
        
        # Create strategy instance
        self.strategy = DEXArbitrageStrategy(
            web3_provider=self.web3_provider,
            private_key=self.private_key,
            event_bus=self.event_bus,
            gas_price_optimizer=self.gas_price_optimizer,
            profit_predictor=self.profit_predictor,
            contract_loader=self.contract_loader
        )
    
    @patch('strategies.dex_arbitrage.Web3')
    async def test_scan_opportunities(self, mock_web3):
        """Test scanning for arbitrage opportunities"""
        # Mock Web3 instance
        mock_web3_instance = MagicMock()
        mock_web3.return_value = mock_web3_instance
        
        # Mock contract instances
        mock_uniswap = MagicMock()
        mock_sushiswap = MagicMock()
        
        # Mock contract loader
        self.contract_loader.get_contract.side_effect = lambda address: {
            self.strategy.uniswap_router: mock_uniswap,
            self.strategy.sushiswap_router: mock_sushiswap
        }.get(address)
        
        # Mock price quotes
        mock_uniswap.functions.getAmountsOut.return_value.call.return_value = [1000000000000000000, 2000000000]
        mock_sushiswap.functions.getAmountsOut.return_value.call.return_value = [1000000000000000000, 1900000000]
        
        # Run scan
        opportunities = await self.strategy._scan_opportunities()
        
        # Assert opportunities were found
        self.assertTrue(len(opportunities) > 0)
        
        # Verify contract calls
        mock_uniswap.functions.getAmountsOut.assert_called()
        mock_sushiswap.functions.getAmountsOut.assert_called()
    
    @patch('strategies.dex_arbitrage.Web3')
    async def test_validate_opportunity(self, mock_web3):
        """Test validating arbitrage opportunities"""
        # Mock Web3 instance
        mock_web3_instance = MagicMock()
        mock_web3.return_value = mock_web3_instance
        
        # Mock opportunity
        opportunity = {
            'token_address': '0x6B175474E89094C44Da98b954EedeAC495271d0F',  # DAI
            'amount': 1000000000000000000,  # 1 ETH
            'source_router': self.strategy.uniswap_router,
            'target_router': self.strategy.sushiswap_router,
            'source_price': 2000,
            'target_price': 2100,
            'profit_percentage': 5.0
        }
        
        # Mock gas price
        self.gas_price_optimizer.return_value = 50000000000  # 50 Gwei
        
        # Mock profitability
        self.profit_predictor.predict_profitability.return_value = True
        
        # Run validation
        is_valid = await self.strategy._validate_opportunity(opportunity)
        
        # Assert validation result
        self.assertTrue(is_valid)
        
        # Verify profit prediction was called
        self.profit_predictor.predict_profitability.assert_called_once()

def run_tests():
    """Run test cases"""
    unittest.main()

if __name__ == "__main__":
    run_tests()
