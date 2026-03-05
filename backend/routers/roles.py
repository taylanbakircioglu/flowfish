"""
Roles router - Role management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import structlog

from database.postgresql import database
from utils.jwt_utils import get_current_user, require_permissions

logger = structlog.get_logger()

router = APIRouter()


# Pydantic schemas
class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = []  # List of permission strings like "clusters.view"


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    permissions: List[str]
    is_system_role: bool
    user_count: int
    created_at: datetime
    updated_at: Optional[datetime]


class RoleListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    user_count: int
    permission_count: int
    is_system_role: bool


# ============================================
# Role Endpoints
# ============================================

@router.get("", response_model=List[RoleListResponse])
async def get_roles(
    current_user: dict = Depends(get_current_user)
):
    """Get list of all roles"""
    try:
        query = """
        SELECT r.id, r.name, r.description, r.is_system_role,
               COUNT(DISTINCT ur.user_id) as user_count,
               COUNT(DISTINCT rp.permission_id) as permission_count
        FROM roles r
        LEFT JOIN user_roles ur ON r.id = ur.role_id
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        GROUP BY r.id
        ORDER BY r.is_system_role DESC, r.name
        """
        
        roles = await database.fetch_all(query)
        
        return [
            RoleListResponse(
                id=role["id"],
                name=role["name"],
                description=role["description"],
                user_count=role["user_count"] or 0,
                permission_count=role["permission_count"] or 0,
                is_system_role=role["is_system_role"] or False
            )
            for role in roles
        ]
        
    except Exception as e:
        logger.error("Get roles failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roles"
        )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get role by ID with full details including permissions"""
    try:
        # Get role basic info
        role_query = """
        SELECT r.id, r.name, r.description, r.is_system_role,
               r.created_at, r.updated_at,
               COUNT(ur.user_id) as user_count
        FROM roles r
        LEFT JOIN user_roles ur ON r.id = ur.role_id
        WHERE r.id = :role_id
        GROUP BY r.id
        """
        
        role = await database.fetch_one(role_query, {"role_id": role_id})
        
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found"
            )
        
        # Get role permissions
        permissions_query = """
        SELECT CONCAT(p.resource, '.', p.action) as permission
        FROM role_permissions rp
        JOIN permissions p ON rp.permission_id = p.id
        WHERE rp.role_id = :role_id
        """
        
        permission_rows = await database.fetch_all(permissions_query, {"role_id": role_id})
        permissions = [row["permission"] for row in permission_rows]
        
        return RoleResponse(
            id=role["id"],
            name=role["name"],
            description=role["description"],
            permissions=permissions,
            is_system_role=role["is_system_role"] or False,
            user_count=role["user_count"] or 0,
            created_at=role["created_at"],
            updated_at=role["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get role failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve role"
        )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new role"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin", "platform admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create roles"
            )
        
        # Check if role name already exists
        existing = await database.fetch_one(
            "SELECT id FROM roles WHERE name = :name",
            {"name": role_data.name}
        )
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{role_data.name}' already exists"
            )
        
        # Insert role
        role_query = """
        INSERT INTO roles (name, description, is_system_role, created_at, updated_at)
        VALUES (:name, :description, FALSE, NOW(), NOW())
        RETURNING id, name, description, is_system_role, created_at, updated_at
        """
        
        role = await database.fetch_one(role_query, {
            "name": role_data.name,
            "description": role_data.description
        })
        
        # Add permissions if provided
        if role_data.permissions:
            for perm_str in role_data.permissions:
                parts = perm_str.split(".")
                if len(parts) == 2:
                    resource, action = parts
                    # Find permission id
                    perm = await database.fetch_one(
                        "SELECT id FROM permissions WHERE resource = :resource AND action = :action",
                        {"resource": resource, "action": action}
                    )
                    if perm:
                        await database.execute(
                            "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id) ON CONFLICT DO NOTHING",
                            {"role_id": role["id"], "perm_id": perm["id"]}
                        )
        
        logger.info("Role created", role_id=role["id"], name=role_data.name, created_by=current_user.get("username"))
        
        return RoleResponse(
            id=role["id"],
            name=role["name"],
            description=role["description"],
            permissions=role_data.permissions or [],
            is_system_role=False,
            user_count=0,
            created_at=role["created_at"],
            updated_at=role["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create role failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role"
        )


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update a role"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin", "platform admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can edit roles"
            )
        
        # Check if role exists
        existing = await database.fetch_one(
            "SELECT id, name, is_system_role FROM roles WHERE id = :role_id",
            {"role_id": role_id}
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found"
            )
        
        # Prevent renaming system roles
        if existing["is_system_role"] and role_data.name and role_data.name != existing["name"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rename system roles"
            )
        
        # Build update query dynamically
        updates = ["updated_at = NOW()"]
        params = {"role_id": role_id}
        
        if role_data.name is not None:
            updates.append("name = :name")
            params["name"] = role_data.name
        
        if role_data.description is not None:
            updates.append("description = :description")
            params["description"] = role_data.description
        
        query = f"""
        UPDATE roles SET {', '.join(updates)}
        WHERE id = :role_id
        RETURNING id, name, description, is_system_role, created_at, updated_at
        """
        
        role = await database.fetch_one(query, params)
        
        # Update permissions if provided
        if role_data.permissions is not None:
            # Remove existing permissions
            await database.execute(
                "DELETE FROM role_permissions WHERE role_id = :role_id",
                {"role_id": role_id}
            )
            
            # Add new permissions
            for perm_str in role_data.permissions:
                parts = perm_str.split(".")
                if len(parts) == 2:
                    resource, action = parts
                    perm = await database.fetch_one(
                        "SELECT id FROM permissions WHERE resource = :resource AND action = :action",
                        {"resource": resource, "action": action}
                    )
                    if perm:
                        await database.execute(
                            "INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id)",
                            {"role_id": role_id, "perm_id": perm["id"]}
                        )
        
        # Get user count
        count_result = await database.fetch_one(
            "SELECT COUNT(*) as count FROM user_roles WHERE role_id = :role_id",
            {"role_id": role_id}
        )
        
        # Get updated permissions
        permissions_query = """
        SELECT CONCAT(p.resource, '.', p.action) as permission
        FROM role_permissions rp
        JOIN permissions p ON rp.permission_id = p.id
        WHERE rp.role_id = :role_id
        """
        permission_rows = await database.fetch_all(permissions_query, {"role_id": role_id})
        permissions = [row["permission"] for row in permission_rows]
        
        logger.info("Role updated", role_id=role_id, updated_by=current_user.get("username"))
        
        return RoleResponse(
            id=role["id"],
            name=role["name"],
            description=role["description"],
            permissions=permissions,
            is_system_role=role["is_system_role"] or False,
            user_count=count_result["count"] if count_result else 0,
            created_at=role["created_at"],
            updated_at=role["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update role failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role"
        )


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a role"""
    try:
        # Check admin permission (case-insensitive)
        user_roles = current_user.get("roles", [])
        if not any(r.lower() in ["super admin", "admin"] for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete roles"
            )
        
        # Check if role exists
        existing = await database.fetch_one(
            "SELECT id, name, is_system_role FROM roles WHERE id = :role_id",
            {"role_id": role_id}
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role {role_id} not found"
            )
        
        # Prevent deleting system roles
        if existing["is_system_role"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete system roles"
            )
        
        # Check if role is assigned to users
        user_count = await database.fetch_one(
            "SELECT COUNT(*) as count FROM user_roles WHERE role_id = :role_id",
            {"role_id": role_id}
        )
        
        if user_count and user_count["count"] > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete role that is assigned to {user_count['count']} user(s)"
            )
        
        # Delete role permissions first
        await database.execute(
            "DELETE FROM role_permissions WHERE role_id = :role_id",
            {"role_id": role_id}
        )
        
        # Delete role
        await database.execute(
            "DELETE FROM roles WHERE id = :role_id",
            {"role_id": role_id}
        )
        
        logger.info("Role deleted", role_id=role_id, deleted_by=current_user.get("username"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete role failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete role"
        )


# ============================================
# User-Role Assignment Endpoints
# ============================================

@router.get("/{role_id}/users")
async def get_role_users(
    role_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get users assigned to a role"""
    try:
        query = """
        SELECT u.id, u.username, u.email, u.first_name, u.last_name
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_id = :role_id
        ORDER BY u.username
        """
        
        users = await database.fetch_all(query, {"role_id": role_id})
        
        return [
            {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or user["username"]
            }
            for user in users
        ]
        
    except Exception as e:
        logger.error("Get role users failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve role users"
        )


# ============================================
# Available Permissions Endpoint
# ============================================

@router.get("/permissions/available")
async def get_available_permissions(
    current_user: dict = Depends(get_current_user)
):
    """Get list of all available permissions"""
    try:
        query = """
        SELECT id, resource, action, description
        FROM permissions
        ORDER BY resource, action
        """
        
        permissions = await database.fetch_all(query)
        
        # Group by resource
        grouped = {}
        for perm in permissions:
            resource = perm["resource"]
            if resource not in grouped:
                grouped[resource] = []
            grouped[resource].append({
                "id": perm["id"],
                "key": f"{perm['resource']}.{perm['action']}",
                "action": perm["action"],
                "description": perm["description"]
            })
        
        return {
            "permissions": [
                {
                    "resource": resource,
                    "actions": actions
                }
                for resource, actions in grouped.items()
            ]
        }
        
    except Exception as e:
        logger.error("Get available permissions failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve permissions"
        )
