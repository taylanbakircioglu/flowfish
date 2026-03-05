"""Authentication middleware - placeholder"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # TODO: Implement auth middleware in Sprint 1-2
        response = await call_next(request)
        return response
