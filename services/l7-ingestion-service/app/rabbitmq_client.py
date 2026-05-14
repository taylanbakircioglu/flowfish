"""RabbitMQ publisher for L7 events with reconnection."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

import pika
from pika.exceptions import AMQPConnectionError, StreamLostError

from app.config import settings
from app.constants import L7_EXCHANGES

logger = logging.getLogger(__name__)


class L7RabbitMQPublisher:
    """Topic publisher for L7 flow events."""

    def __init__(self) -> None:
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._lock = threading.Lock()
        self._closing = False
        self._connect()

    def _connect(self) -> None:
        with self._lock:
            self._connect_unlocked()

    def _connect_unlocked(self) -> None:
        credentials = pika.PlainCredentials(
            settings.rabbitmq_user,
            settings.rabbitmq_password,
        )
        # heartbeat=60s matches the consumer side (timeseries-writer) and
        # detects broker-driven disconnects an order of magnitude faster
        # than the previous 600s. With BlockingConnection idle for many
        # minutes between gRPC requests, the longer interval allowed the
        # broker to silently drop the TCP socket; we'd then surface a
        # ConnectionResetError + full pika traceback on the *next* publish.
        # The reconnect path is unchanged — we just notice the failure
        # sooner and the visible disconnect window shrinks accordingly.
        parameters = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            virtual_host=settings.rabbitmq_vhost,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=120,
        )
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        for exchange in L7_EXCHANGES.values():
            self._channel.exchange_declare(
                exchange=exchange,
                exchange_type="topic",
                durable=True,
            )
        logger.info(
            "Connected to RabbitMQ for L7 at %s:%s",
            settings.rabbitmq_host,
            settings.rabbitmq_port,
        )

    def publish(self, event: Dict[str, Any], routing_key: str = "l7") -> bool:
        """Route by event_type to the configured exchange; JSON body.
        Returns True if published, False if skipped/closing."""
        if self._closing:
            return False
        event_type = event.get("event_type")
        if not event_type:
            logger.warning("l7_publish_skip_missing_event_type")
            return False
        exchange = L7_EXCHANGES.get(event_type)
        if not exchange:
            logger.warning("l7_publish_unknown_event_type: %s", event_type)
            return False
        self._publish_exchange(exchange, event, routing_key=routing_key)
        return True

    def _publish_exchange(
        self,
        exchange: str,
        message: Dict[str, Any],
        routing_key: str,
    ) -> None:
        if self._closing:
            return
        max_retries = 5
        delay = 0.5
        for attempt in range(max_retries):
            try:
                with self._lock:
                    if self._closing:
                        return
                    if not self._connection or self._connection.is_closed:
                        self._connect_unlocked()
                    if not self._channel or self._channel.is_closed:
                        assert self._connection
                        self._channel = self._connection.channel()
                        for ex in L7_EXCHANGES.values():
                            self._channel.exchange_declare(
                                exchange=ex,
                                exchange_type="topic",
                                durable=True,
                            )
                    body = json.dumps(message, default=str)
                    self._channel.basic_publish(
                        exchange=exchange,
                        routing_key=routing_key,
                        body=body,
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            content_type="application/json",
                        ),
                    )
                return
            except (StreamLostError, AMQPConnectionError, AssertionError) as e:
                logger.warning(
                    "l7_rabbitmq_publish_retry attempt=%s err=%s",
                    attempt + 1,
                    e,
                )
                try:
                    with self._lock:
                        if self._connection and not self._connection.is_closed:
                            self._connection.close()
                except Exception:
                    pass
                self._connection = None
                self._channel = None
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))
            except Exception as e:
                logger.error("l7_rabbitmq_publish_error: %s", e)
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    raise

    def close(self) -> None:
        self._closing = True
        with self._lock:
            try:
                if self._connection and not self._connection.is_closed:
                    self._connection.close()
            except Exception as e:
                logger.warning("l7_rabbitmq_close_error: %s", e)
            finally:
                self._connection = None
                self._channel = None
