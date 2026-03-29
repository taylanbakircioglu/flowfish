"""Logging middleware"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
import time

logger = structlog.get_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate process time
        process_time = time.time() - start_time
        
        # Log request
        logger.info(
            "Request processed",
            method=request.method,
            url=str(request.url),
            status_code=response.status_code,
            process_time=process_time
        )
        
        return response
