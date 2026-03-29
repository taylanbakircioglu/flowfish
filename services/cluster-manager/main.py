"""
Flowfish Cluster Manager Service
Main entry point
"""

import logging
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


def main():
    """Main function"""
    logger.info("🐟 Starting Flowfish Cluster Manager Service...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"gRPC Port: {settings.grpc_port}")
    logger.info(f"PostgreSQL: {settings.postgres_host}:{settings.postgres_port}")
    
    # Start gRPC server
    server = serve()
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutting down gracefully...")
        server.stop(grace=5)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        server.stop(grace=5)


if __name__ == '__main__':
    main()

