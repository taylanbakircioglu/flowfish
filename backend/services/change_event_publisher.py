"""
Change Event Publisher for RabbitMQ
Publishes change events to RabbitMQ for consumption by Timeseries Writer

Change events are published to RabbitMQ and consumed by the timeseries-writer
service which writes them to ClickHouse. ClickHouse is the ONLY storage
for change events (PostgreSQL change_events table has been removed).
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# Lazy-loaded connection
_publisher = None
_initialized = False


class ChangeEventPublisher:
    """
    RabbitMQ Publisher for Change Events
    
    Publishes change events to the flowfish.change_events exchange.
    Messages are consumed by Timeseries Writer and stored in ClickHouse.
    
    Thread-safe with connection management.
    """
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self._connected = False
        
        # Exchange configuration
        self.exchange_name = "flowfish.change_events"
        self.routing_key = "change"
    
    def _connect(self) -> bool:
        """Establish connection to RabbitMQ"""
        try:
            import pika
            from config import settings
            
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER,
                settings.RABBITMQ_PASSWORD
            )
            
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                virtual_host=settings.RABBITMQ_VHOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare exchange (idempotent)
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )
            
            self._connected = True
            logger.info(f"Connected to RabbitMQ at {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
            return True
            
        except ImportError:
            logger.warning("pika library not installed, RabbitMQ publishing disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._connected = False
            return False
    
    def _ensure_connection(self) -> bool:
        """Ensure connection is established"""
        if self._connected and self.connection and not self.connection.is_closed:
            return True
        return self._connect()
    
    def publish(self, change_event: Dict[str, Any]) -> bool:
        """
        Publish a change event to RabbitMQ
        
        Args:
            change_event: Change event data dict containing:
                - event_id: UUID (generated if not provided)
                - cluster_id: Cluster ID
                - cluster_name: Cluster name
                - analysis_id: Analysis ID
                - run_id: Run ID (optional)
                - run_number: Run number (optional)
                - change_type: Type of change
                - risk_level: Risk level
                - target_name: Target workload/connection name
                - target_namespace: Target namespace
                - before_state: State before change
                - after_state: State after change
                - affected_services: Number of affected services
                - blast_radius: Impact blast radius
                - changed_by: Who/what made the change
                - details: Additional details
                - metadata: Additional metadata
        
        Returns:
            True if published successfully, False otherwise
        """
        try:
            import pika
            
            if not self._ensure_connection():
                return False
            
            # Ensure event_id is set
            if 'event_id' not in change_event or not change_event['event_id']:
                change_event['event_id'] = str(uuid.uuid4())
            
            # Add timestamp if not present
            if 'timestamp' not in change_event:
                change_event['timestamp'] = datetime.utcnow().isoformat()
            
            if 'detected_at' not in change_event:
                change_event['detected_at'] = change_event['timestamp']
            
            # Wrap data for timeseries-writer format
            message = {
                'event_type': 'change_event',
                'timestamp': change_event['timestamp'],
                'detected_at': change_event.get('detected_at', change_event['timestamp']),
                'event_id': change_event['event_id'],
                'cluster_id': change_event.get('cluster_id'),
                'cluster_name': change_event.get('cluster_name', ''),
                'analysis_id': str(change_event.get('analysis_id', '')),
                'run_id': change_event.get('run_id', 0),
                'run_number': change_event.get('run_number', 1),
                'data': {
                    'change_type': change_event.get('change_type', ''),
                    'risk_level': change_event.get('risk_level', 'medium'),
                    'target_name': change_event.get('target') or change_event.get('target_name', ''),
                    'target_namespace': change_event.get('namespace') or change_event.get('target_namespace', ''),
                    'target_type': change_event.get('target_type', 'workload'),
                    'entity_id': change_event.get('entity_id', 0),
                    'namespace_id': change_event.get('namespace_id'),
                    'before_state': change_event.get('before_state', {}),
                    'after_state': change_event.get('after_state', {}),
                    'affected_services': change_event.get('affected_services', 0),
                    'blast_radius': change_event.get('blast_radius', 0),
                    'changed_by': change_event.get('changed_by', 'auto-discovery'),
                    'details': change_event.get('details', ''),
                    'metadata': change_event.get('metadata', {}),
                }
            }
            
            # Serialize
            body = json.dumps(message, default=str)
            
            # Publish
            self.channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=self.routing_key,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type='application/json',
                )
            )
            
            logger.debug(
                f"Published change event to RabbitMQ",
                extra={
                    "event_id": change_event['event_id'],
                    "change_type": change_event.get('change_type'),
                    "analysis_id": change_event.get('analysis_id')
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish change event: {e}")
            self._connected = False
            return False
    
    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            try:
                self.connection.close()
                logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ connection: {e}")
        self._connected = False


def get_publisher() -> Optional[ChangeEventPublisher]:
    """
    Get the global publisher instance (lazy initialization)
    
    NOTE: ClickHouse is now the ONLY storage for change events.
    Publisher is always enabled.
    
    Returns:
        ChangeEventPublisher instance
    """
    global _publisher, _initialized
    
    if not _initialized:
        _publisher = ChangeEventPublisher()
        logger.info("Change Event Publisher initialized (ClickHouse-only mode)")
        _initialized = True
    
    return _publisher


async def publish_change_event(change_event: Dict[str, Any]) -> bool:
    """
    Async helper to publish a change event to RabbitMQ -> ClickHouse
    
    NOTE: ClickHouse is now the ONLY storage for change events.
    All change events MUST be published via this function.
    
    Args:
        change_event: Change event data dict
        
    Returns:
        True if published successfully, False on error
    """
    publisher = get_publisher()
    if not publisher:
        logger.error("Change Event Publisher not available - events will be lost!")
        return False
    
    try:
        import asyncio
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, publisher.publish, change_event)
        return result
    except Exception as e:
        logger.error(f"Async publish failed: {e}")
        return False


def close_publisher():
    """Close the global publisher connection"""
    global _publisher, _initialized
    
    if _publisher:
        _publisher.close()
        _publisher = None
    
    _initialized = False
