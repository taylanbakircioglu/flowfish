"""RabbitMQ Client for publishing messages

Supports all Inspektor Gadget v0.46.0+ event types:
- network_flow (trace_network, trace_tcpconnect, trace_tcpretrans)
- dns_query (trace_dns)
- tcp_connection (trace_tcp)
- process_event (trace_exec, trace_signal)
- file_event (trace_open, trace_write, trace_fsslower)
- security_event (trace_capabilities, seccomp)
- oom_event (trace_oomkill)
- bind_event (trace_bind)
- sni_event (trace_sni) - TLS/SSL SNI tracking
- mount_event (trace_mount) - Mount operations
"""

import json
import logging
import asyncio
import threading
import time
from typing import Dict, Any
import pika
from pika.exceptions import AMQPConnectionError, StreamLostError
from app.config import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """RabbitMQ Publisher for event messages with async support
    
    Thread-safe publisher using threading.Lock for blocking connection protection.
    """
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self._async_lock = asyncio.Lock()
        self._thread_lock = threading.Lock()  # Protects blocking connection across threads
        self._closing = False  # Flag to prevent publishes during shutdown
        self._pending_count = 0  # Track in-flight messages
        self._connect()
    
    def _connect(self):
        """Establish connection to RabbitMQ (initial connection with lock)"""
        with self._thread_lock:
            self._connect_internal()
    
    def _connect_internal(self):
        """Internal connection logic (caller must hold _thread_lock)"""
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
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare exchanges (idempotent)
            self._declare_exchanges()
            
            logger.info(
                f"✅ Connected to RabbitMQ at {settings.rabbitmq_host}:{settings.rabbitmq_port}"
            )
            
        except AMQPConnectionError as e:
            logger.error(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    def _declare_dlx(self):
        """Declare Dead Letter Exchange and Queue for failed messages"""
        try:
            # Dead Letter Exchange
            self.channel.exchange_declare(
                exchange='flowfish.dlx',
                exchange_type='direct',
                durable=True
            )
            logger.info("Dead Letter Exchange declared: flowfish.dlx")
            
            # Dead Letter Queue for change_events (7 day retention)
            self.channel.queue_declare(
                queue='flowfish.queue.change_events.dlq',
                durable=True,
                arguments={
                    'x-message-ttl': 604800000,  # 7 days
                }
            )
            
            # Bind DLQ to DLX
            self.channel.queue_bind(
                queue='flowfish.queue.change_events.dlq',
                exchange='flowfish.dlx',
                routing_key='change_events'
            )
            logger.info("Dead Letter Queue bound: flowfish.queue.change_events.dlq -> flowfish.dlx")
        except Exception as e:
            logger.warning(f"Failed to declare DLX (may already exist): {e}")
    
    def _declare_exchanges(self):
        """Declare exchanges and queues for all event types (idempotent)"""
        # Define exchanges and their bound queues
        # Format: exchange -> [(queue_name, routing_key), ...]
        exchange_queue_mappings = {
            # Network events - go to both timeseries and graph
            settings.exchange_network_flows: [
                ("flowfish.queue.network_flows.timeseries", "flow"),
                ("flowfish.queue.network_flows.graph", "flow"),
            ],
            # DNS events - go to both timeseries and graph
            settings.exchange_dns_queries: [
                ("flowfish.queue.dns_queries.timeseries", "dns"),
                ("flowfish.queue.dns_queries.graph", "dns"),
            ],
            # TCP events - go to both timeseries and graph
            settings.exchange_tcp_connections: [
                ("flowfish.queue.tcp_connections.timeseries", "tcp"),
                ("flowfish.queue.tcp_connections.graph", "tcp"),
            ],
            # Process events - timeseries only (not relevant for communication graph)
            settings.exchange_process_events: [
                ("flowfish.queue.process_events.timeseries", "process"),
            ],
            # File events - timeseries only
            settings.exchange_file_events: [
                ("flowfish.queue.file_events.timeseries", "file"),
            ],
            # Security events - timeseries only
            settings.exchange_security_events: [
                ("flowfish.queue.security_events.timeseries", "security"),
            ],
            # OOM events - timeseries only
            settings.exchange_oom_events: [
                ("flowfish.queue.oom_events.timeseries", "oom"),
            ],
            # Bind events - timeseries and graph (for service discovery)
            settings.exchange_bind_events: [
                ("flowfish.queue.bind_events.timeseries", "bind"),
                ("flowfish.queue.bind_events.graph", "bind"),
            ],
            # SNI events - timeseries and graph (for TLS/HTTPS connections)
            settings.exchange_sni_events: [
                ("flowfish.queue.sni_events.timeseries", "sni"),
                ("flowfish.queue.sni_events.graph", "sni"),
            ],
            # Mount events - timeseries only
            settings.exchange_mount_events: [
                ("flowfish.queue.mount_events.timeseries", "mount"),
            ],
            # Workload metadata - timeseries only (for IP -> Pod name lookups)
            settings.exchange_workload_metadata: [
                ("flowfish.queue.workload_metadata.timeseries", "metadata"),
            ],
            # Change events - published by Change Detection Worker, consumed by Timeseries Writer
            settings.exchange_change_events: [
                ("flowfish.queue.change_events.timeseries", "change"),
            ],
        }
        
        # Declare Dead Letter Exchange for failed messages
        self._declare_dlx()
        
        for exchange, queues in exchange_queue_mappings.items():
            # Declare exchange
            self.channel.exchange_declare(
                exchange=exchange,
                exchange_type='topic',
                durable=True
            )
            logger.info(f"Exchange declared: {exchange}")
            
            # Declare and bind queues
            for queue_name, routing_key in queues:
                # Special arguments for change_events queue (with DLQ routing)
                if 'change_events' in queue_name:
                    queue_args = {
                        'x-message-ttl': 86400000,  # 24 hours
                        'x-max-length': 1000000,    # Max 1M messages
                        'x-dead-letter-exchange': 'flowfish.dlx',
                        'x-dead-letter-routing-key': 'change_events',
                    }
                else:
                    queue_args = {
                        'x-message-ttl': 86400000,  # 24 hours
                        'x-max-length': 1000000,    # Max 1M messages
                    }
                
                self.channel.queue_declare(
                    queue=queue_name,
                    durable=True,
                    arguments=queue_args
                )
                
                self.channel.queue_bind(
                    queue=queue_name,
                    exchange=exchange,
                    routing_key=routing_key
                )
                logger.info(f"Queue bound: {queue_name} -> {exchange} (routing_key={routing_key})")
    
    def _sync_publish(self, exchange: str, message: Dict[str, Any], routing_key: str = ''):
        """
        Synchronous publish to exchange (internal use)
        
        Thread-safe with retry logic for transient connection errors.
        """
        # Skip if we're closing
        if self._closing:
            logger.debug(f"Skipping publish during shutdown: {exchange}")
            return
        
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                with self._thread_lock:
                    # Double-check closing flag inside lock
                    if self._closing:
                        logger.debug(f"Skipping publish during shutdown: {exchange}")
                        return
                    
                    # Check connection state
                    if not self.connection or self.connection.is_closed:
                        logger.warning("Connection lost, reconnecting...")
                        self._connect_internal()
                    
                    if not self.channel or self.channel.is_closed:
                        logger.warning("Channel lost, recreating...")
                        self.channel = self.connection.channel()
                    
                    self._pending_count += 1
                    try:
                        body = json.dumps(message, default=str)
                        
                        self.channel.basic_publish(
                            exchange=exchange,
                            routing_key=routing_key,
                            body=body,
                            properties=pika.BasicProperties(
                                delivery_mode=2,  # persistent
                                content_type='application/json',
                            )
                        )
                        
                        logger.debug(f"Published to {exchange}: {message.get('event_type')}")
                        return  # Success
                        
                    finally:
                        self._pending_count -= 1
                        
            except (StreamLostError, AMQPConnectionError) as e:
                logger.warning(f"Connection error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    # Force reconnect on next attempt
                    with self._thread_lock:
                        if self.connection and not self.connection.is_closed:
                            try:
                                self.connection.close()
                            except Exception:
                                pass
                        self.connection = None
                        self.channel = None
                else:
                    logger.error(f"Failed to publish after {max_retries} attempts: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to publish message: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise
    
    async def publish(self, exchange: str, message: Dict[str, Any], routing_key: str = ''):
        """
        Async publish message to exchange
        
        Uses asyncio.to_thread to run blocking pika publish in thread pool.
        The thread lock inside _sync_publish ensures thread-safety.
        
        Args:
            exchange: Exchange name
            message: Message dict (will be JSON serialized)
            routing_key: Routing key (default: '')
        """
        if self._closing:
            return
        
        # Use asyncio lock to limit concurrent to_thread calls (reduces thread pool pressure)
        async with self._async_lock:
            await asyncio.to_thread(self._sync_publish, exchange, message, routing_key)
    
    def publish_sync(self, exchange: str, message: Dict[str, Any], routing_key: str = ''):
        """
        Synchronous publish (for non-async contexts)
        """
        self._sync_publish(exchange, message, routing_key)
    
    async def publish_network_flow(self, message: Dict[str, Any]):
        """Publish network flow event"""
        await self.publish(settings.exchange_network_flows, message, routing_key="flow")
    
    async def publish_dns_query(self, message: Dict[str, Any]):
        """Publish DNS query event"""
        await self.publish(settings.exchange_dns_queries, message, routing_key="dns")
    
    async def publish_tcp_connection(self, message: Dict[str, Any]):
        """Publish TCP connection event"""
        await self.publish(settings.exchange_tcp_connections, message, routing_key="tcp")
    
    async def publish_process_event(self, message: Dict[str, Any]):
        """Publish process event (exec, exit, signal)"""
        await self.publish(settings.exchange_process_events, message, routing_key="process")
    
    async def publish_file_event(self, message: Dict[str, Any]):
        """Publish file event (open, read, write, close)"""
        await self.publish(settings.exchange_file_events, message, routing_key="file")
    
    async def publish_security_event(self, message: Dict[str, Any]):
        """Publish security event (capability check, seccomp)"""
        await self.publish(settings.exchange_security_events, message, routing_key="security")
    
    async def publish_oom_event(self, message: Dict[str, Any]):
        """Publish OOM kill event"""
        await self.publish(settings.exchange_oom_events, message, routing_key="oom")
    
    async def publish_bind_event(self, message: Dict[str, Any]):
        """Publish socket bind event"""
        await self.publish(settings.exchange_bind_events, message, routing_key="bind")
    
    async def publish_sni_event(self, message: Dict[str, Any]):
        """Publish TLS/SSL SNI event"""
        await self.publish(settings.exchange_sni_events, message, routing_key="sni")
    
    async def publish_mount_event(self, message: Dict[str, Any]):
        """Publish mount event"""
        await self.publish(settings.exchange_mount_events, message, routing_key="mount")
    
    async def publish_workload_metadata(self, message: Dict[str, Any]):
        """Publish workload/pod metadata for IP -> Pod name lookups"""
        await self.publish(settings.exchange_workload_metadata, message, routing_key="metadata")
    
    async def publish_change_event(self, message: Dict[str, Any]):
        """Publish change event (from Change Detection Worker)"""
        await self.publish(settings.exchange_change_events, message, routing_key="change")
    
    async def publish_by_event_type(self, event_type: str, message: Dict[str, Any]):
        """
        Route message to correct exchange based on event type
        
        Args:
            event_type: Event type (network_flow, dns_query, etc.)
            message: Message to publish
        """
        publishers = {
            "network_flow": self.publish_network_flow,
            "dns_query": self.publish_dns_query,
            "tcp_connection": self.publish_tcp_connection,
            "process_event": self.publish_process_event,
            "file_event": self.publish_file_event,
            "security_event": self.publish_security_event,
            "oom_event": self.publish_oom_event,
            "bind_event": self.publish_bind_event,
            "sni_event": self.publish_sni_event,
            "mount_event": self.publish_mount_event,
            "workload_metadata": self.publish_workload_metadata,
            "change_event": self.publish_change_event,
        }
        
        publisher = publishers.get(event_type)
        if publisher:
            await publisher(message)
        else:
            logger.warning(f"Unknown event type: {event_type}, routing to network_flows")
            await self.publish_network_flow(message)
    
    def close(self, timeout: float = 5.0):
        """Close connection gracefully
        
        Args:
            timeout: Max seconds to wait for pending messages
        """
        logger.info("Initiating RabbitMQ connection shutdown...")
        
        # Signal that we're closing - no new publishes
        self._closing = True
        
        # Wait for pending messages to complete
        wait_start = time.time()
        while self._pending_count > 0 and (time.time() - wait_start) < timeout:
            logger.debug(f"Waiting for {self._pending_count} pending messages...")
            time.sleep(0.1)
        
        if self._pending_count > 0:
            logger.warning(f"Closing with {self._pending_count} messages still pending")
        
        # Close connection with lock to prevent races
        with self._thread_lock:
            try:
                if self.connection and not self.connection.is_closed:
                    self.connection.close()
                    logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ connection: {e}")
            finally:
                self.connection = None
                self.channel = None

