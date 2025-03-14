#!/usr/bin/env python3
"""
404Bot v2 - Main Entry Point
Initializes and runs the 404Bot with configured strategies
"""

import os
import sys
import asyncio
import signal
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent))

from core.bot import Bot404
from utils.logger import setup_logger

# Initialize logger
logger = setup_logger("Main")

# Global bot instance for graceful shutdown
bot_instance = None

async def main():
    """Main function to run the bot"""
    global bot_instance
    
    # Load environment variables
    load_dotenv()
    
    logger.info("Starting 404Bot v2...")
    
    try:
        # Create bot instance
        bot_instance = Bot404()
        
        # Initialize bot
        await bot_instance.initialize()
        
        # Start bot
        await bot_instance.start()
        
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")
    finally:
        # Shutdown bot gracefully
        if bot_instance:
            await bot_instance.shutdown()
        
        logger.info("Bot shutdown complete")

def signal_handler(sig, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {sig}, initiating shutdown...")
    
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Shutdown bot gracefully
    if bot_instance:
        loop.run_until_complete(bot_instance.shutdown())
    
    logger.info("Bot shutdown complete")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the bot
    asyncio.run(main())
