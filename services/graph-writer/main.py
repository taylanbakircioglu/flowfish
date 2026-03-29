"""
Graph Writer Service
Main entry point
"""

import logging
import signal
import sys
import asyncio
import uvloop

from app.config import settings
from app.rabbitmq_consumer import consumer
from app.graph_client import graph_client
from app.graph_builder import GraphBuilder
from app.deleted_analysis_cache import deleted_analysis_cache

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Use uvloop for better performance
uvloop.install()

# Graph builder instance
graph_builder = GraphBuilder()

# Batch buffers
vertex_buffer = []
edge_buffer = []
last_flush_time = 0.0  # Will be initialized in main()


async def flush_buffers():
    """Flush buffers to graph database"""
    global vertex_buffer, edge_buffer, last_flush_time
    
    try:
        vertices_count = len(vertex_buffer)
        if vertex_buffer:
            logger.info(f"Flushing {vertices_count} vertices to graph database")
            result = graph_client.batch_upsert_vertices(vertex_buffer)
            logger.info(f"Vertices flush complete: {result} upserted")
            vertex_buffer = []
        
        # Flush cached edges from graph builder
        cached_edges = graph_builder.flush_edges()
        edges_count = len(cached_edges) if cached_edges else 0
        if cached_edges:
            logger.info(f"Flushing {edges_count} edges to graph database")
            result = graph_client.batch_upsert_edges(cached_edges)
            logger.info(f"Edges flush complete: {result} upserted")
        
        # Log summary with event counts
        if vertices_count > 0 or edges_count > 0:
            logger.info(f"Flush summary - vertices: {vertices_count}, edges: {edges_count}, total_network_flow_received: {event_counts.get('network_flow_received', 0)}")
        
        last_flush_time = asyncio.get_event_loop().time()
        
    except Exception as e:
        logger.error(f"Failed to flush buffers: {e}", exc_info=True)


# Event counters for diagnostics
event_counts = {
    "network_flow_received": 0,
    "network_flow_processed": 0,
    "dns_query_received": 0,
    "dns_query_processed": 0,
    "tcp_connection_received": 0,
    "tcp_connection_processed": 0,
    "bind_event_received": 0,
    "bind_event_processed": 0,
    "sni_event_received": 0,
    "sni_event_processed": 0,
}

async def handle_network_flow(data: dict):
    """Handle network flow event"""
    global event_counts
    event_counts["network_flow_received"] += 1
    
    try:
        # Log every 100th event for diagnostics
        if event_counts["network_flow_received"] % 100 == 0:
            logger.info(f"Network flow events received: {event_counts['network_flow_received']}, processed: {event_counts['network_flow_processed']}")
        
        # Check if analysis has been deleted - skip orphan data
        analysis_id = data.get('analysis_id')
        if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
            logger.debug(f"Skipping network flow for deleted analysis {analysis_id}")
            return
        
        vertices, edges = graph_builder.process_network_flow(data)
        
        # Log first few events with details for diagnostics
        if event_counts["network_flow_received"] <= 5:
            logger.info(f"Network flow event {event_counts['network_flow_received']}: analysis_id={analysis_id}, vertices={len(vertices)}, edges_cached={len(graph_builder.edge_cache)}")
        
        vertex_buffer.extend(vertices)
        edge_buffer.extend(edges)
        event_counts["network_flow_processed"] += 1
        
        # Check if we should flush
        current_time = asyncio.get_event_loop().time()
        if (len(vertex_buffer) >= settings.batch_size or 
            (current_time - last_flush_time) >= settings.flush_interval):
            await flush_buffers()
        
    except Exception as e:
        logger.error(f"Failed to handle network flow: {e}", exc_info=True)


async def handle_dns_query(data: dict):
    """Handle DNS query event"""
    try:
        # Check if analysis has been deleted
        analysis_id = data.get('analysis_id')
        if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
            return
        
        vertices, edges = graph_builder.process_dns_query(data)
        vertex_buffer.extend(vertices)
        edge_buffer.extend(edges)
        
    except Exception as e:
        logger.error(f"Failed to handle DNS query: {e}")


async def handle_tcp_connection(data: dict):
    """Handle TCP connection event"""
    try:
        # Check if analysis has been deleted
        analysis_id = data.get('analysis_id')
        if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
            return
        
        vertices, edges = graph_builder.process_tcp_connection(data)
        vertex_buffer.extend(vertices)
        edge_buffer.extend(edges)
        
    except Exception as e:
        logger.error(f"Failed to handle TCP connection: {e}")


async def handle_bind_event(data: dict):
    """Handle bind event - shows services listening on ports"""
    try:
        # Check if analysis has been deleted
        analysis_id = data.get('analysis_id')
        if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
            return
        
        vertices, edges = graph_builder.process_bind_event(data)
        vertex_buffer.extend(vertices)
        edge_buffer.extend(edges)
        
    except Exception as e:
        logger.error(f"Failed to handle bind event: {e}")


async def handle_sni_event(data: dict):
    """Handle SNI event - shows TLS connections to external services"""
    try:
        # Check if analysis has been deleted
        analysis_id = data.get('analysis_id')
        if analysis_id and deleted_analysis_cache.is_deleted(str(analysis_id)):
            return
        
        vertices, edges = graph_builder.process_sni_event(data)
        vertex_buffer.extend(vertices)
        edge_buffer.extend(edges)
        
    except Exception as e:
        logger.error(f"Failed to handle SNI event: {e}")


async def periodic_flush():
    """Periodically flush buffers"""
    while True:
        await asyncio.sleep(settings.flush_interval)
        await flush_buffers()


async def main():
    """Main function"""
    global last_flush_time
    
    logger.info("Starting Graph Writer Service...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
    logger.info(f"Graph Database: {settings.neo4j_bolt_uri}")
    
    # Initialize last_flush_time
    last_flush_time = asyncio.get_event_loop().time()
    
    # Connect to RabbitMQ
    await consumer.connect()
    
    # Register handlers for all graph-relevant event types
    consumer.register_handler(settings.queue_network_flows, handle_network_flow)
    consumer.register_handler(settings.queue_dns_queries, handle_dns_query)
    consumer.register_handler(settings.queue_tcp_connections, handle_tcp_connection)
    consumer.register_handler(settings.queue_bind_events, handle_bind_event)
    consumer.register_handler(settings.queue_sni_events, handle_sni_event)
    
    logger.info(f"Queues registered: {settings.queue_network_flows}, {settings.queue_dns_queries}, {settings.queue_tcp_connections}, {settings.queue_bind_events}, {settings.queue_sni_events}")
    
    # Start periodic flush task
    flush_task = asyncio.create_task(periodic_flush())
    
    # Start consuming
    try:
        await consumer.consume_all_queues()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        flush_task.cancel()
        await consumer.close()
        graph_client.close()


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Shutting down gracefully...")
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped")

