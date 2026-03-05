"""RabbitMQ Consumer for ClickHouse Writer"""

import json
import logging
import time
import threading
from typing import List, Dict, Any
import pika
from pika.exceptions import AMQPConnectionError

from app.config import settings
from app.clickhouse_client import ClickHouseWriter
from app.deleted_analysis_cache import deleted_analysis_cache

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """RabbitMQ consumer with batch processing"""
    
    def __init__(self, queue_name: str, event_type: str):
        self.queue_name = queue_name
        self.event_type = event_type
        self.connection = None
        self.channel = None
        self.running = False
        self.thread = None
        
        # Batch
        self.batch: List[Dict[str, Any]] = []
        self.batch_tags: List[int] = []
        self.last_flush = time.time()
        
        # ClickHouse client
        self.clickhouse = ClickHouseWriter()
        
        # Statistics
        self.total_consumed = 0
        self.total_written = 0
        self.total_batches = 0
        self.failed_writes = 0
        
        logger.info(f"Consumer initialized for queue: {queue_name}")
    
    def _connect(self):
        """Connect to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(
                settings.rabbitmq_user,
                settings.rabbitmq_password
            )
            
            parameters = pika.ConnectionParameters(
                host=settings.rabbitmq_host,
                port=settings.rabbitmq_port,
                virtual_host=settings.rabbitmq_vhost,
                credentials=credentials,
                # Balanced connection parameters for high-throughput scenarios:
                # - heartbeat=60s: Faster failure detection without excessive overhead
                # - blocked_connection_timeout=120s: Tolerant of temporary flow control under load
                #   (30s was too aggressive - could cause disconnects during traffic spikes)
                heartbeat=60,                     # 600 -> 60s for faster failure detection
                blocked_connection_timeout=120,   # 300 -> 120s (balanced, not too aggressive)
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Set QoS
            self.channel.basic_qos(prefetch_count=settings.prefetch_count)
            
            # Declare queue with same arguments as ingestion-service
            # Special handling for change_events queue (with DLQ routing)
            if 'change_events' in self.queue_name:
                queue_args = {
                    "x-message-ttl": 86400000,  # 24 hours in ms
                    "x-max-length": 1000000,    # 1M messages
                    "x-dead-letter-exchange": "flowfish.dlx",
                    "x-dead-letter-routing-key": "change_events",
                }
            else:
                queue_args = {
                    "x-message-ttl": 86400000,  # 24 hours in ms
                    "x-max-length": 1000000     # 1M messages (same as ingestion-service)
                }
            
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments=queue_args
            )
            
            # Special handling for change_events: bind to the flowfish.change_events exchange
            if 'change_events' in self.queue_name:
                # Declare the exchange (idempotent)
                change_events_exchange = "flowfish.change_events"
                self.channel.exchange_declare(
                    exchange=change_events_exchange,
                    exchange_type='topic',
                    durable=True
                )
                
                # Bind queue to exchange
                # Routing key 'change' matches what the publisher uses
                self.channel.queue_bind(
                    queue=self.queue_name,
                    exchange=change_events_exchange,
                    routing_key="change"
                )
                logger.info(f"📢 Queue {self.queue_name} bound to exchange {change_events_exchange}")
            
            logger.info(f"✅ Connected to RabbitMQ at {settings.rabbitmq_host}:{settings.rabbitmq_port}")
            
        except AMQPConnectionError as e:
            logger.error(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    def start(self):
        """Start consumer in background thread"""
        self.running = True
        self.thread = threading.Thread(target=self._consume, daemon=True)
        self.thread.start()
        logger.info(f"Consumer started for {self.queue_name}")
    
    def stop(self):
        """Stop consumer"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=15)
        if self.connection and not self.connection.is_closed:
            # Flush remaining batch
            self._flush_batch()
            self.connection.close()
        logger.info(f"Consumer stopped for {self.queue_name}")
    
    def _consume(self):
        """Main consume loop"""
        try:
            self._connect()
            
            # Start consuming
            for method, properties, body in self.channel.consume(
                queue=self.queue_name,
                auto_ack=False
            ):
                if not self.running:
                    break
                
                try:
                    # Parse message
                    message = json.loads(body)
                    
                    # Check if analysis has been deleted - skip orphan data
                    analysis_id = message.get('analysis_id')
                    if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
                        logger.debug(f"Skipping event for deleted analysis {analysis_id}")
                        # ACK to remove from queue without processing
                        self.channel.basic_ack(delivery_tag=method.delivery_tag)
                        continue
                    
                    # Add to batch
                    self.batch.append(message)
                    self.batch_tags.append(method.delivery_tag)
                    self.total_consumed += 1
                    
                    # Check if should flush
                    if self._should_flush():
                        self._flush_batch()
                
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON message: {e}")
                    # NACK and discard
                    self.channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # NACK with requeue
                    self.channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            # Try to reconnect
            time.sleep(5)
            if self.running:
                self._consume()
    
    def _should_flush(self) -> bool:
        """Check if batch should be flushed"""
        return (
            len(self.batch) >= settings.batch_size or
            time.time() - self.last_flush >= settings.batch_timeout
        )
    
    def _flush_batch(self):
        """Flush batch to ClickHouse with timeout protection
        
        This method includes timing metrics to detect slow writes that could
        cause RabbitMQ consumer timeout issues (30 minute ack timeout).
        """
        if not self.batch:
            return
        
        # Maximum time allowed for a flush operation (in seconds)
        # If exceeded, we log a warning but still complete the write
        MAX_FLUSH_TIME_WARNING = 30
        flush_start = time.time()
        batch_size = len(self.batch)
        
        try:
            # Write to ClickHouse based on event type
            if self.event_type == "network_flow":
                rows_written = self.clickhouse.write_network_flows(self.batch)
            elif self.event_type == "dns_query":
                rows_written = self.clickhouse.write_dns_queries(self.batch)
            elif self.event_type == "tcp_connection":
                rows_written = self.clickhouse.write_tcp_connections(self.batch)
            elif self.event_type == "process_event":
                rows_written = self.clickhouse.write_process_events(self.batch)
            elif self.event_type == "file_event":
                rows_written = self.clickhouse.write_file_events(self.batch)
            elif self.event_type == "security_event":
                rows_written = self.clickhouse.write_security_events(self.batch)
            elif self.event_type == "oom_event":
                rows_written = self.clickhouse.write_oom_events(self.batch)
            elif self.event_type == "bind_event":
                rows_written = self.clickhouse.write_bind_events(self.batch)
            elif self.event_type == "sni_event":
                rows_written = self.clickhouse.write_sni_events(self.batch)
            elif self.event_type == "mount_event":
                rows_written = self.clickhouse.write_mount_events(self.batch)
            elif self.event_type == "workload_metadata":
                rows_written = self.clickhouse.write_workload_metadata(self.batch)
            elif self.event_type == "change_event":
                rows_written = self.clickhouse.write_change_events(self.batch)
            else:
                logger.warning(f"Unknown event type: {self.event_type}")
                rows_written = 0
            
            # Calculate flush duration and check for slow writes
            flush_duration = time.time() - flush_start
            
            # ACK all messages immediately after successful write
            if self.batch_tags:
                self.channel.basic_ack(delivery_tag=self.batch_tags[-1], multiple=True)
            
            # Update statistics
            self.total_written += rows_written
            self.total_batches += 1
            
            # Log with timing info
            if flush_duration > MAX_FLUSH_TIME_WARNING:
                logger.warning(
                    f"⚠️ Slow flush detected: {batch_size} messages → {rows_written} rows "
                    f"in {flush_duration:.2f}s (threshold: {MAX_FLUSH_TIME_WARNING}s) "
                    f"(Total: {self.total_written} rows, {self.total_batches} batches)"
                )
            else:
                logger.info(
                    f"📊 Flushed batch: {batch_size} messages → {rows_written} rows "
                    f"in {flush_duration:.2f}s "
                    f"(Total: {self.total_written} rows, {self.total_batches} batches)"
                )
            
            # Clear batch
            self.batch.clear()
            self.batch_tags.clear()
            self.last_flush = time.time()
            
        except Exception as e:
            flush_duration = time.time() - flush_start
            logger.error(f"Failed to flush batch after {flush_duration:.2f}s: {e}")
            self.failed_writes += 1
            
            # NACK all with requeue
            if self.batch_tags:
                self.channel.basic_nack(delivery_tag=self.batch_tags[-1], multiple=True, requeue=True)
            
            # Clear batch
            self.batch.clear()
            self.batch_tags.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics"""
        return {
            "queue_name": self.queue_name,
            "event_type": self.event_type,
            "total_consumed": self.total_consumed,
            "total_written": self.total_written,
            "total_batches": self.total_batches,
            "failed_writes": self.failed_writes,
            "current_batch_size": len(self.batch),
        }

