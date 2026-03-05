"""
Flowfish Ingestion Service
Main entry point
"""

import logging
import asyncio
import signal
import sys
from app.grpc_server import serve
from app.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Main async function"""
    logger.info("🐟 Starting Flowfish Ingestion Service...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"gRPC Port: {settings.grpc_port}")
    logger.info(f"RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
    
    # Start async gRPC server
    server = await serve()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Shutting down gracefully...")
        asyncio.create_task(server.stop(grace=5))
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # Wait for termination
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Server cancelled")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")

