"""Ingestion Worker - Collects data from Inspektor Gadget"""

import logging
import threading
from datetime import datetime
from typing import Dict, Any
import time

from app.rabbitmq_client import RabbitMQPublisher
from app.event_transformer import EventTransformer

logger = logging.getLogger(__name__)


class IngestionWorker:
    """Single ingestion worker thread"""
    
    def __init__(self, worker_id: int, task_config: Dict[str, Any]):
        self.worker_id = worker_id
        self.task_config = task_config
        self.running = False
        self.thread = None
        
        # Statistics
        self.events_collected = 0
        self.messages_published = 0
        self.errors_count = 0
        self.started_at = None
        self.last_event_at = None
        
        # Clients
        self.rabbitmq = None
        
    def start(self):
        """Start worker thread"""
        self.running = True
        self.started_at = datetime.utcnow()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"Worker {self.worker_id} started for analysis {self.task_config['analysis_id']}")
    
    def stop(self):
        """Stop worker thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.rabbitmq:
            self.rabbitmq.close()
        logger.info(f"Worker {self.worker_id} stopped")
    
    def _run(self):
        """Main worker loop"""
        try:
            # Initialize RabbitMQ
            self.rabbitmq = RabbitMQPublisher()
            
            # TODO: Connect to Inspektor Gadget gRPC stream
            # For now, simulate data collection
            self._simulate_collection()
            
        except Exception as e:
            logger.error(f"Worker {self.worker_id} error: {e}")
            self.errors_count += 1
    
    def _simulate_collection(self):
        """Simulate data collection (for testing)"""
        logger.info(f"Worker {self.worker_id}: Simulating data collection...")
        
        cluster_id = self.task_config.get("cluster_id", 1)
        analysis_id = self.task_config.get("analysis_id", 1)
        analysis_name = self.task_config.get("analysis_name", "test-analysis")
        
        while self.running:
            try:
                # Simulate network flow event
                raw_event = {
                    "namespace": "default",
                    "pod": "nginx-abc123",
                    "container": "nginx",
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
                
                # Transform to message
                message = EventTransformer.transform_network_flow(
                    raw_event,
                    cluster_id,
                    analysis_id,
                    analysis_name
                )
                
                # Publish to RabbitMQ
                self.rabbitmq.publish_network_flow(message)
                
                self.events_collected += 1
                self.messages_published += 1
                self.last_event_at = datetime.utcnow()
                
                logger.debug(f"Worker {self.worker_id}: Published event {self.events_collected}")
                
                # Sleep (simulate event interval)
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Worker {self.worker_id} collection error: {e}")
                self.errors_count += 1
                time.sleep(1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status"""
        return {
            "worker_id": self.worker_id,
            "status": "running" if self.running else "stopped",
            "events_collected": self.events_collected,
            "messages_published": self.messages_published,
            "errors_count": self.errors_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
        }


class IngestionWorkerManager:
    """Manages multiple ingestion workers"""
    
    def __init__(self):
        self.workers: Dict[int, IngestionWorker] = {}
        self.next_worker_id = 1
        self.lock = threading.Lock()
        logger.info("IngestionWorkerManager initialized")
    
    def start_worker(self, request) -> int:
        """Start a new worker for an analysis"""
        with self.lock:
            worker_id = self.next_worker_id
            self.next_worker_id += 1
            
            task_config = {
                "analysis_id": request.analysis_id,
                "analysis_name": request.analysis_name,
                "cluster_id": request.cluster_id,
                "gadget_namespace": request.gadget_namespace,  # CRITICAL: From UI
                "gadget_endpoint": request.gadget_endpoint,  # Deprecated but kept for compat
                "gadget_token": request.gadget_token,
                "scope_type": request.scope_type,
                "namespaces": list(request.namespaces),
                "enabled_gadgets": list(request.enabled_gadgets),
            }
            
            worker = IngestionWorker(worker_id, task_config)
            worker.start()
            
            self.workers[worker_id] = worker
            
            logger.info(f"Started worker {worker_id} for analysis {request.analysis_id}")
            return worker_id
    
    def stop_worker(self, worker_id: int):
        """Stop a worker"""
        with self.lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                worker.stop()
                del self.workers[worker_id]
                logger.info(f"Stopped worker {worker_id}")
            else:
                raise ValueError(f"Worker {worker_id} not found")
    
    def get_worker_status(self, worker_id: int) -> Dict[str, Any]:
        """Get worker status"""
        with self.lock:
            if worker_id in self.workers:
                return self.workers[worker_id].get_status()
            else:
                return {"status": "not_found"}
    
    def get_worker_stats(self, worker_id: int) -> Dict[str, Any]:
        """Get worker statistics"""
        with self.lock:
            if worker_id in self.workers:
                status = self.workers[worker_id].get_status()
                return {
                    "worker_name": f"worker-{worker_id}",
                    "active_tasks": 1 if status["status"] == "running" else 0,
                    "total_events_processed": status["events_collected"],
                    "total_messages_sent": status["messages_published"],
                    "errors_count": status["errors_count"],
                }
            else:
                return {"worker_name": "unknown", "active_tasks": 0}
    
    def update_heartbeat(self, worker_id: int):
        """Update worker heartbeat"""
        # For future distributed workers
        pass
    
    def stop_all(self):
        """Stop all workers"""
        with self.lock:
            for worker_id in list(self.workers.keys()):
                self.stop_worker(worker_id)

