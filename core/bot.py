#!/usr/bin/env python3
"""
404Bot v2 - Main Bot Orchestration
Coordinates all components and strategies for MEV extraction and arbitrage
"""

import os
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

# Core components
from core.config import Config
from core.event_bus import EventBus

# MEV components
from mev.mempool import MempoolMonitor
from mev.flashbots import FlashbotsManager

# Strategies
from strategies.flash_loan import FlashLoanStrategy
from strategies.dex_arbitrage import DEXArbitrageStrategy
from strategies.cross_chain_mev import CrossChainMEVStrategy
from strategies.mev_share import MEVShareStrategy
from strategies.zk_mev import ZKMEVStrategy
from strategies.advanced_flash_loan import AdvancedFlashLoanStrategy
from strategies.ai_strategy_selector import AISelectorConfig, get_best_strategy, update_performance_data

# Utilities
from utils.logger import setup_logger
from utils.gas_price import get_optimal_gas_price
from utils.performance import PerformanceTracker
from utils.profit_predictor import ProfitPredictor
from utils.contract_loader import ContractLoader

class Bot404:
    """
    Main bot class orchestrating all MEV and arbitrage strategies
    """
    
    def __init__(self):
        """Initialize the bot with all required components"""
        # Setup logging
        self.logger = setup_logger("Bot404")
        self.logger.info("Initializing 404Bot v2...")
        
        # Load configuration
        self.config = Config()
        
        # Initialize event bus for component communication
        self.event_bus = EventBus()
        
        # Initialize MEV components
        self.mempool_monitor = MempoolMonitor(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            private_key=self.config.PRIVATE_KEY,
            event_bus=self.event_bus
        )
        
        self.flashbots = FlashbotsManager(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            private_key=self.config.PRIVATE_KEY,
            event_bus=self.event_bus
        )
        
        # Initialize utilities
        self.gas_price_optimizer = get_optimal_gas_price(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            event_bus=self.event_bus
        )
        
        self.performance_tracker = PerformanceTracker(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            event_bus=self.event_bus
        )
        
        self.profit_predictor = ProfitPredictor(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            event_bus=self.event_bus
        )
        
        self.contract_loader = ContractLoader(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            event_bus=self.event_bus
        )
        
        # Initialize legacy strategies
        self.flash_loan_strategy = FlashLoanStrategy(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            private_key=self.config.PRIVATE_KEY,
            contract_address=self.config.FLASH_LOAN_CONTRACT,
            event_bus=self.event_bus,
            gas_price_optimizer=self.gas_price_optimizer,
            profit_predictor=self.profit_predictor,
            contract_loader=self.contract_loader
        )
        
        self.dex_arbitrage_strategy = DEXArbitrageStrategy(
            web3_provider=self.config.WEB3_PROVIDER_URL,
            private_key=self.config.PRIVATE_KEY,
            event_bus=self.event_bus,
            gas_price_optimizer=self.gas_price_optimizer,
            profit_predictor=self.profit_predictor,
            contract_loader=self.contract_loader
        )
        
        # Initialize advanced MEV strategies (2025)
        self.logger.info("Initializing advanced MEV strategies (2025)...")
        
        # Cross-Chain MEV Strategy
        self.cross_chain_mev_strategy = CrossChainMEVStrategy(
            config=self.config.as_dict(),
            event_bus=self.event_bus,
            performance_tracker=self.performance_tracker
        )
        
        # MEV Share Strategy
        self.mev_share_strategy = MEVShareStrategy(
            config=self.config.as_dict(),
            event_bus=self.event_bus,
            performance_tracker=self.performance_tracker
        )
        
        # ZK MEV Strategy
        self.zk_mev_strategy = ZKMEVStrategy(
            config=self.config.as_dict(),
            event_bus=self.event_bus,
            performance_tracker=self.performance_tracker
        )
        
        # Advanced Flash Loan Strategy
        self.advanced_flash_loan_strategy = AdvancedFlashLoanStrategy(
            config=self.config.as_dict(),
            event_bus=self.event_bus,
            performance_tracker=self.performance_tracker
        )
        
        # AI Strategy Selector Configuration
        self.ai_selector_config = AISelectorConfig(
            strategy_whitelist=[
                "flash_loan",
                "dex_arbitrage",
                "cross_chain_mev",
                "mev_share",
                "zk_mev",
                "advanced_flash_loan"
            ],
            strategy_config=self.config.as_dict(),
            performance_window=self.config.PERFORMANCE_WINDOW,
            performance_threshold=self.config.MIN_PROFIT_THRESHOLD
        )
        
        # Strategy mapping for dynamic selection
        self.strategies = {
            "flash_loan": self.flash_loan_strategy,
            "dex_arbitrage": self.dex_arbitrage_strategy,
            "cross_chain_mev": self.cross_chain_mev_strategy,
            "mev_share": self.mev_share_strategy,
            "zk_mev": self.zk_mev_strategy,
            "advanced_flash_loan": self.advanced_flash_loan_strategy
        }
        
        # Current active strategy (will be selected by AI)
        self.active_strategy = None
        
        # Running state
        self.running = False
        self.tasks = []
        
        # Performance metrics
        self.start_time = None
        self.trades_executed = 0
        self.profitable_trades = 0
        self.total_profit = 0
        
        self.logger.info("404Bot v2 initialized successfully")
    
    async def start(self):
        """Start the bot and all its components"""
        self.logger.info("Starting 404Bot v2...")
        self.running = True
        self.start_time = time.time()
        
        # Register event handlers
        self._register_event_handlers()
        
        # Start MEV components
        self.tasks.append(asyncio.create_task(self.mempool_monitor.start()))
        self.tasks.append(asyncio.create_task(self.flashbots.start()))
        
        # Start utilities
        self.tasks.append(asyncio.create_task(self.gas_price_optimizer.start()))
        self.tasks.append(asyncio.create_task(self.performance_tracker.start()))
        self.tasks.append(asyncio.create_task(self.profit_predictor.start()))
        self.tasks.append(asyncio.create_task(self.contract_loader.start()))
        
        # Start legacy strategies
        self.tasks.append(asyncio.create_task(self.flash_loan_strategy.start()))
        self.tasks.append(asyncio.create_task(self.dex_arbitrage_strategy.start()))
        
        # Start advanced MEV strategies (2025)
        self.logger.info("Starting advanced MEV strategies (2025)...")
        self.tasks.append(asyncio.create_task(self.cross_chain_mev_strategy.start()))
        self.tasks.append(asyncio.create_task(self.mev_share_strategy.start()))
        self.tasks.append(asyncio.create_task(self.zk_mev_strategy.start()))
        self.tasks.append(asyncio.create_task(self.advanced_flash_loan_strategy.start()))
        
        # Start AI strategy selection task
        self.tasks.append(asyncio.create_task(self._ai_strategy_selection()))
        
        # Start monitoring tasks
        self.tasks.append(asyncio.create_task(self._monitor_performance()))
        
        self.logger.info("404Bot v2 started successfully")
    
    async def stop(self):
        """Stop the bot and all its components"""
        self.logger.info("Stopping 404Bot v2...")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Stop MEV components
        await self.mempool_monitor.stop()
        await self.flashbots.stop()
        
        # Stop utilities
        await self.gas_price_optimizer.stop()
        await self.performance_tracker.stop()
        await self.profit_predictor.stop()
        await self.contract_loader.stop()
        
        # Stop legacy strategies
        await self.flash_loan_strategy.stop()
        await self.dex_arbitrage_strategy.stop()
        
        # Stop advanced MEV strategies (2025)
        await self.cross_chain_mev_strategy.stop()
        await self.mev_share_strategy.stop()
        await self.zk_mev_strategy.stop()
        await self.advanced_flash_loan_strategy.stop()
        
        # Log performance summary
        self._log_performance_summary()
        
        self.logger.info("404Bot v2 stopped successfully")
    
    def _register_event_handlers(self):
        """Register event handlers for inter-component communication"""
        # Register for trade execution events
        self.event_bus.subscribe("trade_executed", self._on_trade_executed)
        
        # Register for error events
        self.event_bus.subscribe("error", self._on_error)
        
        # Register for opportunity events
        self.event_bus.subscribe("opportunity_found", self._on_opportunity_found)
        
        # Register for cross-chain events
        self.event_bus.subscribe("cross_chain_opportunity", self._on_cross_chain_opportunity)
        
        # Register for MEV Share events
        self.event_bus.subscribe("mev_share_bundle", self._on_mev_share_bundle)
        
        # Register for ZK MEV events
        self.event_bus.subscribe("zk_batch_opportunity", self._on_zk_batch_opportunity)
    
    async def _ai_strategy_selection(self):
        """AI-driven strategy selection based on performance"""
        while self.running:
            try:
                # Select the best strategy based on historical performance
                best_strategy_name = get_best_strategy(self.ai_selector_config)
                
                if best_strategy_name and best_strategy_name in self.strategies:
                    if self.active_strategy != self.strategies[best_strategy_name]:
                        self.active_strategy = self.strategies[best_strategy_name]
                        self.logger.info(f"AI selected new active strategy: {best_strategy_name}")
                        
                        # Notify all components about strategy change
                        self.event_bus.publish("strategy_changed", {
                            "strategy": best_strategy_name,
                            "timestamp": time.time()
                        })
                
                # Sleep for strategy selection interval
                await asyncio.sleep(self.config.STRATEGY_SELECTION_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in AI strategy selection: {str(e)}")
                await asyncio.sleep(60)
    
    async def _monitor_performance(self):
        """Monitor bot performance and log metrics"""
        while self.running:
            try:
                # Log current performance metrics every 5 minutes
                await asyncio.sleep(300)
                self._log_performance_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring: {str(e)}")
                await asyncio.sleep(60)
    
    def _log_performance_metrics(self):
        """Log current performance metrics"""
        if not self.start_time:
            return
        
        runtime = time.time() - self.start_time
        hours = runtime / 3600
        
        self.logger.info(f"Performance metrics:")
        self.logger.info(f"  Runtime: {hours:.2f} hours")
        self.logger.info(f"  Trades executed: {self.trades_executed}")
        self.logger.info(f"  Profitable trades: {self.profitable_trades}")
        self.logger.info(f"  Success rate: {(self.profitable_trades / max(1, self.trades_executed)) * 100:.2f}%")
        self.logger.info(f"  Total profit: ${self.total_profit:.2f}")
        self.logger.info(f"  Profit per hour: ${self.total_profit / max(1, hours):.2f}")
        
        # Log strategy-specific metrics
        if self.active_strategy:
            strategy_name = next((name for name, strategy in self.strategies.items() 
                                if strategy == self.active_strategy), "unknown")
            self.logger.info(f"  Current active strategy: {strategy_name}")
    
    def _log_performance_summary(self):
        """Log performance summary when bot is stopped"""
        if not self.start_time:
            return
        
        runtime = time.time() - self.start_time
        hours = runtime / 3600
        
        self.logger.info("=" * 50)
        self.logger.info("PERFORMANCE SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Total runtime: {hours:.2f} hours")
        self.logger.info(f"Total trades executed: {self.trades_executed}")
        self.logger.info(f"Profitable trades: {self.profitable_trades}")
        self.logger.info(f"Success rate: {(self.profitable_trades / max(1, self.trades_executed)) * 100:.2f}%")
        self.logger.info(f"Total profit: ${self.total_profit:.2f}")
        self.logger.info(f"Profit per hour: ${self.total_profit / max(1, hours):.2f}")
        
        # Log strategy-specific performance
        self.logger.info("-" * 50)
        self.logger.info("STRATEGY PERFORMANCE")
        for name, strategy in self.strategies.items():
            if hasattr(strategy, 'performance') and hasattr(strategy.performance, 'get_metrics'):
                metrics = strategy.performance.get_metrics()
                self.logger.info(f"  {name}:")
                self.logger.info(f"    Trades: {metrics.get('trades', 0)}")
                self.logger.info(f"    Profit: ${metrics.get('profit', 0):.2f}")
                self.logger.info(f"    Success rate: {metrics.get('success_rate', 0):.2f}%")
        
        self.logger.info("=" * 50)
    
    def _on_trade_executed(self, data):
        """Handle trade execution events"""
        self.trades_executed += 1
        
        if data.get("profit", 0) > 0:
            self.profitable_trades += 1
            self.total_profit += data.get("profit", 0)
        
        self.logger.info(f"Trade executed: {data.get('strategy')} - Profit: ${data.get('profit', 0):.2f}")
        
        # Update strategy performance data for AI selection
        strategy_name = data.get('strategy')
        if strategy_name in self.strategies:
            update_performance_data(strategy_name, data.get('profit', 0))
    
    def _on_error(self, data):
        """Handle error events"""
        self.logger.error(f"Error in {data.get('component')}: {data.get('message')}")
    
    def _on_opportunity_found(self, data):
        """Handle opportunity found events"""
        self.logger.info(f"Opportunity found: {data.get('strategy')} - Expected profit: ${data.get('expected_profit', 0):.2f}")
    
    def _on_cross_chain_opportunity(self, data):
        """Handle cross-chain opportunity events"""
        self.logger.info(f"Cross-chain opportunity found: {data.get('source_chain')} -> {data.get('target_chain')} - Expected profit: ${data.get('expected_profit', 0):.2f}")
    
    def _on_mev_share_bundle(self, data):
        """Handle MEV Share bundle events"""
        self.logger.info(f"MEV Share bundle: {data.get('bundle_id')} - Expected profit: ${data.get('expected_profit', 0):.2f} - Profit share: {data.get('profit_share', 0)}%")
    
    def _on_zk_batch_opportunity(self, data):
        """Handle ZK batch opportunity events"""
        self.logger.info(f"ZK batch opportunity on {data.get('rollup')}: {data.get('batch_size')} txs - Expected profit: ${data.get('expected_profit', 0):.2f}")


async def main():
    """Main entry point"""
    bot = Bot404()
    
    # Setup signal handlers for graceful shutdown
    try:
        await bot.start()
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down...")
    except Exception as e:
        print(f"Error in main loop: {str(e)}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())