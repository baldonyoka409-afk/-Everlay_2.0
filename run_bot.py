#!/usr/bin/env python
"""
Entry point to run the Telegram bot.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.logging_config import setup_logging
from core.config import get_settings
from telegram import run_bot, stop_bot


async def main():
    """Run the bot."""
    settings = get_settings()

    # Setup logging
    setup_logging(settings)

    logger = logging.getLogger(__name__)
    logger.info("Starting Everlay Telegram Bot...")

    try:
        await run_bot()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
    finally:
        await stop_bot()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())