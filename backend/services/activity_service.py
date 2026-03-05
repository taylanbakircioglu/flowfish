"""
Activity Logging Service
Centralized service for logging all user activities
"""

import structlog
from typing import Optional, Dict, Any
from datetime import datetime

from database.postgresql import database

logger = structlog.get_logger()


class ActivityService:
    """Service for logging user activities"""
    
    # Action types
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_START = "start"
    ACTION_STOP = "stop"
    ACTION_EXPORT = "export"
    ACTION_GENERATE = "generate"
    ACTION_SCHEDULE = "schedule"
    ACTION_ASSIGN = "assign"
    ACTION_REVOKE = "revoke"
    
    # Resource types
    RESOURCE_ANALYSIS = "analysis"
    RESOURCE_CLUSTER = "cluster"
    RESOURCE_USER = "user"
    RESOURCE_ROLE = "role"
    RESOURCE_REPORT = "report"
    RESOURCE_SCHEDULE = "schedule"
    RESOURCE_SETTINGS = "settings"
    RESOURCE_SESSION = "session"
    
    @staticmethod
    async def log_activity(
        user_id: Optional[int],
        username: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> Optional[int]:
        """
        Log a user activity
        
        Args:
            user_id: User ID (can be None for system actions)
            username: Username for display
            action: Action type (create, update, delete, start, stop, etc.)
            resource_type: Resource type (analysis, cluster, user, etc.)
            resource_id: Resource identifier
            resource_name: Human-readable resource name
            details: Additional details as JSON
            ip_address: Client IP address
            user_agent: Client user agent
            status: 'success' or 'failed'
            error_message: Error message if failed
            
        Returns:
            Activity log ID or None if failed
        """
        try:
            query = """
                INSERT INTO activity_logs 
                (user_id, username, action, resource_type, resource_id, resource_name,
                 details, ip_address, user_agent, status, error_message, created_at)
                VALUES 
                (:user_id, :username, :action, :resource_type, :resource_id, :resource_name,
                 CAST(:details AS jsonb), :ip_address, :user_agent, :status, :error_message, NOW())
                RETURNING id
            """
            
            import json
            result = await database.fetch_one(query, {
                "user_id": user_id,
                "username": username,
                "action": action,
                "resource_type": resource_type,
                "resource_id": str(resource_id) if resource_id else None,
                "resource_name": resource_name,
                "details": json.dumps(details) if details else "{}",
                "ip_address": ip_address,
                "user_agent": user_agent,
                "status": status,
                "error_message": error_message
            })
            
            log_id = result['id'] if result else None
            
            logger.info("Activity logged",
                       activity_id=log_id,
                       user=username,
                       action=action,
                       resource_type=resource_type,
                       resource_id=resource_id)
            
            return log_id
            
        except Exception as e:
            # Don't fail the main operation if logging fails
            logger.warning("Failed to log activity", 
                          error=str(e),
                          action=action,
                          resource_type=resource_type)
            return None
    
    @staticmethod
    async def get_activities(
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """Get activity logs with optional filters"""
        try:
            query = """
                SELECT 
                    al.id, al.user_id, al.username, al.action, 
                    al.resource_type, al.resource_id, al.resource_name,
                    al.details, al.ip_address, al.user_agent, 
                    al.status, al.error_message, al.created_at
                FROM activity_logs al
                WHERE 1=1
            """
            params = {}
            
            if user_id:
                query += " AND al.user_id = :user_id"
                params["user_id"] = user_id
            
            if action:
                query += " AND al.action = :action"
                params["action"] = action
            
            if resource_type:
                query += " AND al.resource_type = :resource_type"
                params["resource_type"] = resource_type
            
            query += " ORDER BY al.created_at DESC LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset
            
            rows = await database.fetch_all(query, params)
            
            result = []
            for row in rows:
                result.append({
                    "id": row['id'],
                    "user_id": row['user_id'],
                    "username": row['username'],
                    "action": row['action'],
                    "resource_type": row['resource_type'],
                    "resource_id": row['resource_id'],
                    "resource_name": row['resource_name'],
                    "details": row['details'] or {},
                    "ip_address": row['ip_address'],
                    "status": row['status'],
                    "error_message": row['error_message'],
                    "timestamp": row['created_at'].isoformat() if row['created_at'] else None
                })
            
            return result
            
        except Exception as e:
            logger.error("Failed to get activities", error=str(e))
            return []


# Singleton instance
activity_service = ActivityService()
