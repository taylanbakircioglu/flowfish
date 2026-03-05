"""
Report History API endpoints
Track generated reports and their download history
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import structlog
import json

from database.postgresql import database
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/report-history", tags=["Report History"])


# ============================================
# Pydantic Models
# ============================================

class ReportHistoryCreate(BaseModel):
    name: str
    report_type: str
    format: str
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    cluster_id: Optional[int] = None
    analysis_id: Optional[int] = None
    namespace: Optional[str] = None
    filters: Optional[dict] = None
    scheduled_report_id: Optional[int] = None


class ReportHistoryResponse(BaseModel):
    id: int
    name: str
    report_type: str
    format: str
    status: str
    file_size: Optional[int]
    file_size_formatted: str
    file_path: Optional[str]
    cluster_id: Optional[int]
    cluster_name: Optional[str]
    analysis_id: Optional[int]
    analysis_name: Optional[str]
    namespace: Optional[str]
    filters: Optional[dict]
    scheduled_report_id: Optional[int]
    error_message: Optional[str]
    created_by: int
    created_by_username: Optional[str]
    created_at: str
    completed_at: Optional[str]


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=List[ReportHistoryResponse])
async def get_report_history(
    limit: int = 50,
    offset: int = 0,
    report_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get report generation history"""
    try:
        query = """
            SELECT 
                rh.id, rh.name, rh.report_type, rh.format, rh.status,
                rh.file_size, rh.file_path, rh.cluster_id, rh.analysis_id,
                rh.namespace, rh.filters, rh.scheduled_report_id,
                rh.error_message, rh.created_by, rh.created_at, rh.completed_at,
                c.name as cluster_name,
                a.name as analysis_name,
                u.username as created_by_username
            FROM generated_reports rh
            LEFT JOIN clusters c ON rh.cluster_id = c.id
            LEFT JOIN analyses a ON rh.analysis_id = a.id
            LEFT JOIN users u ON rh.created_by = u.id
            WHERE (rh.created_by = :user_id OR :is_admin = true)
        """
        
        params = {
            "user_id": current_user.get('user_id'),
            "is_admin": 'Super Admin' in current_user.get('roles', []) or 'Admin' in current_user.get('roles', [])
        }
        
        if report_type:
            query += " AND rh.report_type = :report_type"
            params["report_type"] = report_type
        
        if status:
            query += " AND rh.status = :status"
            params["status"] = status
        
        query += " ORDER BY rh.created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        rows = await database.fetch_all(query, params)
        
        def format_file_size(size: Optional[int]) -> str:
            if not size:
                return "Unknown"
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            else:
                return f"{size / (1024 * 1024 * 1024):.2f} GB"
        
        result = []
        for row in rows:
            filters = row['filters']
            if isinstance(filters, str):
                filters = json.loads(filters) if filters else None
            
            result.append(ReportHistoryResponse(
                id=row['id'],
                name=row['name'],
                report_type=row['report_type'],
                format=row['format'],
                status=row['status'],
                file_size=row['file_size'],
                file_size_formatted=format_file_size(row['file_size']),
                file_path=row['file_path'],
                cluster_id=row['cluster_id'],
                cluster_name=row['cluster_name'],
                analysis_id=row['analysis_id'],
                analysis_name=row['analysis_name'],
                namespace=row['namespace'],
                filters=filters,
                scheduled_report_id=row['scheduled_report_id'],
                error_message=row['error_message'],
                created_by=row['created_by'],
                created_by_username=row['created_by_username'],
                created_at=str(row['created_at']),
                completed_at=str(row['completed_at']) if row['completed_at'] else None
            ))
        
        return result
        
    except Exception as e:
        logger.error("Failed to get report history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get report history: {str(e)}")


@router.post("", response_model=ReportHistoryResponse)
async def create_report_history(
    report: ReportHistoryCreate,
    current_user: dict = Depends(get_current_user)
):
    """Record a new report generation"""
    try:
        query = """
            INSERT INTO generated_reports 
            (name, report_type, format, status, file_size, file_path,
             cluster_id, analysis_id, namespace, filters, scheduled_report_id,
             created_by, created_at)
            VALUES 
            (:name, :report_type, :format, 'generating', :file_size, :file_path,
             :cluster_id, :analysis_id, :namespace, CAST(:filters AS jsonb), :scheduled_report_id,
             :created_by, NOW())
            RETURNING id, name, report_type, format, status, file_size, file_path,
                      cluster_id, analysis_id, namespace, filters, scheduled_report_id,
                      error_message, created_by, created_at, completed_at
        """
        
        row = await database.fetch_one(query, {
            "name": report.name,
            "report_type": report.report_type,
            "format": report.format,
            "file_size": report.file_size,
            "file_path": report.file_path,
            "cluster_id": report.cluster_id,
            "analysis_id": report.analysis_id,
            "namespace": report.namespace,
            "filters": json.dumps(report.filters) if report.filters else None,
            "scheduled_report_id": report.scheduled_report_id,
            "created_by": current_user.get('user_id')
        })
        
        logger.info("Report history created", report_id=row['id'], name=report.name)
        
        def format_file_size(size: Optional[int]) -> str:
            if not size:
                return "Unknown"
            if size < 1024:
                return f"{size} B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            else:
                return f"{size / (1024 * 1024):.1f} MB"
        
        filters = row['filters']
        if isinstance(filters, str):
            filters = json.loads(filters) if filters else None
        
        return ReportHistoryResponse(
            id=row['id'],
            name=row['name'],
            report_type=row['report_type'],
            format=row['format'],
            status=row['status'],
            file_size=row['file_size'],
            file_size_formatted=format_file_size(row['file_size']),
            file_path=row['file_path'],
            cluster_id=row['cluster_id'],
            cluster_name=None,
            analysis_id=row['analysis_id'],
            analysis_name=None,
            namespace=row['namespace'],
            filters=filters,
            scheduled_report_id=row['scheduled_report_id'],
            error_message=row['error_message'],
            created_by=row['created_by'],
            created_by_username=None,
            created_at=str(row['created_at']),
            completed_at=str(row['completed_at']) if row['completed_at'] else None
        )
        
    except Exception as e:
        logger.error("Failed to create report history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create report history: {str(e)}")


@router.put("/{report_id}/complete")
async def complete_report(
    report_id: int,
    file_size: Optional[int] = None,
    file_path: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Mark a report as completed"""
    try:
        query = """
            UPDATE generated_reports
            SET status = 'ready', 
                file_size = COALESCE(:file_size, file_size),
                file_path = COALESCE(:file_path, file_path),
                completed_at = NOW()
            WHERE id = :id
            RETURNING id, status
        """
        
        row = await database.fetch_one(query, {
            "id": report_id,
            "file_size": file_size,
            "file_path": file_path
        })
        
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        
        logger.info("Report marked as complete", report_id=report_id)
        
        return {"success": True, "status": row['status']}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to complete report", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to complete report: {str(e)}")


@router.put("/{report_id}/fail")
async def fail_report(
    report_id: int,
    error_message: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark a report as failed"""
    try:
        query = """
            UPDATE generated_reports
            SET status = 'failed', 
                error_message = :error_message,
                completed_at = NOW()
            WHERE id = :id
            RETURNING id, status
        """
        
        row = await database.fetch_one(query, {
            "id": report_id,
            "error_message": error_message
        })
        
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        
        logger.info("Report marked as failed", report_id=report_id, error=error_message)
        
        return {"success": True, "status": row['status']}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to mark report as failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to mark report as failed: {str(e)}")


@router.delete("/{report_id}")
async def delete_report_history(
    report_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete a report from history"""
    try:
        # Check ownership
        check_query = "SELECT created_by FROM generated_reports WHERE id = :id"
        existing = await database.fetch_one(check_query, {"id": report_id})
        
        if not existing:
            raise HTTPException(status_code=404, detail="Report not found")
        
        roles = current_user.get('roles', [])
        is_admin = 'Super Admin' in roles or 'Admin' in roles
        
        if existing['created_by'] != current_user.get('user_id') and not is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to delete this report")
        
        await database.execute(
            "DELETE FROM generated_reports WHERE id = :id",
            {"id": report_id}
        )
        
        logger.info("Report history deleted", report_id=report_id, user_id=current_user.get('user_id'))
        
        return {"success": True, "message": "Report deleted from history"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete report history", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete report history: {str(e)}")


@router.get("/stats")
async def get_report_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get report generation statistics"""
    try:
        query = """
            SELECT 
                COUNT(*) as total_reports,
                COUNT(*) FILTER (WHERE status = 'ready') as completed_reports,
                COUNT(*) FILTER (WHERE status = 'failed') as failed_reports,
                COUNT(*) FILTER (WHERE status = 'generating') as pending_reports,
                COALESCE(SUM(file_size) FILTER (WHERE status = 'ready'), 0) as total_size,
                COUNT(DISTINCT report_type) as report_types_used
            FROM generated_reports
            WHERE created_by = :user_id OR :is_admin = true
        """
        
        roles = current_user.get('roles', [])
        is_admin = 'Super Admin' in roles or 'Admin' in roles
        
        row = await database.fetch_one(query, {
            "user_id": current_user.get('user_id'),
            "is_admin": is_admin
        })
        
        total_size = row['total_size'] or 0
        if total_size < 1024 * 1024:
            size_formatted = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:
            size_formatted = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_formatted = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        
        return {
            "total_reports": row['total_reports'],
            "completed_reports": row['completed_reports'],
            "failed_reports": row['failed_reports'],
            "pending_reports": row['pending_reports'],
            "total_size": total_size,
            "total_size_formatted": size_formatted,
            "report_types_used": row['report_types_used']
        }
        
    except Exception as e:
        logger.error("Failed to get report stats", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get report stats: {str(e)}")
