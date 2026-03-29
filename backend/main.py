"""
Flowfish Backend - FastAPI Application
eBPF-based Kubernetes Application Communication and Dependency Mapping Platform
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import structlog
import uvicorn
import os

# Version info - auto-updated by CI/CD pipeline
try:
    from __version__ import __version__, __build__, __full_version__
except ImportError:
    __version__ = "dev"
    __build__ = 0
    __full_version__ = "dev-local"

from config import settings
from database.postgresql import database, test_connection
from database.redis import redis_client
# from database.clickhouse import clickhouse_client  # Disabled for MVP
from database.neo4j import neo4j_driver, test_neo4j_connection

# Routers - Enable auth and clusters for MVP
from routers import auth, clusters, analyses, workloads, event_types, namespaces, communications, websocket, events
from routers import changes, export_router, dev_console, simulation, blast_radius, api_keys
from routers import settings as settings_router  # Renamed to avoid conflict with config.settings
from routers import scheduled_reports, report_history, users, roles

# Other routers will be enabled progressively
# from routers import (
#     users,
#     dependencies,
#     anomalies,
#     import_router
# )

from middleware.auth_middleware import AuthMiddleware
from middleware.rbac_middleware import RBACMiddleware
from middleware.logging_middleware import LoggingMiddleware

# Health monitoring
from services.health import cluster_health_monitor

# Background workers (optional - can be run as standalone service)
# Set EMBEDDED_CHANGE_WORKER=true to run change detection in backend process
EMBEDDED_CHANGE_WORKER = os.getenv("EMBEDDED_CHANGE_WORKER", "false").lower() == "true"

if EMBEDDED_CHANGE_WORKER:
    from workers.change_detection_worker import change_detection_worker
else:
    change_detection_worker = None

# Scheduled simulation worker (always enabled by default)
from workers.scheduled_simulation_worker import scheduled_simulation_worker


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("🐟 Starting Flowfish Backend...")
    
    # Database connections
    try:
        logger.info("🔌 Connecting to PostgreSQL...")
        pg_connected = await test_connection()
        if pg_connected:
            logger.info("✅ PostgreSQL connected")
        else:
            logger.warning("⚠️ PostgreSQL connection failed, but continuing...")
            
        logger.info("✅ FastAPI app ready")
    except Exception as e:
        logger.error("❌ Startup failed", error=str(e))
        # Continue anyway for MVP testing
        logger.warning("⚠️ Continuing without full database connectivity...")
    
    # Start background services
    try:
        logger.info("🔄 Starting cluster health monitor...")
        await cluster_health_monitor.start()
        logger.info("✅ Cluster health monitor started")
    except Exception as e:
        logger.warning("⚠️ Cluster health monitor failed to start", error=str(e))
    
    # Start change detection worker (only if embedded mode is enabled)
    if EMBEDDED_CHANGE_WORKER and change_detection_worker:
        try:
            logger.info("🔄 Starting embedded change detection worker...")
            await change_detection_worker.start()
            if change_detection_worker.ENABLED:
                logger.info("✅ Embedded change detection worker started")
            else:
                logger.info("ℹ️ Embedded change detection worker disabled (set CHANGE_DETECTION_ENABLED=true to enable)")
        except Exception as e:
            logger.warning("⚠️ Embedded change detection worker failed to start", error=str(e))
    else:
        logger.info("ℹ️ Change detection runs as standalone service (18-change-detection-worker.yaml)")
    
    # Start scheduled simulation worker
    try:
        logger.info("🔄 Starting scheduled simulation worker...")
        await scheduled_simulation_worker.start()
        if scheduled_simulation_worker.ENABLED:
            logger.info("✅ Scheduled simulation worker started")
        else:
            logger.info("ℹ️ Scheduled simulation worker disabled (set SCHEDULED_SIMULATION_ENABLED=true to enable)")
    except Exception as e:
        logger.warning("⚠️ Scheduled simulation worker failed to start", error=str(e))
    
    logger.info("🚀 Flowfish Backend started successfully!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Flowfish Backend...")
    
    # Stop background services
    try:
        logger.info("🔄 Stopping cluster health monitor...")
        await cluster_health_monitor.stop()
        logger.info("✅ Cluster health monitor stopped")
    except Exception as e:
        logger.warning("⚠️ Cluster health monitor stop failed", error=str(e))
    
    # Stop change detection worker (if embedded)
    if EMBEDDED_CHANGE_WORKER and change_detection_worker:
        try:
            logger.info("🔄 Stopping embedded change detection worker...")
            await change_detection_worker.stop()
            logger.info("✅ Embedded change detection worker stopped")
        except Exception as e:
            logger.warning("⚠️ Embedded change detection worker stop failed", error=str(e))
    
    # Stop scheduled simulation worker
    try:
        logger.info("🔄 Stopping scheduled simulation worker...")
        await scheduled_simulation_worker.stop()
        logger.info("✅ Scheduled simulation worker stopped")
    except Exception as e:
        logger.warning("⚠️ Scheduled simulation worker stop failed", error=str(e))
    
    # Close connections
    await redis_client.close()
    
    logger.info("👋 Flowfish Backend shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Flowfish Platform API",
    description="""
    # Flowfish Platform API
    
    eBPF-based Kubernetes/OpenShift application communication and dependency mapping platform.
    
    ## Features
    
    - 🔍 **Automatic Discovery**: eBPF-powered workload communication detection
    - 🗺️ **Real-Time Maps**: Interactive dependency visualization  
    - 🤖 **AI Anomaly Detection**: LLM-powered intelligent analysis
    - 🔄 **Change Simulation**: CAP integration with impact assessment
    - 🏢 **Multi-Cluster**: Enterprise multi-cluster management
    - 📊 **Rich Analytics**: Historical analysis and trend tracking
    
    ## Authentication
    
    This API uses JWT-based authentication. Include the token in the Authorization header:
    `Authorization: Bearer <your_jwt_token>`
    
    ## Rate Limiting
    
    - Authenticated users: 1000 requests/hour
    - Unauthenticated: 100 requests/hour
    """,
    version=__full_version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Add middleware
# CORS - Allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts (security)
if settings.TRUSTED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.TRUSTED_HOSTS.split(",")
    )

# Custom middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RBACMiddleware)

# Include routers - Enable progressively
api_prefix = "/api/v1"

# MVP Phase 1 - Core authentication and cluster management
app.include_router(auth.router, prefix=api_prefix, tags=["Authentication"])
app.include_router(clusters.router, prefix=api_prefix, tags=["Clusters"])

# Phase 2 - Sprint 5-6 enabled
app.include_router(analyses.router, prefix=f"{api_prefix}/analyses", tags=["Analyses"])
app.include_router(workloads.router, prefix=api_prefix, tags=["Workloads"])
app.include_router(event_types.router, prefix=api_prefix, tags=["Event Types"])
app.include_router(namespaces.router, prefix=api_prefix, tags=["Cluster Resources"])

# Communications and Dependency Graph
app.include_router(communications.router, prefix=f"{api_prefix}/communications", tags=["Communications"])

# Events - eBPF event statistics and queries (Layered Architecture)
app.include_router(events.router, prefix=f"{api_prefix}/events", tags=["Events"])

# WebSocket for real-time updates
app.include_router(websocket.router, prefix=api_prefix, tags=["WebSocket"])

# Changes and Export
app.include_router(changes.router, prefix=api_prefix, tags=["Changes"])
app.include_router(export_router.router, prefix=f"{api_prefix}/export", tags=["Export"])

# Dev Console - Developer Query Interface
app.include_router(dev_console.router, prefix=api_prefix, tags=["Dev Console"])

# System Settings - Enterprise configuration
app.include_router(settings_router.router, prefix=api_prefix, tags=["Settings"])

# Simulation - Impact simulation and Network Policy
app.include_router(simulation.router, prefix=f"{api_prefix}/simulation", tags=["Simulation"])

# Blast Radius Oracle - Pre-deployment impact assessment API
app.include_router(blast_radius.router, prefix=api_prefix, tags=["Blast Radius"])
app.include_router(api_keys.router, prefix=api_prefix, tags=["API Keys"])

# Scheduled Reports & Report History
app.include_router(scheduled_reports.router, prefix=api_prefix, tags=["Scheduled Reports"])
app.include_router(report_history.router, prefix=api_prefix, tags=["Report History"])

# User Management
app.include_router(users.router, prefix=api_prefix, tags=["Users"])
app.include_router(roles.router, prefix=f"{api_prefix}/roles", tags=["Roles"])

# Phase 3 - To be enabled next
# app.include_router(dependencies.router, prefix=api_prefix, tags=["Dependencies"])
# app.include_router(anomalies.router, prefix=api_prefix, tags=["Anomalies"])
# app.include_router(import_router.router, prefix=api_prefix, tags=["Import"])


# Root endpoints
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Flowfish Platform API",
        "version": "1.0.0",
        "description": "eBPF-based Kubernetes Application Communication and Dependency Mapping",
        "status": "healthy",
        "docs_url": "/api/docs",
        "api_prefix": api_prefix
    }


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    # Test PostgreSQL
    pg_status = "unknown"
    try:
        pg_ok = await test_connection()
        pg_status = "healthy" if pg_ok else "unhealthy"
    except Exception as e:
        pg_status = f"error: {str(e)[:50]}"
    
    health_status = {"status": "healthy", "checks": {}}
    overall_healthy = True
    
    # Database health checks
    health_status["checks"]["postgresql"] = pg_status
    health_status["checks"]["redis"] = "disabled"
    health_status["checks"]["clickhouse"] = "disabled"
    health_status["checks"]["neo4j"] = "disabled"
    
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    return JSONResponse(
        content=health_status,
        status_code=200 if overall_healthy else 503
    )


@app.get("/api/v1/info")
async def api_info():
    """API information and capabilities"""
    return {
        "api": {
            "name": "Flowfish Platform API",
            "version": "1.0.0",
            "description": "eBPF-based Kubernetes Application Communication and Dependency Mapping",
            "environment": settings.ENVIRONMENT
        },
        "capabilities": {
            "authentication": ["jwt", "oauth", "kubernetes_sa"],
            "data_sources": ["ebpf", "kubernetes", "prometheus", "service_mesh"],
            "databases": ["postgresql", "clickhouse", "neo4j", "redis"],
            "features": ["real_time_mapping", "anomaly_detection", "change_simulation", "policy_simulation"]
        },
        "endpoints": {
            "auth": f"{api_prefix}/auth",
            "clusters": f"{api_prefix}/clusters", 
            "analyses": f"{api_prefix}/analyses",
            "dependencies": f"{api_prefix}/dependencies",
            "health": "/health"
        }
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True
    )
    
    if settings.ENVIRONMENT == "development":
        # Return detailed error in development
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "path": request.url.path,
                "method": request.method
            }
        )
    else:
        # Generic error in production
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR", 
                "message": "An internal error occurred"
            }
        )


if __name__ == "__main__":
    # For development
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["./"],
        log_level="info"
    )
