"""
Time-Series Writer Service
Main entry point

Consumes all Inspektor Gadget event types from RabbitMQ and writes to ClickHouse.

Build: 2026-01-17
"""

import logging
import signal
import sys
import time

from app.config import settings
from app.rabbitmq_consumer import RabbitMQConsumer

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main function"""
    logger.info("🐟 Starting Time-Series Writer Service...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
    logger.info(f"Time-Series DB: {settings.clickhouse_host}:{settings.clickhouse_port}")
    logger.info(f"Batch Size: {settings.batch_size}")
    logger.info(f"Batch Timeout: {settings.batch_timeout}s")
    
    # Create consumers for each queue - ALL event types
    consumers = [
        # Core network events
        RabbitMQConsumer(settings.queue_network_flows, "network_flow"),
        RabbitMQConsumer(settings.queue_dns_queries, "dns_query"),
        RabbitMQConsumer(settings.queue_tcp_connections, "tcp_connection"),
        # Process and file events
        RabbitMQConsumer(settings.queue_process_events, "process_event"),
        RabbitMQConsumer(settings.queue_file_events, "file_event"),
        # Security events
        RabbitMQConsumer(settings.queue_security_events, "security_event"),
        RabbitMQConsumer(settings.queue_oom_events, "oom_event"),
        # Socket, TLS, and mount events
        RabbitMQConsumer(settings.queue_bind_events, "bind_event"),
        RabbitMQConsumer(settings.queue_sni_events, "sni_event"),
        RabbitMQConsumer(settings.queue_mount_events, "mount_event"),
        # Workload metadata (pod info for IP -> name lookups)
        RabbitMQConsumer(settings.queue_workload_metadata, "workload_metadata"),
    ]
    
    # Change events consumer (feature flag controlled)
    if settings.change_events_consumer_enabled:
        consumers.append(
            RabbitMQConsumer(settings.queue_change_events, "change_event")
        )
        logger.info("📢 Change events consumer ENABLED (CHANGE_EVENTS_CONSUMER_ENABLED=true)")
    else:
        logger.info("⏸️  Change events consumer DISABLED (CHANGE_EVENTS_CONSUMER_ENABLED=false)")
    
    # Start all consumers
    for consumer in consumers:
        consumer.start()
    
    logger.info(f"✅ Started {len(consumers)} consumers for all event types")
    event_types = "network_flow, dns_query, tcp_connection, process_event, file_event, security_event, oom_event, bind_event, sni_event, mount_event, workload_metadata"
    if settings.change_events_consumer_enabled:
        event_types += ", change_event"
    logger.info(f"   Event types: {event_types}")
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutting down gracefully...")
        for consumer in consumers:
            consumer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Main loop - print statistics every 30 seconds
    try:
        while True:
            time.sleep(30)
            logger.info("📊 Consumer Statistics:")
            for consumer in consumers:
                stats = consumer.get_stats()
                logger.info(
                    f"  {stats['queue_name']}: "
                    f"Consumed={stats['total_consumed']}, "
                    f"Written={stats['total_written']}, "
                    f"Batches={stats['total_batches']}, "
                    f"Failed={stats['failed_writes']}"
                )
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        for consumer in consumers:
            consumer.stop()


if __name__ == '__main__':
    main()

