"""
Graph Writer Service
Main entry point
"""

import logging
import os
import signal
import sys
import asyncio
import uvloop

from app.config import settings
from app.rabbitmq_consumer import consumer
from app.graph_client import graph_client
from app.graph_builder import GraphBuilder
from app.deleted_analysis_cache import deleted_analysis_cache
from app.l7_graph_builder import (
    handle_l7_http_flow,
    handle_l7_grpc_flow,
    handle_l7_dns_flow,
    l7_edge_buffer,
)
from app.l7_same_workload import run_same_workload_periodic

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


async def handle_l7_http_flow_message(data: dict):
    """L7 HTTP flow — L7Workload nodes and L7_COMMUNICATES_WITH in Neo4j."""
    handle_l7_http_flow(data, graph_client)


async def handle_l7_grpc_flow_message(data: dict):
    """L7 gRPC flow — L7Workload nodes and L7_COMMUNICATES_WITH in Neo4j."""
    handle_l7_grpc_flow(data, graph_client)


async def handle_l7_dns_flow_message(data: dict):
    """L7 DNS flow — L7Workload nodes and L7_COMMUNICATES_WITH in Neo4j."""
    try:
        handle_l7_dns_flow(data, graph_client, graph_builder)
    except Exception as e:
        logger.error(f"Failed to handle L7 DNS flow: {e}", exc_info=True)


async def periodic_flush():
    """Periodically flush buffers.

    Each iteration is wrapped in try/except so a transient Neo4j or executor
    error does not terminate the entire periodic loop. The SAME_WORKLOAD task
    runs sequentially after the L4/L7 dedup pass to avoid lock contention on
    the same L7Workload nodes.
    """
    same_workload_counter = 0
    while True:
        await asyncio.sleep(settings.flush_interval)
        try:
            await flush_buffers()
            await asyncio.get_event_loop().run_in_executor(
                None, l7_edge_buffer.flush_if_needed, graph_client
            )
            # SAME_WORKLOAD periodic — runs every N flush cycles when tracing
            # is enabled. Sequential (not parallel) so it never contends with
            # the L7 dedup pass that may be writing to the same nodes.
            if getattr(settings, "l7_tracing_enabled", False):
                same_workload_counter += 1
                cycles = max(1, settings.same_workload_interval // max(1, settings.flush_interval))
                if same_workload_counter >= cycles:
                    same_workload_counter = 0
                    # Thread-safe snapshot — `_flush()` in the executor thread
                    # may mutate `_seen_analysis_ids` concurrently.
                    aids = l7_edge_buffer.snapshot_seen_analysis_ids()
                    if aids:
                        await asyncio.get_event_loop().run_in_executor(
                            None, run_same_workload_periodic, graph_client, aids
                        )
        except Exception:
            logger.error("periodic_flush iteration failed", exc_info=True)


def _parse_resolv_conf() -> list:
    """Read /etc/resolv.conf and extract search domains.

    Per POSIX, if multiple 'search' directives exist, the LAST one wins.
    """
    search_domains: list = []
    try:
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('search '):
                    search_domains = line.split()[1:]
    except (FileNotFoundError, PermissionError):
        pass
    return search_domains


async def refresh_dns_config():
    """Fetch DNS config from backend API and merge with resolv.conf.

    Domain sources (merged):
    1. API: Only enabled, NON-default custom domains (K8s defaults handled by hardcoded logic)
    2. resolv.conf: All search domains from the pod's /etc/resolv.conf
    3. Env var: DNS_SEARCH_DOMAINS (backward compatibility fallback)
    """
    import aiohttp
    backend_url = f"http://{settings.backend_service_host}:{settings.backend_service_port}"

    api_domains: list = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{backend_url}/api/v1/settings/dns-config/defaults") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    api_domains = [
                        d['domain'] for d in data.get('search_domains', [])
                        if d.get('enabled', True) and not d.get('is_default', False)
                    ]
    except Exception as e:
        logger.warning(f"Failed to fetch DNS config from backend: {e}")

    resolv_domains = _parse_resolv_conf()
    all_domains = set(api_domains) | set(resolv_domains)

    env_raw = os.environ.get('DNS_SEARCH_DOMAINS', '')
    if env_raw:
        all_domains |= set(d.strip() for d in env_raw.split(',') if d.strip())

    graph_builder.update_search_domains(list(all_domains))

    if all_domains:
        logger.info(f"DNS search domains updated ({len(all_domains)} domains): {sorted(all_domains)}")
    else:
        logger.warning("DNS search domains list is empty — custom domain normalization will rely on env var fallback")


async def periodic_dns_config_refresh():
    """Periodically refresh DNS search domain config."""
    while True:
        try:
            await refresh_dns_config()
        except Exception as e:
            logger.error(f"DNS config refresh failed: {e}")
        await asyncio.sleep(60)


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
    
    if settings.l7_enabled:
        consumer.register_handler(settings.queue_l7_http_flows, handle_l7_http_flow_message)
        consumer.register_handler(settings.queue_l7_grpc_flows, handle_l7_grpc_flow_message)
        consumer.register_handler(settings.queue_l7_dns_flows, handle_l7_dns_flow_message)
        logger.info(
            "L7 graph consumers ENABLED: %s, %s, %s",
            settings.queue_l7_http_flows,
            settings.queue_l7_grpc_flows,
            settings.queue_l7_dns_flows,
        )
    
    logger.info(
        f"Queues registered: {settings.queue_network_flows}, {settings.queue_dns_queries}, "
        f"{settings.queue_tcp_connections}, {settings.queue_bind_events}, {settings.queue_sni_events}"
        + (
            f", {settings.queue_l7_http_flows}, {settings.queue_l7_grpc_flows}, {settings.queue_l7_dns_flows}"
            if settings.l7_enabled
            else ""
        )
    )
    
    # Refresh DNS search domains at startup, then periodically
    await refresh_dns_config()
    dns_refresh_task = asyncio.create_task(periodic_dns_config_refresh())
    
    # Start periodic flush task
    flush_task = asyncio.create_task(periodic_flush())
    
    # Start consuming
    try:
        await consumer.consume_all_queues()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        flush_task.cancel()
        dns_refresh_task.cancel()
        logger.info("Flushing remaining buffers before shutdown...")
        try:
            await flush_buffers()
        except Exception as e:
            logger.error("L4 shutdown flush failed: %s", e)
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, l7_edge_buffer.force_flush, graph_client
            )
        except Exception as e:
            logger.error("L7 shutdown flush failed: %s", e)
        await consumer.close()
        graph_client.close()


def signal_handler(sig, frame):
    """Handle shutdown signals — raise KeyboardInterrupt so the main loop's
    finally block runs (flush L7 buffer, close connections)."""
    logger.info("Shutting down gracefully (signal %s)...", sig)
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped")

