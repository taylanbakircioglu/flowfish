"""RBAC middleware - placeholder"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # TODO: Implement RBAC middleware in Sprint 1-2
        response = await call_next(request)
        return response
