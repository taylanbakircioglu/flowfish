"""
Scheduled Reports API endpoints
Manage scheduled report generation and delivery
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
import structlog
import json

from database.postgresql import database
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/scheduled-reports", tags=["Scheduled Reports"])


# ============================================
# Pydantic Models
# ============================================

class ScheduledReportCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    report_types: List[str] = Field(..., min_items=1)
    format: str = Field("CSV", pattern="^(CSV|JSON)$")
    schedule: str = Field(..., pattern="^(daily|weekly|monthly)$")
    time: str = Field(..., pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    email: Optional[EmailStr] = None
    enabled: bool = True
    cluster_id: Optional[int] = None
    analysis_id: Optional[int] = None
    namespace: Optional[str] = None


class ScheduledReportUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    report_types: Optional[List[str]] = None
    format: Optional[str] = Field(None, pattern="^(CSV|JSON)$")
    schedule: Optional[str] = Field(None, pattern="^(daily|weekly|monthly)$")
    time: Optional[str] = Field(None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    email: Optional[EmailStr] = None
    enabled: Optional[bool] = None
    cluster_id: Optional[int] = None
    analysis_id: Optional[int] = None
    namespace: Optional[str] = None


class ScheduledReportResponse(BaseModel):
    id: int
    name: str
    report_types: List[str]
    format: str
    schedule: str
    time: str
    email: Optional[str]
    enabled: bool
    cluster_id: Optional[int]
    analysis_id: Optional[int]
    namespace: Optional[str]
    last_run: Optional[str]
    next_run: str
    created_by: int
    created_at: str
    updated_at: Optional[str]


# ============================================
# Helper Functions
# ============================================

def calculate_next_run(schedule: str, time: str) -> datetime:
    """Calculate next run time based on schedule"""
    from datetime import timedelta
    
    now = datetime.now()
    hour, minute = map(int, time.split(':'))
    
    # Set time for today
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if schedule == 'daily':
        if next_run <= now:
            next_run += timedelta(days=1)
    elif schedule == 'weekly':
        # Next Monday
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and next_run <= now:
            days_until_monday = 7
        next_run += timedelta(days=days_until_monday)
    elif schedule == 'monthly':
        # First day of next month
        if now.month == 12:
            next_run = next_run.replace(year=now.year + 1, month=1, day=1)
        else:
            next_run = next_run.replace(month=now.month + 1, day=1)
    
    return next_run


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=List[ScheduledReportResponse])
async def get_scheduled_reports(
    current_user: dict = Depends(get_current_user)
):
    """Get all scheduled reports for current user"""
    try:
        query = """
            SELECT id, name, report_type, format, schedule, time, email,
                   enabled, cluster_id, analysis_id, namespace,
                   last_run, next_run, created_by, created_at, updated_at
            FROM scheduled_reports
            WHERE created_by = :user_id OR :is_admin = true
            ORDER BY created_at DESC
        """
        
        roles = current_user.get('roles', [])
        is_admin = 'Super Admin' in roles or 'Admin' in roles
        
        rows = await database.fetch_all(query, {
            "user_id": current_user.get('user_id'),
            "is_admin": is_admin
        })
        
        result = []
        for row in rows:
            report_types = row['report_type']  # Column name is singular
            if isinstance(report_types, str):
                report_types = json.loads(report_types)
            elif report_types is None:
                report_types = []
            
            result.append(ScheduledReportResponse(
                id=row['id'],
                name=row['name'],
                report_types=report_types if isinstance(report_types, list) else [report_types] if report_types else [],
                format=row['format'],
                schedule=row['schedule'],
                time=row['time'],
                email=row['email'],
                enabled=row['enabled'],
                cluster_id=row['cluster_id'],
                analysis_id=row['analysis_id'],
                namespace=row['namespace'],
                last_run=str(row['last_run']) if row['last_run'] else None,
                next_run=str(row['next_run']),
                created_by=row['created_by'],
                created_at=str(row['created_at']),
                updated_at=str(row['updated_at']) if row['updated_at'] else None
            ))
        
        return result
        
    except Exception as e:
        logger.error("Failed to get scheduled reports", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get scheduled reports: {str(e)}")


@router.post("", response_model=ScheduledReportResponse)
async def create_scheduled_report(
    report: ScheduledReportCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new scheduled report"""
    try:
        next_run = calculate_next_run(report.schedule, report.time)
        
        query = """
            INSERT INTO scheduled_reports 
            (name, report_type, format, schedule, time, email, enabled,
             cluster_id, analysis_id, namespace, next_run, created_by, created_at)
            VALUES 
            (:name, CAST(:report_type AS jsonb), :format, :schedule, :time, :email, :enabled,
             :cluster_id, :analysis_id, :namespace, :next_run, :created_by, NOW())
            RETURNING id, name, report_type, format, schedule, time, email, enabled,
                      cluster_id, analysis_id, namespace, last_run, next_run, 
                      created_by, created_at, updated_at
        """
        
        row = await database.fetch_one(query, {
            "name": report.name,
            "report_type": json.dumps(report.report_types),
            "format": report.format,
            "schedule": report.schedule,
            "time": report.time,
            "email": report.email,
            "enabled": report.enabled,
            "cluster_id": report.cluster_id,
            "analysis_id": report.analysis_id,
            "namespace": report.namespace,
            "next_run": next_run,
            "created_by": current_user.get('user_id')
        })
        
        logger.info("Scheduled report created", 
                   report_id=row['id'], 
                   name=report.name,
                   user_id=current_user.get('user_id'))
        
        report_types = row['report_type']  # Column name is singular
        if isinstance(report_types, str):
            report_types = json.loads(report_types)
        elif report_types is None:
            report_types = []
        
        return ScheduledReportResponse(
            id=row['id'],
            name=row['name'],
            report_types=report_types if isinstance(report_types, list) else [report_types] if report_types else [],
            format=row['format'],
            schedule=row['schedule'],
            time=row['time'],
            email=row['email'],
            enabled=row['enabled'],
            cluster_id=row['cluster_id'],
            analysis_id=row['analysis_id'],
            namespace=row['namespace'],
            last_run=str(row['last_run']) if row['last_run'] else None,
            next_run=str(row['next_run']),
            created_by=row['created_by'],
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']) if row['updated_at'] else None
        )
        
    except Exception as e:
        logger.error("Failed to create scheduled report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create scheduled report: {str(e)}")


@router.put("/{report_id}", response_model=ScheduledReportResponse)
async def update_scheduled_report(
    report_id: int,
    report: ScheduledReportUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing scheduled report"""
    try:
        # Check ownership
        check_query = "SELECT created_by FROM scheduled_reports WHERE id = :id"
        existing = await database.fetch_one(check_query, {"id": report_id})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Scheduled report not found")
        
        roles = current_user.get('roles', [])
        is_admin = 'Super Admin' in roles or 'Admin' in roles
        
        if existing['created_by'] != current_user.get('user_id') and not is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to update this report")
        
        # Build update query dynamically
        update_fields = []
        params = {"id": report_id}
        
        if report.name is not None:
            update_fields.append("name = :name")
            params["name"] = report.name
        if report.report_types is not None:
            update_fields.append("report_type = CAST(:report_type AS jsonb)")
            params["report_type"] = json.dumps(report.report_types)
        if report.format is not None:
            update_fields.append("format = :format")
            params["format"] = report.format
        if report.schedule is not None:
            update_fields.append("schedule = :schedule")
            params["schedule"] = report.schedule
        if report.time is not None:
            update_fields.append("time = :time")
            params["time"] = report.time
        if report.email is not None:
            update_fields.append("email = :email")
            params["email"] = report.email
        if report.enabled is not None:
            update_fields.append("enabled = :enabled")
            params["enabled"] = report.enabled
        if report.cluster_id is not None:
            update_fields.append("cluster_id = :cluster_id")
            params["cluster_id"] = report.cluster_id
        if report.analysis_id is not None:
            update_fields.append("analysis_id = :analysis_id")
            params["analysis_id"] = report.analysis_id
        if report.namespace is not None:
            update_fields.append("namespace = :namespace")
            params["namespace"] = report.namespace
        
        # Recalculate next_run if schedule or time changed
        if report.schedule is not None or report.time is not None:
            # Get current values
            current = await database.fetch_one(
                "SELECT schedule, time FROM scheduled_reports WHERE id = :id",
                {"id": report_id}
            )
            schedule = report.schedule or current['schedule']
            time = report.time or current['time']
            next_run = calculate_next_run(schedule, time)
            update_fields.append("next_run = :next_run")
            params["next_run"] = next_run
        
        update_fields.append("updated_at = NOW()")
        
        query = f"""
            UPDATE scheduled_reports
            SET {', '.join(update_fields)}
            WHERE id = :id
            RETURNING id, name, report_type, format, schedule, time, email, enabled,
                      cluster_id, analysis_id, namespace, last_run, next_run,
                      created_by, created_at, updated_at
        """
        
        row = await database.fetch_one(query, params)
        
        logger.info("Scheduled report updated", report_id=report_id, user_id=current_user.get('user_id'))
        
        report_types = row['report_type']  # Column name is singular
        if isinstance(report_types, str):
            report_types = json.loads(report_types)
        elif report_types is None:
            report_types = []
        
        return ScheduledReportResponse(
            id=row['id'],
            name=row['name'],
            report_types=report_types if isinstance(report_types, list) else [report_types] if report_types else [],
            format=row['format'],
            schedule=row['schedule'],
            time=row['time'],
            email=row['email'],
            enabled=row['enabled'],
            cluster_id=row['cluster_id'],
            analysis_id=row['analysis_id'],
            namespace=row['namespace'],
            last_run=str(row['last_run']) if row['last_run'] else None,
            next_run=str(row['next_run']),
            created_by=row['created_by'],
            created_at=str(row['created_at']),
            updated_at=str(row['updated_at']) if row['updated_at'] else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update scheduled report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update scheduled report: {str(e)}")


@router.delete("/{report_id}")
async def delete_scheduled_report(
    report_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a scheduled report"""
    try:
        # Check ownership
        check_query = "SELECT created_by FROM scheduled_reports WHERE id = :id"
        existing = await database.fetch_one(check_query, {"id": report_id})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Scheduled report not found")
        
        roles = current_user.get('roles', [])
        is_admin = 'Super Admin' in roles or 'Admin' in roles
        
        if existing['created_by'] != current_user.get('user_id') and not is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to delete this report")
        
        await database.execute(
            "DELETE FROM scheduled_reports WHERE id = :id",
            {"id": report_id}
        )
        
        logger.info("Scheduled report deleted", report_id=report_id, user_id=current_user.get('user_id'))
        
        return {"success": True, "message": "Scheduled report deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete scheduled report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete scheduled report: {str(e)}")


@router.post("/{report_id}/toggle")
async def toggle_scheduled_report(
    report_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Toggle enabled/disabled status of a scheduled report"""
    try:
        query = """
            UPDATE scheduled_reports
            SET enabled = NOT enabled, updated_at = NOW()
            WHERE id = :id
            RETURNING id, enabled
        """
        
        row = await database.fetch_one(query, {"id": report_id})
        
        if not row:
            raise HTTPException(status_code=404, detail="Scheduled report not found")
        
        logger.info("Scheduled report toggled", 
                   report_id=report_id, 
                   enabled=row['enabled'],
                   user_id=current_user.get('user_id'))
        
        return {"success": True, "enabled": row['enabled']}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to toggle scheduled report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to toggle scheduled report: {str(e)}")
