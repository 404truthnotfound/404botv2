"""
Web3 Provider Module
Manages Web3 connections to Ethereum and other EVM-compatible chains
"""

import time
import json
import asyncio
from web3 import Web3, HTTPProvider, WebsocketProvider
from typing import Dict, Optional, Any, List

from utils.logger import setup_logger
from utils.config import load_config

# Initialize logger
logger = setup_logger("Web3Provider")

class Web3Provider:
    """Manages Web3 connections and provides Web3 instances"""
    
    def __init__(self):
        """Initialize Web3 provider"""
        self.config = load_config()
        self.providers = {}
        self.health_checks = {}
        self.last_block = {}
        self.monitoring_task = None
        self.is_monitoring = False
    
    async def initialize(self):
        """Initialize Web3 connections"""
        logger.info("Initializing Web3 connections")
        
        # Main provider (from config)
        main_url = self.config.WEB3_PROVIDER_URL
        if main_url:
            await self.add_provider("main", main_url)
        
        # Additional providers if configured
        fallback_urls = getattr(self.config, "FALLBACK_PROVIDER_URLS", [])
        for i, url in enumerate(fallback_urls):
            await self.add_provider(f"fallback_{i}", url)
        
        # Start health monitoring
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self.monitor_health())
        
        logger.info(f"Initialized {len(self.providers)} Web3 connections")
    
    async def shutdown(self):
        """Shutdown Web3 connections"""
        logger.info("Shutting down Web3 connections")
        
        # Stop health monitoring
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Close websocket connections
        for name, provider in self.providers.items():
            if isinstance(provider._provider, WebsocketProvider):
                await asyncio.to_thread(provider._provider.disconnect)
        
        self.providers = {}
        logger.info("Web3 connections shut down")
    
    async def add_provider(self, name: str, provider_url: str) -> bool:
        """
        Add a new Web3 provider
        
        Args:
            name: Provider name
            provider_url: Provider URL
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create provider based on URL type
            if provider_url.startswith("ws"):
                provider = Web3(WebsocketProvider(provider_url))
            else:
                provider = Web3(HTTPProvider(provider_url))
            
            # Test connection
            is_connected = await asyncio.to_thread(provider.is_connected)
            if not is_connected:
                logger.error(f"Could not connect to Web3 provider {name} at {provider_url}")
                return False
            
            # Get current block number
            block_number = await asyncio.to_thread(provider.eth.block_number)
            logger.info(f"Connected to Web3 provider {name} at block #{block_number}")
            
            # Store provider
            self.providers[name] = provider
            self.health_checks[name] = {
                "url": provider_url,
                "last_check": time.time(),
                "is_healthy": True,
                "failures": 0,
                "latency": 0
            }
            self.last_block[name] = block_number
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding Web3 provider {name}: {str(e)}")
            return False
    
    async def get_provider(self, name: str = None) -> Optional[Web3]:
        """
        Get a Web3 provider by name or the best available provider
        
        Args:
            name: Provider name (optional)
            
        Returns:
            Web3 instance or None if no healthy provider
        """
        # Return specific provider if requested
        if name and name in self.providers:
            return self.providers[name]
        
        # Return best available provider
        healthy_providers = [
            name for name, check in self.health_checks.items()
            if check["is_healthy"]
        ]
        
        if not healthy_providers:
            # If no healthy providers, try the main one anyway
            if "main" in self.providers:
                return self.providers["main"]
            # Or return any provider
            if self.providers:
                return next(iter(self.providers.values()))
            return None
        
        # Return the provider with the lowest latency
        best_provider = min(
            healthy_providers,
            key=lambda name: self.health_checks[name]["latency"] if self.health_checks[name]["latency"] > 0 else float('inf')
        )
        
        return self.providers[best_provider]
    
    async def monitor_health(self):
        """Monitor the health of all Web3 providers"""
        logger.info("Starting Web3 provider health monitoring")
        
        while self.is_monitoring:
            try:
                for name, provider in list(self.providers.items()):
                    await self.check_provider_health(name, provider)
                
                # Log health status periodically
                logger.debug(f"Web3 provider health: " + 
                         ", ".join([
                             f"{name}: {'✓' if check['is_healthy'] else '✗'} ({check['latency']:.0f}ms)"
                             for name, check in self.health_checks.items()
                         ]))
                
                # Sleep before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Web3 provider health monitoring: {str(e)}")
                await asyncio.sleep(10)
    
    async def check_provider_health(self, name: str, provider: Web3):
        """
        Check the health of a Web3 provider
        
        Args:
            name: Provider name
            provider: Web3 instance
        """
        start_time = time.time()
        try:
            # Check if connected
            is_connected = await asyncio.to_thread(provider.is_connected)
            if not is_connected:
                raise Exception("Provider not connected")
            
            # Check block number
            block_number = await asyncio.to_thread(provider.eth.block_number)
            
            # Check if block number is advancing
            last_block = self.last_block.get(name, 0)
            if block_number < last_block:
                logger.warning(f"Web3 provider {name} returned decreasing block number: {last_block} -> {block_number}")
            
            # Update last block
            self.last_block[name] = block_number
            
            # Calculate latency
            latency = (time.time() - start_time) * 1000  # in milliseconds
            
            # Update health check
            self.health_checks[name].update({
                "last_check": time.time(),
                "is_healthy": True,
                "failures": 0,
                "latency": latency
            })
            
        except Exception as e:
            # Update health check
            failures = self.health_checks[name]["failures"] + 1
            is_healthy = failures < 3  # Consider unhealthy after 3 consecutive failures
            
            self.health_checks[name].update({
                "last_check": time.time(),
                "is_healthy": is_healthy,
                "failures": failures,
            })
            
            if not is_healthy:
                logger.warning(f"Web3 provider {name} is unhealthy: {str(e)}")
    
    async def get_eth_price(self) -> float:
        """
        Get current ETH price in USD (simplified implementation)
        
        Returns:
            ETH price in USD
        """
        try:
            # In a real implementation, this would query a price oracle
            # For now, return a hardcoded price
            return 3000.0
        except Exception as e:
            logger.error(f"Error getting ETH price: {str(e)}")
            return 3000.0  # Fallback value

# Singleton instance
_provider = None

async def get_web3_provider() -> Web3Provider:
    """
    Get the singleton Web3Provider instance
    
    Returns:
        Web3Provider instance
    """
    global _provider
    if _provider is None:
        _provider = Web3Provider()
        await _provider.initialize()
    return _provider

async def get_web3(name: str = None) -> Optional[Web3]:
    """
    Get a Web3 instance
    
    Args:
        name: Provider name (optional)
        
    Returns:
        Web3 instance
    """
    provider = await get_web3_provider()
    return await provider.get_provider(name)