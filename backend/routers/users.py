"""
Users router - User management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
import structlog
from passlib.context import CryptContext

from database.postgresql import database
from utils.jwt_utils import get_current_user, require_permissions

logger = structlog.get_logger()

router = APIRouter()

# Password hashing - bcrypt with auto-truncate for passwords > 72 bytes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)

def hash_password(password: str) -> str:
    # Manually truncate to 72 bytes to avoid bcrypt limit error
    password_truncated = password[:72]
    return pwd_context.hash(password_truncated)

# Pydantic schemas
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: Optional[List[str]] = None  # List of role names

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None

class PasswordChange(BaseModel):
    new_password: str

class UserRolesUpdate(BaseModel):
    roles: List[str]  # List of role names

class UserResponse(BaseModel):
    id: int
    username: str = ""
    email: str = ""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str = ""
    is_active: bool = True
    roles: List[str] = []
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@router.get("/users", response_model=List[UserResponse])
async def get_users(
    is_active: Optional[bool] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get list of users"""
    try:
        query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name,
               u.is_active, u.last_login_at, u.created_at,
               array_agg(r.name) FILTER (WHERE r.name IS NOT NULL) as roles
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE 1=1
        """
        
        params = {}
        
        if is_active is not None:
            query += " AND u.is_active = :is_active"
            params["is_active"] = is_active
        
        query += " GROUP BY u.id ORDER BY u.created_at DESC"
        
        users = await database.fetch_all(query, params)
        
        result = []
        for user in users:
            full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
            result.append(UserResponse(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                first_name=user["first_name"],
                last_name=user["last_name"],
                full_name=full_name,
                is_active=user["is_active"],
                roles=user["roles"] or [],
                last_login_at=user["last_login_at"],
                created_at=user["created_at"]
            ))
        
        return result
        
    except Exception as e:
        logger.error("Get users failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get user by ID"""
    try:
        query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name,
               u.is_active, u.last_login_at, u.created_at,
               array_agg(r.name) FILTER (WHERE r.name IS NOT NULL) as roles
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE u.id = :user_id
        GROUP BY u.id
        """
        
        user = await database.fetch_one(query, {"user_id": user_id})
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            full_name=full_name,
            is_active=user["is_active"],
            roles=user["roles"] or [],
            last_login_at=user["last_login_at"],
            created_at=user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get user failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new user"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin", "platform admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create users"
            )
        
        # Check if username already exists
        existing = await database.fetch_one(
            "SELECT id FROM users WHERE username = :username",
            {"username": user_data.username}
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{user_data.username}' already exists"
            )
        
        # Check if email already exists
        existing_email = await database.fetch_one(
            "SELECT id FROM users WHERE email = :email",
            {"email": user_data.email}
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{user_data.email}' already exists"
            )
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        
        # Insert user
        query = """
        INSERT INTO users (username, email, password_hash, first_name, last_name, is_active, created_at)
        VALUES (:username, :email, :password_hash, :first_name, :last_name, TRUE, NOW())
        RETURNING id, username, email, first_name, last_name, is_active, last_login_at, created_at
        """
        
        user = await database.fetch_one(query, {
            "username": user_data.username,
            "email": user_data.email,
            "password_hash": hashed_password,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name
        })
        
        # Assign roles if provided
        assigned_roles = []
        if user_data.roles:
            for role_name in user_data.roles:
                role = await database.fetch_one(
                    "SELECT id FROM roles WHERE name = :name",
                    {"name": role_name}
                )
                if role:
                    await database.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING",
                        {"user_id": user["id"], "role_id": role["id"]}
                    )
                    assigned_roles.append(role_name)
        
        full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
        
        logger.info("User created", user_id=user["id"], username=user_data.username, created_by=current_user.get("username"))
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            full_name=full_name,
            is_active=user["is_active"],
            roles=assigned_roles,
            last_login_at=user["last_login_at"],
            created_at=user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create user failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a user"""
    try:
        # Check admin permission or self-update (case-insensitive)
        user_roles = current_user.get("roles", [])
        is_admin = any(r.lower() in ["super admin", "admin", "platform admin"] for r in user_roles)
        is_self = current_user.get("user_id") == user_id
        
        if not is_admin and not is_self:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile"
            )
        
        # Check if user exists
        existing = await database.fetch_one(
            "SELECT id FROM users WHERE id = :user_id",
            {"user_id": user_id}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Build update query
        updates = ["updated_at = NOW()"]
        params = {"user_id": user_id}
        
        if user_data.email is not None:
            updates.append("email = :email")
            params["email"] = user_data.email
        
        if user_data.first_name is not None:
            updates.append("first_name = :first_name")
            params["first_name"] = user_data.first_name
        
        if user_data.last_name is not None:
            updates.append("last_name = :last_name")
            params["last_name"] = user_data.last_name
        
        # Only admins can change is_active
        if user_data.is_active is not None and is_admin:
            updates.append("is_active = :is_active")
            params["is_active"] = user_data.is_active
        
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = :user_id"
        await database.execute(query, params)
        
        # Fetch updated user
        user_query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name,
               u.is_active, u.last_login_at, u.created_at,
               array_agg(r.name) FILTER (WHERE r.name IS NOT NULL) as roles
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE u.id = :user_id
        GROUP BY u.id
        """
        user = await database.fetch_one(user_query, {"user_id": user_id})
        
        full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
        
        logger.info("User updated", user_id=user_id, updated_by=current_user.get("username"))
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            full_name=full_name,
            is_active=user["is_active"],
            roles=user["roles"] or [],
            last_login_at=user["last_login_at"],
            created_at=user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update user failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a user"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete users"
            )
        
        # Prevent self-deletion
        if current_user.get("user_id") == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Check if user exists
        existing = await database.fetch_one(
            "SELECT id, username FROM users WHERE id = :user_id",
            {"user_id": user_id}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Delete user roles first
        await database.execute(
            "DELETE FROM user_roles WHERE user_id = :user_id",
            {"user_id": user_id}
        )
        
        # Delete user
        await database.execute(
            "DELETE FROM users WHERE id = :user_id",
            {"user_id": user_id}
        )
        
        logger.info("User deleted", user_id=user_id, username=existing["username"], deleted_by=current_user.get("username"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete user failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


@router.put("/users/{user_id}/password", status_code=status.HTTP_200_OK)
async def change_password(
    user_id: int,
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user)
):
    """Change user password"""
    try:
        # Check admin permission or self-update (case-insensitive)
        user_roles = current_user.get("roles", [])
        is_admin = any(r.lower() in ["super admin", "admin"] for r in user_roles)
        is_self = current_user.get("user_id") == user_id
        
        if not is_admin and not is_self:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only change your own password"
            )
        
        # Check if user exists
        existing = await database.fetch_one(
            "SELECT id FROM users WHERE id = :user_id",
            {"user_id": user_id}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Hash new password
        hashed_password = hash_password(password_data.new_password)
        
        # Update password
        await database.execute(
            "UPDATE users SET password_hash = :password_hash, updated_at = NOW() WHERE id = :user_id",
            {"user_id": user_id, "password_hash": hashed_password}
        )
        
        logger.info("Password changed", user_id=user_id, changed_by=current_user.get("username"))
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Change password failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.put("/users/{user_id}/roles", response_model=UserResponse)
async def update_user_roles(
    user_id: int,
    roles_data: UserRolesUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update user roles"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user roles"
            )
        
        # Check if user exists
        existing = await database.fetch_one(
            "SELECT id FROM users WHERE id = :user_id",
            {"user_id": user_id}
        )
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Remove existing roles
        await database.execute(
            "DELETE FROM user_roles WHERE user_id = :user_id",
            {"user_id": user_id}
        )
        
        # Add new roles
        assigned_roles = []
        for role_name in roles_data.roles:
            role = await database.fetch_one(
                "SELECT id FROM roles WHERE name = :name",
                {"name": role_name}
            )
            if role:
                await database.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)",
                    {"user_id": user_id, "role_id": role["id"]}
                )
                assigned_roles.append(role_name)
        
        # Fetch updated user
        user_query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name,
               u.is_active, u.last_login_at, u.created_at,
               array_agg(r.name) FILTER (WHERE r.name IS NOT NULL) as roles
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE u.id = :user_id
        GROUP BY u.id
        """
        user = await database.fetch_one(user_query, {"user_id": user_id})
        
        full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
        
        logger.info("User roles updated", user_id=user_id, roles=assigned_roles, updated_by=current_user.get("username"))
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            full_name=full_name,
            is_active=user["is_active"],
            roles=user["roles"] or [],
            last_login_at=user["last_login_at"],
            created_at=user["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update user roles failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user roles"
        )


# ============================================
# User Activity Logs Endpoint
# ============================================

@router.get("/user-activity")
async def get_user_activity(
    limit: int = 100,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get user activity logs - comprehensive audit trail of all user actions"""
    try:
        # First try activity_logs table (new comprehensive system)
        # Fall back to login history if activity_logs is empty
        
        # Check if activity_logs table has data
        check_query = "SELECT COUNT(*) as cnt FROM activity_logs"
        check_result = await database.fetch_one(check_query)
        has_activity_logs = check_result and check_result['cnt'] > 0
        
        if has_activity_logs:
            # Use comprehensive activity_logs table
            query = """
            SELECT 
                al.id,
                al.user_id,
                al.username,
                al.action,
                al.resource_type,
                al.resource_id,
                al.resource_name,
                al.details,
                al.ip_address,
                al.status,
                al.error_message,
                al.created_at as timestamp
            FROM activity_logs al
            WHERE 1=1
            """
            params = {}
            
            if action:
                query += " AND al.action = :action"
                params["action"] = action
            
            if resource_type:
                query += " AND al.resource_type = :resource_type"
                params["resource_type"] = resource_type
            
            query += " ORDER BY al.created_at DESC LIMIT :limit"
            params["limit"] = limit
            
            activities = await database.fetch_all(query, params)
            
            result = []
            for activity in activities:
                result.append({
                    "id": activity["id"],
                    "user_id": activity["user_id"],
                    "username": activity["username"],
                    "action": activity["action"],
                    "resource_type": activity["resource_type"],
                    "resource_id": activity["resource_id"],
                    "resource_name": activity["resource_name"],
                    "details": activity["details"] or {},
                    "ip_address": activity["ip_address"],
                    "status": activity["status"],
                    "error_message": activity["error_message"],
                    "timestamp": activity["timestamp"].isoformat() if activity["timestamp"] else None
                })
            
            return {"activities": result}
        
        else:
            # Fall back to login history from users table
            query = """
            SELECT 
                u.id as user_id,
                u.username,
                'login' as action,
                'session' as resource_type,
                CAST(u.id as TEXT) as resource_id,
                '{}'::jsonb as details,
                COALESCE(u.last_login_ip, '0.0.0.0') as ip_address,
                u.last_login_at as timestamp
            FROM users u
            WHERE u.last_login_at IS NOT NULL
            ORDER BY u.last_login_at DESC
            LIMIT :limit
            """
            
            activities = await database.fetch_all(query, {"limit": limit})
            
            result = []
            for i, activity in enumerate(activities):
                if activity["timestamp"]:
                    result.append({
                        "id": i + 1,
                        "user_id": activity["user_id"],
                        "username": activity["username"],
                        "action": activity["action"],
                        "resource_type": activity["resource_type"],
                        "resource_id": activity["resource_id"],
                        "resource_name": None,
                        "details": activity["details"] or {},
                        "ip_address": activity["ip_address"],
                        "status": "success",
                        "error_message": None,
                        "timestamp": activity["timestamp"].isoformat() if activity["timestamp"] else None
                    })
            
            return {"activities": result}
        
    except Exception as e:
        logger.error("Get user activity failed", error=str(e))
        # Return empty list on error instead of failing
        return {"activities": []}
