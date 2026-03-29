"""
Mock Inspector Gadget gRPC Server
Simulates Inspektor Gadget for local testing
"""

import grpc
from concurrent import futures
import time
import logging
import os
import uuid
import json
from datetime import datetime
import threading
import random

# gRPC Health Check
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_health.v1.health import HealthServicer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('mock-gadget')

# ============================================================================
# MOCK DATA GENERATORS
# ============================================================================

NAMESPACES = ['default', 'kube-system', 'flowfish', 'monitoring', 'ingress-nginx']
PODS = [
    'backend-7d4b8f9c6-abc12',
    'frontend-5f6b7c8d9-def34',
    'postgresql-0',
    'redis-0',
    'clickhouse-0',
    'rabbitmq-0',
    'neo4j-0',
    'nginx-ingress-controller-xyz',
]
SERVICES = [
    {'name': 'backend', 'port': 8000},
    {'name': 'frontend', 'port': 3000},
    {'name': 'postgresql', 'port': 5432},
    {'name': 'redis', 'port': 6379},
    {'name': 'clickhouse', 'port': 9000},
    {'name': 'rabbitmq', 'port': 5672},
    {'name': 'neo4j', 'port': 7687},
]


def generate_network_flow_event(cluster_id: str, analysis_id: str):
    """Generate a mock network flow event"""
    src_pod = random.choice(PODS)
    dst_service = random.choice(SERVICES)
    
    return {
        "event_type": "network_flow",
        "timestamp": datetime.utcnow().isoformat(),
        "event_id": str(uuid.uuid4()),
        "cluster_id": cluster_id,
        "cluster_name": "local-cluster",
        "analysis_id": analysis_id,
        "source_namespace": random.choice(NAMESPACES),
        "source_pod": src_pod,
        "source_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "source_port": random.randint(30000, 65535),
        "dest_namespace": random.choice(NAMESPACES),
        "dest_pod": f"{dst_service['name']}-{random.randint(0,9)}",
        "dest_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "dest_port": dst_service['port'],
        "protocol": random.choice(["TCP", "UDP"]),
        "direction": random.choice(["inbound", "outbound", "internal"]),
        "bytes_sent": random.randint(100, 100000),
        "bytes_received": random.randint(100, 100000),
        "packets_sent": random.randint(1, 1000),
        "packets_received": random.randint(1, 1000),
        "duration_ms": random.randint(1, 5000),
        "latency_ms": random.uniform(0.1, 100.0),
        # Network error metrics (5% chance of error)
        "error_count": 1 if random.random() < 0.05 else 0,
        "retransmit_count": random.randint(0, 3) if random.random() < 0.1 else 0,
        "error_type": random.choice(["CONNECTION_RESET", "CONNECTION_TIMEOUT", "RETRANSMIT", ""]) if random.random() < 0.05 else "",
    }


def generate_dns_event(cluster_id: str, analysis_id: str):
    """Generate a mock DNS query event"""
    domains = [
        'kubernetes.default.svc.cluster.local',
        'postgresql.flowfish.svc.cluster.local',
        'redis.flowfish.svc.cluster.local',
        'www.google.com',
        'api.github.com',
        'registry.docker.io',
    ]
    
    return {
        "event_type": "dns_query",
        "timestamp": datetime.utcnow().isoformat(),
        "event_id": str(uuid.uuid4()),
        "cluster_id": cluster_id,
        "cluster_name": "local-cluster",
        "analysis_id": analysis_id,
        "source_namespace": random.choice(NAMESPACES),
        "source_pod": random.choice(PODS),
        "source_ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "query_name": random.choice(domains),
        "query_type": random.choice(["A", "AAAA", "CNAME"]),
        "response_code": "NOERROR",
        "response_ips": [f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"],
        "latency_ms": random.uniform(0.1, 50.0),
        "dns_server_ip": "10.96.0.10",
        "dns_server_port": 53,
    }


def generate_process_event(cluster_id: str, analysis_id: str):
    """Generate a mock process exec event"""
    commands = [
        ('/bin/sh', ['-c', 'echo hello']),
        ('/usr/bin/python', ['app.py']),
        ('/usr/local/bin/node', ['server.js']),
        ('/bin/curl', ['http://localhost:8080/health']),
        ('/usr/bin/wget', ['https://example.com']),
    ]
    
    cmd = random.choice(commands)
    
    return {
        "event_type": "process_exec",
        "timestamp": datetime.utcnow().isoformat(),
        "event_id": str(uuid.uuid4()),
        "cluster_id": cluster_id,
        "cluster_name": "local-cluster",
        "analysis_id": analysis_id,
        "namespace": random.choice(NAMESPACES),
        "pod": random.choice(PODS),
        "container": "main",
        "pid": random.randint(1000, 65535),
        "ppid": random.randint(1, 1000),
        "uid": 1000,
        "gid": 1000,
        "comm": os.path.basename(cmd[0]),
        "exe": cmd[0],
        "args": cmd[1],
        "event_type_detail": "exec",
    }


# ============================================================================
# MOCK GADGET SERVICE
# ============================================================================

class MockGadgetService:
    """Mock implementation of Inspector Gadget gRPC service"""
    
    def __init__(self):
        self.active_traces = {}
        self.version = "v0.31.0-mock"
        logger.info("MockGadgetService initialized")
    
    def get_version(self):
        return self.version
    
    def start_trace(self, analysis_id: str, cluster_id: str, event_types: list):
        """Start a mock trace"""
        trace_id = str(uuid.uuid4())
        self.active_traces[trace_id] = {
            "analysis_id": analysis_id,
            "cluster_id": cluster_id,
            "event_types": event_types,
            "started_at": datetime.utcnow().isoformat(),
            "events_generated": 0,
        }
        logger.info(f"Started trace {trace_id} for analysis {analysis_id}")
        return trace_id
    
    def stop_trace(self, trace_id: str):
        """Stop a trace"""
        if trace_id in self.active_traces:
            trace = self.active_traces.pop(trace_id)
            logger.info(f"Stopped trace {trace_id}, generated {trace['events_generated']} events")
            return True
        return False
    
    def generate_events(self, trace_id: str, count: int = 10):
        """Generate mock events for a trace"""
        if trace_id not in self.active_traces:
            return []
        
        trace = self.active_traces[trace_id]
        events = []
        
        for _ in range(count):
            event_type = random.choice(trace['event_types']) if trace['event_types'] else 'network_flow'
            
            if event_type == 'network_flow':
                event = generate_network_flow_event(trace['cluster_id'], trace['analysis_id'])
            elif event_type == 'dns_query':
                event = generate_dns_event(trace['cluster_id'], trace['analysis_id'])
            elif event_type == 'process_exec':
                event = generate_process_event(trace['cluster_id'], trace['analysis_id'])
            else:
                event = generate_network_flow_event(trace['cluster_id'], trace['analysis_id'])
            
            events.append(event)
            trace['events_generated'] += 1
        
        return events


# Global service instance
mock_service = MockGadgetService()


# ============================================================================
# gRPC SERVER
# ============================================================================

def serve():
    """Start the gRPC server"""
    port = os.environ.get('GRPC_PORT', '16060')
    
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add health service
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    
    # Set service status to SERVING
    health_servicer.set('', health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set('inspektor-gadget', health_pb2.HealthCheckResponse.SERVING)
    
    # Enable reflection for debugging
    try:
        from grpc_reflection.v1alpha import reflection
        SERVICE_NAMES = (
            health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        logger.info("gRPC reflection enabled")
    except Exception as e:
        logger.warning(f"Could not enable reflection: {e}")
    
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    logger.info(f"🚀 Mock Inspector Gadget gRPC server started on port {port}")
    logger.info(f"   Version: {mock_service.get_version()}")
    logger.info(f"   Health check: grpc://{port}/grpc.health.v1.Health/Check")
    
    # Keep server running
    try:
        while True:
            time.sleep(86400)  # Sleep for a day
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.stop(0)


if __name__ == '__main__':
    serve()

