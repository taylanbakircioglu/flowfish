"""
flowfish-l7-collector: In-cluster OTLP receiver and Pull API bridge.

Receives OTLP traces and metrics from Grafana Beyla via HTTP on port 8080,
transforms them into Flowfish L7 events, and exposes a pull API for central ingestion.
"""
import asyncio
import logging
import random
import time
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import config
from app import k8s_metadata
from app.event_buffer import EventBuffer
from app.otlp_receiver import router as otlp_router, set_buffer as set_otlp_buffer
from app.pull_api import router as pull_router, set_buffer as set_pull_buffer

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("flowfish-l7-collector")

buffer = EventBuffer(
    max_size=config.BUFFER_MAX_SIZE,
    ttl_seconds=config.BUFFER_TTL_SECONDS,
)
set_otlp_buffer(buffer)
set_pull_buffer(buffer)

_mock_task = None

MOCK_PODS = [
    ("web-frontend", "app-ns", "web-frontend-abc123", "10.0.1.5"),
    ("api-gateway", "gateway-ns", "api-gateway-xyz789", "10.0.2.10"),
    ("users-service", "backend-ns", "users-service-def456", "10.0.3.15"),
    ("orders-service", "backend-ns", "orders-service-ghi012", "10.0.3.20"),
    ("products-service", "backend-ns", "products-service-jkl345", "10.0.3.25"),
    ("payment-service", "backend-ns", "payment-service-mno678", "10.0.3.30"),
]

MOCK_PATHS = [
    "/api/v1/users", "/api/v1/orders", "/api/v1/products",
    "/api/v1/payments", "/api/v2/auth/login", "/api/v1/health",
]


def _mock_endpoint(idx: int) -> dict:
    name, ns, pod, ip = MOCK_PODS[idx]
    return {
        "ip": ip,
        "port": random.randint(3000, 9999),
        "namespace": ns,
        "pod_name": pod,
        "workload_name": name,
    }


async def _generate_mock_events():
    """Generate sample L7 events for local testing without real Beyla."""
    logger.info("Mock mode enabled - generating sample events")
    while True:
        try:
            src_idx = random.randint(0, len(MOCK_PODS) - 1)
            dst_idx = random.choice([i for i in range(len(MOCK_PODS)) if i != src_idx])

            event_type = random.choices(
                ["l7_http_flow", "l7_grpc_flow", "l7_dns_flow"],
                weights=[70, 20, 10],
            )[0]

            if event_type == "l7_http_flow":
                event = {
                    "event_type": "l7_http_flow",
                    "timestamp": int(time.time() * 1000),
                    "data": {
                        "src": _mock_endpoint(src_idx),
                        "dst": _mock_endpoint(dst_idx),
                        "method": random.choice(["GET", "POST", "PUT", "DELETE"]),
                        "path": random.choice(MOCK_PATHS),
                        "host": f"{MOCK_PODS[dst_idx][0]}.{MOCK_PODS[dst_idx][1]}.svc.cluster.local",
                        "response_status": random.choices(
                            [200, 201, 204, 400, 404, 500, 502],
                            weights=[60, 10, 5, 8, 7, 5, 5],
                        )[0],
                        "request_size": random.randint(100, 5000),
                        "response_size": random.randint(200, 50000),
                        "duration_ms": round(random.uniform(1, 500), 2),
                    },
                }
            elif event_type == "l7_grpc_flow":
                event = {
                    "event_type": "l7_grpc_flow",
                    "timestamp": int(time.time() * 1000),
                    "data": {
                        "src": _mock_endpoint(src_idx),
                        "dst": _mock_endpoint(dst_idx),
                        "grpc_service": random.choice([
                            "users.UserService", "orders.OrderService",
                            "products.ProductService", "payment.PaymentService",
                        ]),
                        "grpc_method": random.choice(["GetUser", "CreateOrder", "ListProducts", "ProcessPayment"]),
                        "grpc_status_code": random.choices([0, 2, 5, 13], weights=[85, 5, 5, 5])[0],
                        "grpc_status_message": "",
                        "request_size": random.randint(50, 2000),
                        "response_size": random.randint(100, 10000),
                        "duration_ms": round(random.uniform(1, 200), 2),
                    },
                }
            else:
                event = {
                    "event_type": "l7_dns_flow",
                    "timestamp": int(time.time() * 1000),
                    "data": {
                        "src": _mock_endpoint(src_idx),
                        "dst": _mock_endpoint(dst_idx),
                        "query_name": random.choice([
                            "users-service.backend-ns.svc.cluster.local",
                            "orders-service.backend-ns.svc.cluster.local",
                            "api-gateway.gateway-ns.svc.cluster.local",
                            "external-api.example.com",
                        ]),
                        "query_type": "A",
                        "response_code": 0,
                        "response_ips": "[]",
                        "duration_ms": round(random.uniform(0.1, 10), 2),
                    },
                }

            await buffer.add(event)
            await asyncio.sleep(config.MOCK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("mock_event_error: %s", e)
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global _mock_task
    logger.info(
        "Starting flowfish-l7-collector (mock=%s, buffer_max=%d)",
        config.MOCK_MODE,
        config.BUFFER_MAX_SIZE,
    )
    if not config.MOCK_MODE:
        try:
            k8s_metadata.warm_cache()
        except Exception as e:
            logger.warning("k8s_metadata warm_cache failed (will retry in background): %s", e)
    if config.MOCK_MODE:
        _mock_task = asyncio.create_task(_generate_mock_events())
    yield
    if _mock_task:
        _mock_task.cancel()
        try:
            await _mock_task
        except asyncio.CancelledError:
            pass
    logger.info("flowfish-l7-collector shutdown")


app = FastAPI(
    title="flowfish-l7-collector",
    description="In-cluster OTLP receiver and pull API bridge for Beyla L7 events",
    lifespan=lifespan,
)
app.include_router(otlp_router, tags=["OTLP Receiver"])
app.include_router(pull_router, tags=["Pull API"])


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.API_PORT,
        log_level=config.LOG_LEVEL.lower(),
    )
