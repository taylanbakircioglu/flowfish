"""
API Keys Router - Manage API keys for CI/CD pipeline authentication

Features:
- Generate API keys with custom scopes and expiration
- List, view, and revoke API keys
- Track usage statistics
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
import structlog
import secrets
import hashlib
import uuid

from database.postgresql import database
from utils.jwt_utils import get_current_user

logger = structlog.get_logger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key"""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for the key")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description")
    scopes: List[str] = Field(default=["blast-radius"], description="API scopes this key can access")
    cluster_ids: Optional[List[int]] = Field(None, description="Specific cluster IDs, null for all clusters")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiration, null for never")


class ApiKeyResponse(BaseModel):
    """API key details (without the actual key)"""
    id: int
    key_id: str
    key_prefix: str
    name: str
    description: Optional[str]
    scopes: List[str]
    cluster_ids: Optional[List[int]]
    is_active: bool
    expires_at: Optional[str]
    last_used_at: Optional[str]
    last_used_ip: Optional[str]
    usage_count: int
    created_at: str
    created_by: str


class ApiKeyCreatedResponse(BaseModel):
    """Response when a new API key is created (includes the actual key - shown only once!)"""
    key_id: str
    api_key: str  # Full key - only shown once!
    name: str
    scopes: List[str]
    expires_at: Optional[str]
    message: str = "Store this API key securely - it will not be shown again!"


class RevokeApiKeyRequest(BaseModel):
    """Request to revoke an API key"""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for revoking")


# =============================================================================
# Helper Functions
# =============================================================================

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns: (full_key, key_hash, key_prefix)
    
    Format: fk_<random_32_chars>
    Example: fk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    """
    # Generate random bytes and convert to hex
    random_part = secrets.token_hex(24)  # 48 chars
    full_key = f"fk_{random_part}"
    
    # Hash the key for storage (never store plain key!)
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    
    # Prefix for identification (first 8 chars after fk_)
    key_prefix = f"fk_{random_part[:8]}"
    
    return full_key, key_hash, key_prefix


def generate_key_id() -> str:
    """Generate a unique key ID"""
    return f"key_{uuid.uuid4().hex[:12]}"


async def verify_api_key(api_key: str) -> Optional[dict]:
    """
    Verify an API key and return the key details if valid.
    Returns None if invalid.
    """
    if not api_key or not api_key.startswith("fk_"):
        return None
    
    # Hash the provided key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    # Look up in database
    query = """
        SELECT 
            ak.id, ak.key_id, ak.name, ak.scopes, ak.cluster_ids,
            ak.is_active, ak.expires_at, ak.user_id,
            u.username as created_by
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
            SET last_used_at = NOW(), usage_count = usage_count + 1
            WHERE id = :id
        """
        await database.execute(update_query, {"id": result["id"]})
        
        return dict(result)
    
    return None


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: CreateApiKeyRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new API key.
    
    **Important**: The full API key is only shown once in the response.
    Store it securely - it cannot be retrieved later!
    
    Available scopes:
    - `blast-radius`: Access blast radius assessment API
    - `read`: Read-only access to clusters and analyses
    - `write`: Write access (create analyses, etc.)
    """
    try:
        # Generate the key
        full_key, key_hash, key_prefix = generate_api_key()
        key_id = generate_key_id()
        
        # Calculate expiration
        expires_at = None
        if request.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
        
        # Insert into database
        scopes_list = list(request.scopes) if request.scopes else ['blast-radius']
        cluster_ids_list = list(request.cluster_ids) if request.cluster_ids else []
        
        logger.info(
            "Creating API key in database",
            key_id=key_id,
            user_id=current_user["id"],
            scopes=scopes_list,
            cluster_ids=cluster_ids_list
        )
        
        # Convert arrays to PostgreSQL array literal format for SQLAlchemy text()
        # Format: ARRAY['val1', 'val2'] for text arrays
        scopes_sql = "ARRAY[" + ",".join(f"'{s}'" for s in scopes_list) + "]::text[]"
        cluster_ids_sql = "ARRAY[" + ",".join(str(c) for c in cluster_ids_list) + "]::integer[]" if cluster_ids_list else "NULL"
        
        # Build query with inline arrays (safe since we control the values)
        insert_query = f"""
            INSERT INTO api_keys (
                key_id, key_hash, key_prefix, name, description,
                user_id, scopes, cluster_ids, expires_at, is_active, usage_count
            ) VALUES (
                :key_id, :key_hash, :key_prefix, :name, :description,
                :user_id, {scopes_sql}, {cluster_ids_sql}, :expires_at, true, 0
            )
            RETURNING id
        """
        
        await database.execute(insert_query, {
            "key_id": key_id,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "name": request.name,
            "description": request.description,
            "user_id": current_user["id"],
            "expires_at": expires_at
        })
        
        logger.info(
            "API key created",
            key_id=key_id,
            name=request.name,
            scopes=request.scopes,
            created_by=current_user["username"]
        )
        
        return ApiKeyCreatedResponse(
            key_id=key_id,
            api_key=full_key,
            name=request.name,
            scopes=request.scopes,
            expires_at=expires_at.isoformat() if expires_at else None,
            message="Store this API key securely - it will not be shown again!"
        )
        
    except Exception as e:
        import traceback
        error_detail = str(e)
        error_traceback = traceback.format_exc()
        logger.error("Failed to create API key", error=error_detail, traceback=error_traceback)
        
        # Return more helpful error message
        if "api_keys" in error_detail.lower() and "does not exist" in error_detail.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API keys table not found. Please restart the backend to run migrations."
            )
        elif "user_id" in error_detail.lower() or "foreign key" in error_detail.lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User reference error: {error_detail}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create API key: {error_detail}"
            )


@router.get("/api-keys", response_model=List[ApiKeyResponse])
async def list_api_keys(
    include_revoked: bool = Query(False, description="Include revoked keys"),
    current_user: dict = Depends(get_current_user)
):
    """
    List all API keys for the current user.
    Admins can see all keys.
    """
    try:
        # Check if user is admin
        is_admin = current_user.get("role") == "Super Admin" or current_user.get("username") == "admin"
        
        if is_admin:
            query = """
                SELECT 
                    ak.id, ak.key_id, ak.key_prefix, ak.name, ak.description,
                    ak.scopes, ak.cluster_ids, ak.is_active, ak.expires_at,
                    ak.last_used_at, ak.last_used_ip, ak.usage_count, ak.created_at,
                    u.username as created_by
                FROM api_keys ak
                JOIN users u ON ak.user_id = u.id
                WHERE (:include_revoked = TRUE OR ak.is_active = TRUE)
                ORDER BY ak.created_at DESC
            """
            results = await database.fetch_all(query, {"include_revoked": include_revoked})
        else:
            query = """
                SELECT 
                    ak.id, ak.key_id, ak.key_prefix, ak.name, ak.description,
                    ak.scopes, ak.cluster_ids, ak.is_active, ak.expires_at,
                    ak.last_used_at, ak.last_used_ip, ak.usage_count, ak.created_at,
                    u.username as created_by
                FROM api_keys ak
                JOIN users u ON ak.user_id = u.id
                WHERE ak.user_id = :user_id
                AND (:include_revoked = TRUE OR ak.is_active = TRUE)
                ORDER BY ak.created_at DESC
            """
            results = await database.fetch_all(query, {
                "user_id": current_user["id"],
                "include_revoked": include_revoked
            })
        
        return [
            ApiKeyResponse(
                id=row["id"],
                key_id=row["key_id"],
                key_prefix=row["key_prefix"],
                name=row["name"],
                description=row["description"],
                scopes=row["scopes"] or [],
                cluster_ids=row["cluster_ids"],
                is_active=row["is_active"],
                expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
                last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
                last_used_ip=row["last_used_ip"],
                usage_count=row["usage_count"] or 0,
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
                created_by=row["created_by"]
            )
            for row in results
        ]
        
    except Exception as e:
        logger.error("Failed to list API keys", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list API keys"
        )


@router.get("/api-keys/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details of a specific API key"""
    try:
        query = """
            SELECT 
                ak.id, ak.key_id, ak.key_prefix, ak.name, ak.description,
                ak.scopes, ak.cluster_ids, ak.is_active, ak.expires_at,
                ak.last_used_at, ak.last_used_ip, ak.usage_count, ak.created_at,
                ak.user_id, u.username as created_by
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.key_id = :key_id
        """
        row = await database.fetch_one(query, {"key_id": key_id})
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # Check permission
        is_admin = current_user.get("role") == "Super Admin" or current_user.get("username") == "admin"
        if not is_admin and row["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return ApiKeyResponse(
            id=row["id"],
            key_id=row["key_id"],
            key_prefix=row["key_prefix"],
            name=row["name"],
            description=row["description"],
            scopes=row["scopes"] or [],
            cluster_ids=row["cluster_ids"],
            is_active=row["is_active"],
            expires_at=row["expires_at"].isoformat() if row["expires_at"] else None,
            last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
            last_used_ip=row["last_used_ip"],
            usage_count=row["usage_count"] or 0,
            created_at=row["created_at"].isoformat() if row["created_at"] else "",
            created_by=row["created_by"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get API key", error=str(e), key_id=key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get API key"
        )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    request: Optional[RevokeApiKeyRequest] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke an API key.
    Once revoked, the key can no longer be used for authentication.
    """
    try:
        # Get the key first
        query = "SELECT id, user_id, is_active FROM api_keys WHERE key_id = :key_id"
        row = await database.fetch_one(query, {"key_id": key_id})
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        # Check permission
        is_admin = current_user.get("role") == "Super Admin" or current_user.get("username") == "admin"
        if not is_admin and row["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        if not row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key is already revoked"
            )
        
        # Revoke the key
        revoke_query = """
            UPDATE api_keys 
            SET is_active = FALSE, 
                revoked_at = NOW(), 
                revoked_by = :revoked_by,
                revoke_reason = :reason
            WHERE key_id = :key_id
        """
        await database.execute(revoke_query, {
            "key_id": key_id,
            "revoked_by": current_user["id"],
            "reason": request.reason if request else None
        })
        
        logger.info(
            "API key revoked",
            key_id=key_id,
            revoked_by=current_user["username"],
            reason=request.reason if request else None
        )
        
        return {"message": "API key revoked successfully", "key_id": key_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to revoke API key", error=str(e), key_id=key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key"
        )


@router.post("/api-keys/verify")
async def verify_api_key_endpoint(
    current_user: dict = Depends(get_current_user)
):
    """
    Verify the current API key (for testing).
    This endpoint requires authentication, so if you reach it, your key is valid.
    """
    return {
        "valid": True,
        "user_id": current_user.get("id"),
        "username": current_user.get("username"),
        "scopes": current_user.get("scopes", []),
        "message": "API key is valid"
    }
