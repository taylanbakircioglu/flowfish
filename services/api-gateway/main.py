"""
Flowfish API Gateway Service
Main entry point
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.grpc_clients import grpc_clients
from app.api import clusters, analyses, health, event_types, communications

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Create FastAPI app
app = FastAPI(
    title="Flowfish API Gateway",
    description="REST API Gateway for Flowfish Platform",
    version=settings.api_version,
    docs_url=f"/api/{settings.api_version}/docs",
    redoc_url=f"/api/{settings.api_version}/redoc",
    openapi_url=f"/api/{settings.api_version}/openapi.json"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Include routers
app.include_router(health.router, prefix=f"/api/{settings.api_version}")
app.include_router(clusters.router, prefix=f"/api/{settings.api_version}")
app.include_router(event_types.router, prefix=f"/api/{settings.api_version}")
app.include_router(analyses.router, prefix=f"/api/{settings.api_version}")
app.include_router(communications.router, prefix=f"/api/{settings.api_version}")


@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("🐟 Starting Flowfish API Gateway...")
    logger.info(f"Service: {settings.service_name}")
    logger.info(f"Host: {settings.host}:{settings.port}")
    logger.info(f"API Version: {settings.api_version}")
    
    # Connect to gRPC services
    grpc_clients.connect()
    
    logger.info("✅ API Gateway ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("Shutting down API Gateway...")
    grpc_clients.close()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Flowfish API Gateway",
        "version": settings.api_version,
        "docs": f"/api/{settings.api_version}/docs"
    }


def main():
    """Main function"""
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False
    )


if __name__ == '__main__':
    main()

