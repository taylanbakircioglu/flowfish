# 🐟 Flowfish - RabbitMQ Integration

## Why RabbitMQ?

Benefits of using a RabbitMQ message queue instead of writing stream data from Inspector Gadget directly to ClickHouse:

### 1. **Decoupling**
- Ingestion Service and ClickHouse Writer are independent of each other
- Each service runs at its own pace
- Failure in one service does not affect the other

### 2. **Buffering & Backpressure**
- RabbitMQ holds messages in the queue
- If ClickHouse is slow, messages are not lost
- Ingestion Service does not block

### 3. **Scalability**
- Multiple Ingestion workers (1-N)
- Multiple ClickHouse writers (1-N)
- Each worker scales independently

### 4. **Reliability**
- Message persistence (written to disk)
- Delivery acknowledgment
- Dead Letter Queue (failed messages)
- Retry logic

### 5. **Flexibility**
- The same data can be consumed by multiple consumers
- Future: Neo4j writer, Kafka bridge, etc.
- Real-time streaming to dashboard

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA FLOW ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────┘

  Inspektor Gadget (Target Cluster)     Change Detection Worker
         │                                        │
         │ gRPC Stream                            │ Dual-Write
         │ (eBPF Events)                          │
         ▼                                        │
  ┌──────────────────┐                            │
  │ Ingestion Service│ (Multiple Workers)         │
  │  - Stream read   │                            │
  │  - Transform     │                            │
  │  - Validate      │                            │
  │  - Enrich        │                            │
  └────────┬─────────┘                            │
           │ Publish                              │
           │ (JSON Messages)                      │
           ▼                                      ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                      RabbitMQ Exchanges                        │
  │  • flowfish.network_flows (topic)                              │
  │  • flowfish.dns_queries (topic)                                │
  │  • flowfish.tcp_connections (topic)                            │
  │  • flowfish.workload_metadata (topic) 🆕                       │
  │  • flowfish.change_events (topic) 🆕                           │
  └────────┬──────────────────────────────────────────────────────┘
           │ Route
           │ (Routing Keys)
           ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                       RabbitMQ Queues                          │
  │  • network_flows.clickhouse (durable)                          │
  │  • dns_queries.clickhouse (durable)                            │
  │  • tcp_connections.clickhouse (durable)                        │
  │  • flowfish.queue.workload_metadata.timeseries (durable) 🆕    │
  │  • flowfish.queue.change_events.timeseries (durable) 🆕        │
  │                                                                │
  │  Features:                                                     │
  │    - Max length: 1M messages                                   │
  │    - TTL: 24 hours                                             │
  │    - Persistence: disk                                         │
  │    - Dead Letter Queue for failed messages                     │
  └────────┬──────────────────────────────────────────────────────┘
           │ Consume
           │ (Batch: 1000 msg or 10s)
           ▼
  ┌──────────────────────┐
  │ Timeseries Writer    │ (Multiple Workers)
  │  - Batch consume     │
  │  - Bulk insert       │
  │  - ACK on success    │
  │  - Retry on error    │
  │  - Workload sync     │ 🆕 (PostgreSQL)
  └────────┬─────────────┘
           │ Bulk INSERT
           ▼
  ┌──────────────────────┐
  │   ClickHouse DB      │
  │  - network_flows     │
  │  - dns_queries       │
  │  - tcp_connections   │
  │  - workload_metadata │ 🆕
  │  - change_events     │ 🆕
  └──────────────────────┘
```

---

## RabbitMQ Configuration

### Exchanges

| Name | Type | Durable | Purpose |
|------|------|---------|---------|
| `flowfish.network_flows` | topic | yes | Network flow events |
| `flowfish.dns_queries` | topic | yes | DNS query events |
| `flowfish.tcp_connections` | topic | yes | TCP connection events |
| `flowfish.change_events` | topic | yes | Infrastructure change events 🆕 |
| `flowfish.workload_metadata` | topic | yes | Pod/workload discovery events 🆕 |

### Queues

| Name | Durable | Max Length | TTL | Consumer |
|------|---------|------------|-----|----------|
| `network_flows.clickhouse` | yes | 1,000,000 | 24h | ClickHouse Writer |
| `dns_queries.clickhouse` | yes | 1,000,000 | 24h | ClickHouse Writer |
| `tcp_connections.clickhouse` | yes | 1,000,000 | 24h | ClickHouse Writer |
| `flowfish.queue.change_events.timeseries` | yes | 1,000,000 | 24h | Timeseries Writer 🆕 |
| `flowfish.queue.workload_metadata.timeseries` | yes | 1,000,000 | 24h | Timeseries Writer 🆕 |

### Bindings

```
flowfish.network_flows (exchange)
  └── network_flows.clickhouse (queue)
      Routing Key: #

flowfish.dns_queries (exchange)
  └── dns_queries.clickhouse (queue)
      Routing Key: #

flowfish.tcp_connections (exchange)
  └── tcp_connections.clickhouse (queue)
      Routing Key: #

flowfish.change_events (exchange) 🆕
  └── flowfish.queue.change_events.timeseries (queue)
      Routing Key: #
      DLQ: flowfish.change_events.dlq

flowfish.workload_metadata (exchange) 🆕
  └── flowfish.queue.workload_metadata.timeseries (queue)
      Routing Key: #
```

---

## Message Formats (JSON)

### Network Flow Message
```json
{
  "message_id": "uuid-v4",
  "event_type": "network_flow",
  "cluster_id": 1,
  "analysis_id": 42,
  "analysis_name": "production-analysis-2024",
  "timestamp": "2024-11-21T12:34:56.789Z",
  "data": {
    "namespace": "default",
    "pod_name": "nginx-deployment-abc123",
    "container_name": "nginx",
    "src_ip": "10.1.2.3",
    "src_port": 54321,
    "dst_ip": "10.1.2.4",
    "dst_port": 80,
    "protocol": "TCP",
    "bytes_sent": 1024,
    "bytes_received": 2048,
    "packets_sent": 10,
    "packets_received": 15,
    "duration_ms": 150
  }
}
```

### DNS Query Message
```json
{
  "message_id": "uuid-v4",
  "event_type": "dns_query",
  "cluster_id": 1,
  "analysis_id": 42,
  "analysis_name": "production-analysis-2024",
  "timestamp": "2024-11-21T12:34:56.789Z",
  "data": {
    "namespace": "default",
    "pod_name": "app-pod-xyz",
    "query_name": "api.example.com",
    "query_type": "A",
    "response_ip": "1.2.3.4",
    "response_code": 0,
    "latency_ms": 12.5
  }
}
```

### TCP Connection Message
```json
{
  "message_id": "uuid-v4",
  "event_type": "tcp_connection",
  "cluster_id": 1,
  "analysis_id": 42,
  "analysis_name": "production-analysis-2024",
  "timestamp": "2024-11-21T12:34:56.789Z",
  "data": {
    "namespace": "default",
    "pod_name": "backend-pod-123",
    "src_ip": "10.1.2.5",
    "src_port": 45678,
    "dst_ip": "10.1.2.6",
    "dst_port": 5432,
    "state": "ESTABLISHED",
    "rtt_ms": 2.3
  }
}
```

### Change Event Message (NEW) 🆕
```json
{
  "message_type": "change_event",
  "event_id": "uuid-v4",
  "analysis_id": 42,
  "run_id": "uuid-v4",
  "cluster_id": 1,
  "event_type": "workload_added",
  "entity_type": "workload",
  "entity_name": "payment-service",
  "namespace": "production",
  "target_namespace": null,
  "severity": "low",
  "risk_score": 0.2,
  "details": {
    "replicas": 3,
    "image": "payment:v2.0"
  },
  "detected_at": "2024-11-21T12:34:56.789Z"
}
```

**Change Event Types:**
- `workload_added`: New deployment/pod discovered
- `workload_removed`: Deployment/pod deleted
- `workload_updated`: Replicas, labels, or config changed
- `connection_added`: New network connection detected
- `connection_removed`: Network connection lost
- `port_changed`: Service port modified

---

## Ingestion Service Logic

```python
# Pseudo-code

import grpc
import pika
import json
import uuid
from datetime import datetime

class IngestionWorker:
    def __init__(self, task):
        self.task = task
        self.gadget_client = None
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
    
    async def start(self):
        # Connect to Inspektor Gadget
        self.gadget_client = await self.connect_to_gadget()
        
        # Connect to RabbitMQ
        self.rabbitmq_connection = await self.connect_to_rabbitmq()
        self.rabbitmq_channel = self.rabbitmq_connection.channel()
        
        # Start streaming
        await self.stream_data()
    
    async def stream_data(self):
        # Start gadget trace
        stream = self.gadget_client.start_trace(
            gadgets=["trace_network", "trace_dns", "trace_tcp"],
            namespace=self.task.namespace,
            label_selector=self.task.labels
        )
        
        # Read stream
        async for event in stream:
            try:
                # Transform event
                message = self.transform_event(event)
                
                # Publish to RabbitMQ
                self.publish_to_rabbitmq(message)
                
                # Update stats
                self.stats.events_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                self.stats.errors += 1
    
    def transform_event(self, event):
        """Transform eBPF event to RabbitMQ message"""
        message = {
            "message_id": str(uuid.uuid4()),
            "event_type": event.type,  # network_flow, dns_query, tcp_connection
            "cluster_id": self.task.cluster_id,
            "analysis_id": self.task.analysis_id,
            "analysis_name": self.task.analysis_name,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event.data
        }
        return message
    
    def publish_to_rabbitmq(self, message):
        """Publish message to appropriate exchange"""
        exchange = f"flowfish.{message['event_type']}s"
        
        self.rabbitmq_channel.basic_publish(
            exchange=exchange,
            routing_key='',
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type='application/json'
            )
        )
```

---

## ClickHouse Writer Service Logic

```python
# Pseudo-code

import pika
import json
from clickhouse_driver import Client

class ClickHouseWriter:
    def __init__(self):
        self.clickhouse = Client(host='clickhouse', port=9000)
        self.batch = []
        self.batch_size = 1000
        self.last_flush = time.time()
        self.flush_interval = 10  # seconds
    
    def start(self):
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters('rabbitmq')
        )
        channel = connection.channel()
        
        # Consume from all queues
        channel.basic_qos(prefetch_count=self.batch_size)
        
        channel.basic_consume(
            queue='network_flows.clickhouse',
            on_message_callback=self.on_message,
            auto_ack=False
        )
        
        channel.basic_consume(
            queue='dns_queries.clickhouse',
            on_message_callback=self.on_message,
            auto_ack=False
        )
        
        channel.basic_consume(
            queue='tcp_connections.clickhouse',
            on_message_callback=self.on_message,
            auto_ack=False
        )
        
        # Start consuming
        channel.start_consuming()
    
    def on_message(self, ch, method, properties, body):
        """Process single message"""
        try:
            message = json.loads(body)
            
            # Add to batch
            self.batch.append((message, method.delivery_tag))
            
            # Check if should flush
            if self.should_flush():
                self.flush_batch(ch)
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # NACK with requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def should_flush(self):
        """Check if batch should be flushed"""
        return (
            len(self.batch) >= self.batch_size or
            time.time() - self.last_flush >= self.flush_interval
        )
    
    def flush_batch(self, channel):
        """Write batch to ClickHouse"""
        if not self.batch:
            return
        
        try:
            # Group by event type
            network_flows = []
            dns_queries = []
            tcp_connections = []
            
            for message, tag in self.batch:
                if message['event_type'] == 'network_flow':
                    network_flows.append(message)
                elif message['event_type'] == 'dns_query':
                    dns_queries.append(message)
                elif message['event_type'] == 'tcp_connection':
                    tcp_connections.append(message)
            
            # Bulk insert
            if network_flows:
                self.write_network_flows(network_flows)
            if dns_queries:
                self.write_dns_queries(dns_queries)
            if tcp_connections:
                self.write_tcp_connections(tcp_connections)
            
            # ACK all messages
            for _, tag in self.batch:
                channel.basic_ack(delivery_tag=tag)
            
            # Clear batch
            self.batch.clear()
            self.last_flush = time.time()
            
            logger.info(f"Flushed batch: {len(self.batch)} messages")
        
        except Exception as e:
            logger.error(f"Failed to flush batch: {e}")
            # NACK all with requeue
            for _, tag in self.batch:
                channel.basic_nack(delivery_tag=tag, requeue=True)
    
    def write_network_flows(self, messages):
        """Bulk insert network flows"""
        rows = []
        for msg in messages:
            data = msg['data']
            rows.append((
                msg['timestamp'],
                msg['cluster_id'],
                msg['analysis_id'],
                msg['analysis_name'],
                data['namespace'],
                data['pod_name'],
                data['container_name'],
                data['src_ip'],
                data['src_port'],
                data['dst_ip'],
                data['dst_port'],
                data['protocol'],
                data['bytes_sent'],
                data['bytes_received'],
                data['packets_sent'],
                data['packets_received'],
                data['duration_ms']
            ))
        
        self.clickhouse.execute(
            'INSERT INTO network_flows VALUES',
            rows
        )
```

---

## Deployment

### 1. Deploy RabbitMQ
```bash
kubectl apply -f deployment/kubernetes-manifests/06-rabbitmq.yaml
```

### 2. Wait for RabbitMQ to be ready
```bash
kubectl wait --for=condition=ready pod -l app=rabbitmq -n flowfish --timeout=300s
```

### 3. Verify exchanges and queues
```bash
kubectl port-forward -n flowfish svc/rabbitmq 15672:15672
# Open http://localhost:15672
# Login: flowfish / flowfish-rabbit-2024
```

---

## Monitoring & Metrics

### RabbitMQ Management UI
- **URL:** http://localhost:15672
- **Credentials:** flowfish / flowfish-rabbit-2024
- **Metrics:**
  - Queue depth
  - Message rates (publish/consume)
  - Consumer count
  - Memory usage

### Prometheus Metrics (RabbitMQ Exporter)
- `rabbitmq_queue_messages`
- `rabbitmq_queue_messages_ready`
- `rabbitmq_queue_messages_unacknowledged`
- `rabbitmq_queue_consumers`

### Application Metrics
- **Ingestion Service:**
  - Events processed
  - Messages published
  - Errors
- **ClickHouse Writer:**
  - Messages consumed
  - Rows written
  - Batch size/time
  - Write errors

---

## Error Handling

### Dead Letter Queue (DLQ)
```yaml
# Create DLQ for failed messages
queues:
  - name: network_flows.clickhouse
    arguments:
      x-dead-letter-exchange: flowfish.dlx
      x-dead-letter-routing-key: network_flows.failed
```

### Retry Strategy
1. **Immediate Retry:** RabbitMQ requeue (max 3 times)
2. **Delayed Retry:** Move to delayed queue (exponential backoff)
3. **Dead Letter:** After max retries, move to DLQ for manual inspection

---

## Benefits Summary

✅ **Decoupling:** Services independent  
✅ **Reliability:** No data loss  
✅ **Scalability:** Easy horizontal scaling  
✅ **Observability:** Queue metrics & monitoring  
✅ **Flexibility:** Multiple consumers possible  
✅ **Performance:** Batch processing, backpressure handling  

---

**Status:** ✅ Architecture fully implemented  
**Last Updated:** January 2026  
**Change Detection:** ClickHouse-only architecture (PostgreSQL removed)

