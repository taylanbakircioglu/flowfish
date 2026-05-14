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

# Pika is verbose at INFO and dumps a full ERROR traceback every time the
# broker drops an idle TCP connection — even though our publisher detects
# the disconnect and reconnects automatically. WARNING keeps real errors
# visible while suppressing the per-disconnect log storm. The same change
# is applied to l7-ingestion-service for consistency.
for _pika_logger in ("pika", "pika.adapters", "pika.connection",
                     "pika.adapters.utils.io_services_utils",
                     "pika.adapters.utils.connection_workflow",
                     "pika.adapters.blocking_connection",
                     "pika.adapters.base_connection"):
    logging.getLogger(_pika_logger).setLevel(logging.WARNING)

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

