"""RabbitMQ Consumer for graph writer"""

import logging
import asyncio
import json
from typing import Callable, Optional
from aio_pika import connect_robust, Message, IncomingMessage
from aio_pika.abc import AbstractRobustConnection, AbstractRobustChannel

from app.config import settings

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """Asynchronous RabbitMQ consumer"""
    
    def __init__(self):
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractRobustChannel] = None
        self.handlers = {}
    
    async def connect(self):
        """Connect to RabbitMQ"""
        try:
            from urllib.parse import quote_plus
            
            # URL encode credentials to handle special characters
            user_encoded = quote_plus(str(settings.rabbitmq_user))
            password_encoded = quote_plus(str(settings.rabbitmq_password))
            vhost_encoded = quote_plus(str(settings.rabbitmq_vhost))
            
            connection_url = f"amqp://{user_encoded}:{password_encoded}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/{vhost_encoded}"
            
            logger.info(f"Connecting to RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
            
            self.connection = await connect_robust(connection_url)
            self.channel = await self.connection.channel()
            
            # Set QoS
            await self.channel.set_qos(prefetch_count=settings.prefetch_count)
            
            logger.info(f"✅ Connected to RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            logger.error(f"  Host: {settings.rabbitmq_host}")
            logger.error(f"  Port: {settings.rabbitmq_port} (type: {type(settings.rabbitmq_port)})")
            logger.error(f"  User: {settings.rabbitmq_user}")
            raise
    
    def register_handler(self, queue_name: str, handler: Callable):
        """Register a message handler for a queue"""
        self.handlers[queue_name] = handler
    
    async def start_consuming(self, queue_name: str):
        """Start consuming from a queue"""
        try:
            # Declare queue with same arguments as ingestion-service
            # Must match x-message-ttl and x-max-length from queue creation
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False,
                arguments={
                    "x-message-ttl": 86400000,  # 24 hours in ms
                    "x-max-length": 1000000     # 1M messages (same as ingestion-service)
                }
            )
            
            logger.info(f"📥 Started consuming from queue: {queue_name}")
            
            # Get handler
            handler = self.handlers.get(queue_name)
            if not handler:
                logger.error(f"No handler registered for queue: {queue_name}")
                return
            
            # Start consuming
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            # Decode message
                            body = message.body.decode('utf-8')
                            data = json.loads(body)
                            
                            # Call handler
                            await handler(data)
                            
                        except Exception as e:
                            logger.error(f"Failed to process message: {e}")
                            # Message will be rejected and requeued
                            raise
        
        except Exception as e:
            logger.error(f"Consumer error for queue {queue_name}: {e}")
            raise
    
    async def consume_all_queues(self):
        """Consume from all registered queues"""
        tasks = []
        for queue_name in self.handlers.keys():
            task = asyncio.create_task(self.start_consuming(queue_name))
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks)
    
    async def close(self):
        """Close connection"""
        if self.channel:
            await self.channel.close()
        if self.connection:
            await self.connection.close()
        logger.info("RabbitMQ connection closed")


# Global consumer instance
consumer = RabbitMQConsumer()

