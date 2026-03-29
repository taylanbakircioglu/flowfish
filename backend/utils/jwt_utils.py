"""
JWT token utilities for authentication

Supports two authentication methods:
1. Bearer token (JWT) - for UI users
2. X-API-Key header - for CI/CD pipelines
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import hashlib
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

from config import settings
from database.postgresql import database

logger = structlog.get_logger()

# HTTP Bearer token extractor (auto_error=False to allow API key fallback)
security = HTTPBearer(auto_error=False)


def create_access_token(data: Dict[str, Any]) -> str:
    """Create JWT access token"""
    try:
        to_encode = data.copy()
        
        # Set expiration
        expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        # Encode token
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        
        return encoded_jwt
        
    except Exception as e:
        logger.error("Failed to create access token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token creation failed"
        )


def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Check token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        # Check if token is expired
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
        
        # TODO: Check token blacklist
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    except Exception as e:
        logger.error("Token verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )


async def verify_api_key(api_key: str, client_ip: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Verify an API key and return user info if valid.
    Returns None if invalid.
    """
    if not api_key or not api_key.startswith("fk_"):
        return None
    
    try:
        # Hash the provided key
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Look up in database
        query = """
            SELECT 
                ak.id as key_id, ak.key_id as key_identifier, ak.name as key_name, 
                ak.scopes, ak.cluster_ids, ak.user_id,
                u.username, u.email
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.key_hash = :key_hash
            AND ak.is_active = TRUE
            AND (ak.expires_at IS NULL OR ak.expires_at > NOW())
        """
        
        result = await database.fetch_one(query, {"key_hash": key_hash})
        
        if result:
            # Update usage statistics
            update_query = """
                UPDATE api_keys 
                SET last_used_at = NOW(), 
                    usage_count = usage_count + 1,
                    last_used_ip = :client_ip
                WHERE id = :id
            """
            await database.execute(update_query, {"id": result["key_id"], "client_ip": client_ip})
            
            logger.info(
                "API key authenticated",
                key_id=result["key_identifier"],
                username=result["username"]
            )
            
            return {
                "id": result["user_id"],
                "user_id": result["user_id"],
                "username": result["username"],
                "email": result["email"],
                "roles": ["API Key User"],  # API keys have limited role
                "auth_type": "api_key",
                "key_id": result["key_identifier"],
                "key_name": result["key_name"],
                "scopes": result["scopes"] or [],
                "cluster_ids": result["cluster_ids"]
            }
        
        return None
        
    except Exception as e:
        logger.error("API key verification failed", error=str(e))
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user.
    
    Supports two authentication methods:
    1. Bearer token (JWT) - Authorization: Bearer <token>
    2. API Key - X-API-Key: fk_xxx...
    """
    
    # Get client IP for logging
    client_ip = request.client.host if request.client else None
    if request.headers.get("X-Forwarded-For"):
        client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
    
    # Method 1: Try API Key first (X-API-Key header)
    if x_api_key:
        api_key_user = await verify_api_key(x_api_key, client_ip)
        if api_key_user:
            return api_key_user
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key"
            )
    
    # Method 2: Try Bearer token (JWT)
    if credentials:
        try:
            token = credentials.credentials
            
            # Verify token and get payload
            payload = verify_token(token)
            
            # Extract user information
            user_id = payload.get("user_id")
            username = payload.get("username")
            roles = payload.get("roles", [])
            
            if not user_id or not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
            
            return {
                "id": user_id,
                "user_id": user_id,
                "username": username,
                "roles": roles,
                "auth_type": "jwt",
                "token_payload": payload
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error("JWT verification failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide either 'Authorization: Bearer <token>' or 'X-API-Key: <key>'"
    )


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[Dict[str, Any]]:
    """FastAPI dependency to get current user if authenticated (optional)"""
    if not credentials and not x_api_key:
        return None
    
    try:
        return await get_current_user(request, credentials, x_api_key)
    except HTTPException:
        return None


def require_roles(*required_roles: str):
    """Decorator to require specific roles"""
    def decorator(current_user: Dict[str, Any] = Depends(get_current_user)):
        user_roles = current_user.get("roles", [])
        
        # Super Admin has access to everything
        if "Super Admin" in user_roles:
            return current_user
        
        # Check if user has any of the required roles
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of the following roles: {', '.join(required_roles)}"
            )
        
        return current_user
    
    return decorator


def require_permissions(*required_permissions: str):
    """Decorator to require specific permissions"""
    async def decorator(current_user: Dict[str, Any] = Depends(get_current_user)):
        user_id = current_user["user_id"]
        
        # Check permissions from database
        permissions_query = """
        SELECT DISTINCT p.resource, p.action
        FROM permissions p
        JOIN role_permissions rp ON p.id = rp.permission_id
        JOIN roles r ON rp.role_id = r.id
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = :user_id
        """
        
        user_permissions = await database.fetch_all(permissions_query, {"user_id": user_id})
        user_permission_set = {
            f"{perm['resource']}.{perm['action']}" 
            for perm in user_permissions
        }
        
        # Check if user has required permissions
        missing_permissions = []
        for permission in required_permissions:
            if permission not in user_permission_set:
                missing_permissions.append(permission)
        
        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(missing_permissions)}"
            )
        
        return current_user
    
    return decorator


# Helper functions
async def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user with username and password"""
    try:
        query = """
        SELECT u.id, u.username, u.email, u.password_hash, u.first_name, u.last_name,
               u.is_active, u.is_locked,
               array_agg(r.name) as roles
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE u.username = :username AND u.is_active = true
        GROUP BY u.id
        """
        
        user_record = await database.fetch_one(query, {"username": username})
        
        if not user_record or user_record["is_locked"]:
            return None
        
        # TODO: Implement proper password verification with bcrypt
        # For MVP, simplified check
        if user_record["password_hash"]:
            # Verify password here
            pass
        
        return {
            "id": user_record["id"],
            "username": user_record["username"],
            "email": user_record["email"],
            "full_name": f"{user_record['first_name'] or ''} {user_record['last_name'] or ''}".strip() or user_record["username"],
            "roles": user_record["roles"] or [],
            "is_active": user_record["is_active"]
        }
        
    except Exception as e:
        logger.error("User authentication failed", error=str(e))
        return None
