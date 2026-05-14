"""L7 ingestion service entrypoint.

Pulls buffered L7 events from the in-cluster collector, enriches them
with analysis metadata, and publishes to RabbitMQ for downstream processing.
"""

import logging
import os
import signal

from app.config import settings
from app.grpc_server import serve_grpc
from app.kubeconfig_manager import cleanup_stale_temp_files

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Pika is verbose at INFO: it logs every connection-workflow step and emits
# a full ERROR + traceback on RabbitMQ heartbeat-driven disconnects, even
# though our publisher already detects the lost connection and reconnects
# transparently in `rabbitmq_client._publish_exchange`. Bumping these
# loggers to WARNING removes the duplicate noise — our own
# `l7_rabbitmq_publish_retry` warning is the source of truth for operators.
for _pika_logger in ("pika", "pika.adapters", "pika.connection",
                     "pika.adapters.utils.io_services_utils",
                     "pika.adapters.utils.connection_workflow",
                     "pika.adapters.blocking_connection",
                     "pika.adapters.base_connection"):
    logging.getLogger(_pika_logger).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    cleanup_stale_temp_files()
    logger.info(
        "starting l7-ingestion-service grpc_port=%s redis=%s:%s",
        settings.grpc_port,
        settings.redis_host,
        settings.redis_port,
    )
    server, servicer = serve_grpc()

    def _stop(*_args):
        logger.info("shutdown signal received — draining sessions")
        server.stop(grace=10)
        if servicer and hasattr(servicer, "_publisher") and servicer._publisher:
            servicer._publisher.close()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    server.wait_for_termination()


if __name__ == "__main__":
    main()
