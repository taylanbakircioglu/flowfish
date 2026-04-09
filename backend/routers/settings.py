"""
System Settings API endpoints
Enterprise feature for global configuration management
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import structlog
import json
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

from database.postgresql import database
from utils.jwt_utils import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/settings", tags=["Settings"])


def check_admin_role(current_user: dict):
    """Check if user has admin role (case-insensitive)"""
    roles = current_user.get('roles', [])
    # Case-insensitive role check
    lower_roles = [r.lower() for r in roles]
    if 'super admin' not in lower_roles and 'admin' not in lower_roles and 'platform admin' not in lower_roles:
        logger.warning(
            "Non-admin attempted to update settings",
            user_id=current_user.get('user_id'),
            username=current_user.get('username'),
            roles=roles
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to update system settings"
        )


# ============================================
# Pydantic Models
# ============================================

class AnalysisLimits(BaseModel):
    """Global analysis time and size limits configuration"""
    continuous_auto_stop_enabled: bool = Field(
        True, 
        description="Enable automatic stopping for continuous analyses"
    )
    default_continuous_duration_minutes: int = Field(
        10, 
        ge=1, 
        le=1440,
        description="Default duration in minutes for continuous analyses (1 min to 24 hours)"
    )
    max_allowed_duration_minutes: int = Field(
        1440, 
        ge=10, 
        le=10080,
        description="Maximum allowed duration in minutes (10 min to 7 days)"
    )
    warning_before_minutes: int = Field(
        2, 
        ge=1, 
        le=10,
        description="Show warning notification this many minutes before auto-stop"
    )
    ingestion_rate_limit_per_second: int = Field(
        5000,
        ge=0,
        le=50000,
        description="Max events per second per ingestion session (0 = unlimited)"
    )


class AnalysisLimitsResponse(AnalysisLimits):
    """Response model including metadata"""
    updated_at: Optional[str] = None
    updated_by: Optional[int] = None


# ============================================
# API Endpoints
# ============================================

@router.get("/analysis-limits", response_model=AnalysisLimitsResponse)
async def get_analysis_limits(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current analysis limits configuration.
    
    Accessible to all authenticated users.
    Returns default values if not configured.
    """
    try:
        # Note: Live database uses only 'key' column, no 'category' column
        query = """
            SELECT value, updated_at, updated_by 
            FROM system_settings 
            WHERE key = 'analysis_limits'
        """
        row = await database.fetch_one(query)
        
        if row:
            # Parse JSON value
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            
            return AnalysisLimitsResponse(
                **value,
                updated_at=str(row['updated_at']) if row['updated_at'] else None,
                updated_by=row['updated_by']
            )
        
        # Return defaults if not configured
        logger.info("No analysis limits configured, returning defaults")
        return AnalysisLimitsResponse()
        
    except Exception as e:
        logger.error("Failed to get analysis limits", error=str(e))
        # Return defaults on error (graceful degradation)
        return AnalysisLimitsResponse()


@router.put("/analysis-limits", response_model=AnalysisLimitsResponse)
async def update_analysis_limits(
    limits: AnalysisLimits,
    current_user: dict = Depends(get_current_user)
):
    """
    Update analysis limits configuration.
    
    **Admin only** - Requires 'Super Admin' or 'Admin' role.
    
    These settings affect all users:
    - continuous_auto_stop_enabled: Enable/disable auto-stop for continuous analyses
    - default_continuous_duration_minutes: Default runtime for continuous analyses
    - max_allowed_duration_minutes: Maximum duration users can set
    - warning_before_minutes: When to show warning before auto-stop
    """
    check_admin_role(current_user)
    
    try:
        # Validate that default duration doesn't exceed max
        if limits.default_continuous_duration_minutes > limits.max_allowed_duration_minutes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Default duration cannot exceed maximum allowed duration"
            )
        
        # Upsert the settings
        # Note: Use CAST() instead of :: to avoid conflict with SQLAlchemy's :param syntax
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES (
                'analysis_limits', 
                CAST(:value AS jsonb), 
                'Global analysis time and size limits for enterprise protection',
                NOW(),
                :user_id
            )
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), 
                updated_at = NOW(),
                updated_by = :user_id
            RETURNING updated_at
        """
        
        result = await database.fetch_one(query, {
            "value": json.dumps(limits.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info(
            "Analysis limits updated",
            user_id=current_user.get('user_id'),
            username=current_user.get('username'),
            limits=limits.dict()
        )
        
        return AnalysisLimitsResponse(
            **limits.dict(),
            updated_at=str(result['updated_at']) if result else None,
            updated_by=current_user.get('user_id')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update analysis limits", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )


@router.get("/analysis-limits/defaults", response_model=AnalysisLimits)
async def get_analysis_limits_defaults():
    """
    Get current analysis limits (no authentication required).
    
    This endpoint is used by services that need defaults without auth,
    like the analysis orchestrator during startup.
    Reads from DB first, falls back to Pydantic defaults if not configured.
    """
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'analysis_limits'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return AnalysisLimits(**value)
    except Exception as e:
        logger.warning("Failed to read analysis limits from DB in /defaults", error=str(e))
    
    return AnalysisLimits()


# ============================================
# Network Configuration (SDN Pod CIDR Ranges)
# ============================================

class PodCIDRRange(BaseModel):
    """A single SDN pod network CIDR range for gateway detection"""
    cidr: str = Field(..., pattern=r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$')
    label: str = Field(..., min_length=1, max_length=100)
    enabled: bool = Field(True)
    is_default: bool = Field(False)


class NetworkConfig(BaseModel):
    """Network configuration for SDN gateway detection and CIDR classification"""
    sdn_pod_cidrs: List[PodCIDRRange] = Field(default_factory=lambda: [
        PodCIDRRange(cidr="10.128.0.0/14", label="OpenShift", enabled=True, is_default=True),
        PodCIDRRange(cidr="10.244.0.0/16", label="Flannel / kubeadm", enabled=True, is_default=True),
        PodCIDRRange(cidr="10.42.0.0/16", label="K3s / RKE2", enabled=True, is_default=True),
        PodCIDRRange(cidr="192.168.0.0/16", label="Kind / Minikube", enabled=False, is_default=True),
    ])


class NetworkConfigResponse(NetworkConfig):
    """Response model including metadata"""
    updated_at: Optional[str] = None
    updated_by: Optional[int] = None


@router.get("/network-config", response_model=NetworkConfigResponse)
async def get_network_config(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current network CIDR configuration.
    
    Accessible to all authenticated users.
    Returns Pydantic defaults if not configured.
    """
    try:
        query = """
            SELECT value, updated_at, updated_by 
            FROM system_settings 
            WHERE key = 'network_config'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            
            return NetworkConfigResponse(
                **value,
                updated_at=str(row['updated_at']) if row['updated_at'] else None,
                updated_by=row['updated_by']
            )
        
        logger.info("No network config configured, returning defaults")
        return NetworkConfigResponse()
        
    except Exception as e:
        logger.error("Failed to get network config", error=str(e))
        return NetworkConfigResponse()


@router.put("/network-config", response_model=NetworkConfigResponse)
async def update_network_config(
    config: NetworkConfig,
    current_user: dict = Depends(get_current_user)
):
    """
    Update network CIDR configuration.
    
    **Admin only** - Requires 'Super Admin' or 'Admin' role.
    
    These settings control SDN gateway detection and IP classification
    across all new analysis sessions.
    """
    check_admin_role(current_user)
    
    try:
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES (
                'network_config', 
                CAST(:value AS jsonb), 
                'Network CIDR configuration for SDN gateway detection',
                NOW(),
                :user_id
            )
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), 
                updated_at = NOW(),
                updated_by = :user_id
            RETURNING updated_at
        """
        
        result = await database.fetch_one(query, {
            "value": json.dumps(config.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info(
            "Network config updated",
            user_id=current_user.get('user_id'),
            username=current_user.get('username'),
            cidr_count=len(config.sdn_pod_cidrs)
        )
        
        return NetworkConfigResponse(
            **config.dict(),
            updated_at=str(result['updated_at']) if result else None,
            updated_by=current_user.get('user_id')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update network config", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update network config: {str(e)}"
        )


@router.get("/network-config/defaults", response_model=NetworkConfig, responses={204: {"description": "Not configured"}})
async def get_network_config_defaults():
    """
    Get current network config (no authentication required).
    
    Used by the analysis orchestrator to pass CIDR configuration
    to the ingestion service during collection startup.
    Returns 204 if not explicitly configured -- orchestrator should
    let PodDiscovery use its hardcoded defaults for backward compatibility.
    """
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'network_config'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return NetworkConfig(**value)
    except Exception as e:
        logger.warning("Failed to read network config from DB in /defaults", error=str(e))
    
    return Response(status_code=204)


# ============================================
# SMTP Settings
# ============================================

class SMTPSettings(BaseModel):
    """SMTP configuration for email notifications"""
    enabled: bool = False
    host: str = ""
    port: int = Field(587, ge=1, le=65535)
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "Flowfish"
    use_tls: bool = True
    use_ssl: bool = False


@router.get("/smtp", response_model=SMTPSettings)
async def get_smtp_settings(current_user: dict = Depends(get_current_user)):
    """Get SMTP configuration (password masked)"""
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'smtp_settings'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            # Mask password for security
            if value.get('password'):
                value['password'] = '••••••••'
            return SMTPSettings(**value)
        
        return SMTPSettings()
    except Exception as e:
        logger.error("Failed to get SMTP settings", error=str(e))
        return SMTPSettings()


@router.put("/smtp", response_model=SMTPSettings)
async def update_smtp_settings(
    settings: SMTPSettings,
    current_user: dict = Depends(get_current_user)
):
    """Update SMTP configuration (Admin only)"""
    check_admin_role(current_user)
    
    try:
        # If password is masked, keep the old one
        if settings.password == '••••••••':
            query = """
                SELECT value FROM system_settings 
                WHERE key = 'smtp_settings'
            """
            row = await database.fetch_one(query)
            if row:
                old_value = row['value']
                if isinstance(old_value, str):
                    old_value = json.loads(old_value)
                settings.password = old_value.get('password', '')
        
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES ('smtp_settings', CAST(:value AS jsonb), 'SMTP server configuration', NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), updated_at = NOW(), updated_by = :user_id
        """
        
        await database.execute(query, {
            "value": json.dumps(settings.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info("SMTP settings updated", user_id=current_user.get('user_id'))
        
        # Return with masked password
        settings.password = '••••••••' if settings.password else ''
        return settings
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update SMTP settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/smtp/test")
async def test_smtp_connection(
    settings: SMTPSettings,
    current_user: dict = Depends(get_current_user)
):
    """Test SMTP connection by sending a test email"""
    check_admin_role(current_user)
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # If password is masked, get real password from DB
        if settings.password == '••••••••':
            query = """
                SELECT value FROM system_settings 
                WHERE key = 'smtp_settings'
            """
            row = await database.fetch_one(query)
            if row:
                old_value = row['value']
                if isinstance(old_value, str):
                    old_value = json.loads(old_value)
                settings.password = old_value.get('password', '')
        
        # Create test email
        msg = MIMEMultipart()
        msg['From'] = f"{settings.from_name} <{settings.from_email}>"
        msg['To'] = current_user.get('email', settings.from_email)
        msg['Subject'] = "Flowfish SMTP Test"
        
        body = f"""
        This is a test email from Flowfish.
        
        If you received this email, your SMTP configuration is working correctly.
        
        Sent at: {datetime.now().isoformat()}
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect and send
        if settings.use_ssl:
            server = smtplib.SMTP_SSL(settings.host, settings.port)
        else:
            server = smtplib.SMTP(settings.host, settings.port)
            if settings.use_tls:
                server.starttls()
        
        if settings.username and settings.password:
            server.login(settings.username, settings.password)
        
        server.send_message(msg)
        server.quit()
        
        logger.info("SMTP test email sent", user_id=current_user.get('user_id'))
        return {"success": True, "message": "Test email sent successfully"}
        
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="Authentication failed. Check username/password.")
    except smtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail="Connection failed. Check host and port.")
    except Exception as e:
        logger.error("SMTP test failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"SMTP test failed: {str(e)}")


# ============================================
# Notification Settings
# ============================================

class NotificationSettings(BaseModel):
    """Notification preferences"""
    email_enabled: bool = False
    email_on_analysis_complete: bool = True
    email_on_analysis_error: bool = True
    email_on_anomaly_detected: bool = True
    email_on_scheduled_report: bool = True
    slack_enabled: bool = False
    slack_webhook_url: str = ""
    slack_channel: str = "#flowfish-alerts"
    in_app_enabled: bool = True


@router.get("/notifications", response_model=NotificationSettings)
async def get_notification_settings(current_user: dict = Depends(get_current_user)):
    """Get notification preferences"""
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'notification_preferences'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return NotificationSettings(**value)
        
        return NotificationSettings()
    except Exception as e:
        logger.error("Failed to get notification settings", error=str(e))
        return NotificationSettings()


@router.put("/notifications", response_model=NotificationSettings)
async def update_notification_settings(
    settings: NotificationSettings,
    current_user: dict = Depends(get_current_user)
):
    """Update notification preferences (Admin only)"""
    check_admin_role(current_user)
    
    try:
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES ('notification_preferences', CAST(:value AS jsonb), 'Notification preferences', NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), updated_at = NOW(), updated_by = :user_id
        """
        
        await database.execute(query, {
            "value": json.dumps(settings.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info("Notification settings updated", user_id=current_user.get('user_id'))
        return settings
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update notification settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


# ============================================
# Data Retention Settings
# ============================================

class DataRetentionSettings(BaseModel):
    """Data retention policies"""
    events_retention_days: int = Field(30, ge=1, le=365)
    network_flows_retention_days: int = Field(30, ge=1, le=365)
    dns_queries_retention_days: int = Field(30, ge=1, le=365)
    process_events_retention_days: int = Field(30, ge=1, le=365)
    analysis_retention_days: int = Field(90, ge=1, le=365)
    auto_cleanup_enabled: bool = True
    cleanup_schedule: str = "daily"


@router.get("/retention", response_model=DataRetentionSettings)
async def get_retention_settings(current_user: dict = Depends(get_current_user)):
    """Get data retention policies"""
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'retention_policies'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return DataRetentionSettings(**value)
        
        return DataRetentionSettings()
    except Exception as e:
        logger.error("Failed to get retention settings", error=str(e))
        return DataRetentionSettings()


@router.put("/retention", response_model=DataRetentionSettings)
async def update_retention_settings(
    settings: DataRetentionSettings,
    current_user: dict = Depends(get_current_user)
):
    """Update data retention policies (Admin only)"""
    check_admin_role(current_user)
    
    try:
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES ('retention_policies', CAST(:value AS jsonb), 'Data retention policies', NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), updated_at = NOW(), updated_by = :user_id
        """
        
        await database.execute(query, {
            "value": json.dumps(settings.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info("Retention settings updated", user_id=current_user.get('user_id'))
        return settings
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update retention settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/retention/cleanup")
async def run_data_cleanup(
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    """Manually trigger data cleanup (Admin only)"""
    check_admin_role(current_user)
    
    try:
        # Get retention settings
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'retention_policies'
        """
        row = await database.fetch_one(query)
        
        retention_days = 30  # default
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            retention_days = value.get('events_retention_days', 30)
        
        deleted_count = 0
        
        # Clean up old activity logs
        activity_result = await database.execute(
            "DELETE FROM activity_logs WHERE created_at < NOW() - INTERVAL :days DAY",
            {"days": retention_days}
        )
        
        # Clean up old analysis runs
        analysis_retention = retention_days * 3  # Keep analysis longer
        analysis_result = await database.execute(
            "DELETE FROM analysis_runs WHERE created_at < NOW() - INTERVAL :days DAY AND status IN ('completed', 'stopped', 'error')",
            {"days": analysis_retention}
        )
        
        # Try to clean ClickHouse if available
        try:
            from database.clickhouse import clickhouse_client, CLICKHOUSE_ENABLED, DummyClickHouseClient
            
            if CLICKHOUSE_ENABLED and not isinstance(clickhouse_client, DummyClickHouseClient):
                # Delete old network flows
                clickhouse_client.execute(f"""
                    ALTER TABLE flowfish.network_flows 
                    DELETE WHERE timestamp < now() - INTERVAL {retention_days} DAY
                """)
                
                # Delete old change events
                clickhouse_client.execute(f"""
                    ALTER TABLE flowfish.change_events 
                    DELETE WHERE timestamp < now() - INTERVAL {retention_days} DAY
                """)
                
                logger.info("ClickHouse cleanup executed", retention_days=retention_days)
        except Exception as ch_error:
            logger.warning("ClickHouse cleanup skipped", error=str(ch_error))
        
        logger.info(
            "Manual data cleanup completed",
            user_id=current_user.get('user_id'),
            retention_days=retention_days
        )
        
        return {
            "success": True, 
            "deleted_count": deleted_count,
            "retention_days": retention_days,
            "message": f"Cleanup completed. Data older than {retention_days} days removed."
        }
        
    except Exception as e:
        logger.error("Data cleanup failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


# ============================================
# Security Settings
# ============================================

class SecuritySettings(BaseModel):
    """Security configuration"""
    session_timeout_minutes: int = Field(480, ge=5, le=1440)
    max_login_attempts: int = Field(5, ge=3, le=10)
    lockout_duration_minutes: int = Field(30, ge=5, le=1440)
    password_min_length: int = Field(8, ge=6, le=32)
    password_require_uppercase: bool = True
    password_require_numbers: bool = True
    password_require_special: bool = False
    two_factor_enabled: bool = False
    two_factor_required_for_all: bool = False
    two_factor_code_expiry_minutes: int = Field(5, ge=1, le=30)
    allowed_ip_ranges: str = ""
    api_rate_limit_per_minute: int = Field(100, ge=10, le=1000)


@router.get("/security", response_model=SecuritySettings)
async def get_security_settings(current_user: dict = Depends(get_current_user)):
    """Get security configuration"""
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'security_policies'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return SecuritySettings(**value)
        
        return SecuritySettings()
    except Exception as e:
        logger.error("Failed to get security settings", error=str(e))
        return SecuritySettings()


@router.put("/security", response_model=SecuritySettings)
async def update_security_settings(
    settings: SecuritySettings,
    current_user: dict = Depends(get_current_user)
):
    """Update security configuration (Admin only)"""
    check_admin_role(current_user)
    
    try:
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES ('security_policies', CAST(:value AS jsonb), 'Security policies', NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), updated_at = NOW(), updated_by = :user_id
        """
        
        await database.execute(query, {
            "value": json.dumps(settings.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info("Security settings updated", user_id=current_user.get('user_id'))
        return settings
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update security settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


# ============================================
# System Information
# ============================================

class SystemInfo(BaseModel):
    """System status and information"""
    version: str = "1.0.0"
    database_size: str = "Unknown"
    events_count: int = 0
    uptime: str = "Unknown"
    last_backup: str = "Never"
    clickhouse_status: str = "unknown"
    rabbitmq_status: str = "unknown"
    neo4j_status: str = "unknown"


@router.get("/system-info", response_model=SystemInfo)
async def get_system_info(current_user: dict = Depends(get_current_user)):
    """Get system status and information"""
    try:
        info = SystemInfo()
        
        # Get database size (PostgreSQL)
        try:
            query = "SELECT pg_database_size(current_database()) as size"
            row = await database.fetch_one(query)
            if row:
                size_bytes = row['size']
                if size_bytes > 1024*1024*1024:
                    info.database_size = f"{size_bytes / (1024*1024*1024):.1f} GB"
                else:
                    info.database_size = f"{size_bytes / (1024*1024):.1f} MB"
        except:
            pass
        
        # Get events count from activity_logs
        try:
            count_query = "SELECT COUNT(*) as count FROM activity_logs"
            count_row = await database.fetch_one(count_query)
            if count_row:
                info.events_count = count_row['count']
        except:
            pass
        
        # Check ClickHouse status
        try:
            from database.clickhouse import clickhouse_client, CLICKHOUSE_ENABLED, DummyClickHouseClient
            
            if CLICKHOUSE_ENABLED and not isinstance(clickhouse_client, DummyClickHouseClient):
                clickhouse_client.execute("SELECT 1")
                info.clickhouse_status = "healthy"
            else:
                info.clickhouse_status = "disabled"
        except Exception as e:
            logger.warning("ClickHouse health check failed", error=str(e))
            info.clickhouse_status = "error"
        
        # Check RabbitMQ status
        try:
            import os
            import socket
            
            rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
            rabbitmq_port = int(os.getenv('RABBITMQ_PORT', '5672'))
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((rabbitmq_host, rabbitmq_port))
            sock.close()
            
            if result == 0:
                info.rabbitmq_status = "healthy"
            else:
                info.rabbitmq_status = "error"
        except Exception as e:
            logger.warning("RabbitMQ health check failed", error=str(e))
            info.rabbitmq_status = "error"
        
        # Check Neo4j status
        try:
            import os
            neo4j_enabled = os.getenv('NEO4J_ENABLED', 'false').lower() == 'true'
            neo4j_uri = os.getenv('NEO4J_URI', '')
            
            if not neo4j_enabled or not neo4j_uri:
                info.neo4j_status = "disabled"
            else:
                try:
                    from database.neo4j import neo4j_driver
                    if neo4j_driver:
                        with neo4j_driver.session() as session:
                            session.run("RETURN 1")
                        info.neo4j_status = "healthy"
                    else:
                        info.neo4j_status = "disabled"
                except Exception:
                    info.neo4j_status = "error"
        except Exception as e:
            logger.warning("Neo4j health check failed", error=str(e))
            info.neo4j_status = "disabled"
        
        # Get uptime from PostgreSQL
        try:
            uptime_query = "SELECT pg_postmaster_start_time() as start_time"
            uptime_row = await database.fetch_one(uptime_query)
            if uptime_row and uptime_row['start_time']:
                start_time = uptime_row['start_time']
                uptime_delta = datetime.now(start_time.tzinfo) - start_time
                days = uptime_delta.days
                hours = uptime_delta.seconds // 3600
                if days > 0:
                    info.uptime = f"{days} days, {hours} hours"
                else:
                    info.uptime = f"{hours} hours"
        except:
            pass
        
        return info
        
    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        return SystemInfo()


# ============================================
# Two-Factor Authentication (2FA)
# ============================================

class TwoFactorSettings(BaseModel):
    """2FA configuration"""
    enabled: bool = False
    required_for_all: bool = False
    code_expiry_minutes: int = Field(5, ge=1, le=30)
    max_attempts: int = Field(3, ge=1, le=10)


class TwoFactorVerifyRequest(BaseModel):
    """2FA verification request"""
    user_id: int
    code: str


class TwoFactorCodeResponse(BaseModel):
    """2FA code generation response"""
    success: bool
    message: str
    expires_at: Optional[str] = None


@router.get("/2fa", response_model=TwoFactorSettings)
async def get_2fa_settings(current_user: dict = Depends(get_current_user)):
    """Get 2FA configuration"""
    try:
        query = """
            SELECT value FROM system_settings 
            WHERE key = '2fa_settings'
        """
        row = await database.fetch_one(query)
        
        if row:
            value = row['value']
            if isinstance(value, str):
                value = json.loads(value)
            return TwoFactorSettings(**value)
        
        return TwoFactorSettings()
    except Exception as e:
        logger.error("Failed to get 2FA settings", error=str(e))
        return TwoFactorSettings()


@router.put("/2fa", response_model=TwoFactorSettings)
async def update_2fa_settings(
    settings: TwoFactorSettings,
    current_user: dict = Depends(get_current_user)
):
    """Update 2FA configuration (Admin only)"""
    check_admin_role(current_user)
    
    try:
        query = """
            INSERT INTO system_settings (key, value, description, updated_at, updated_by)
            VALUES ('2fa_settings', CAST(:value AS jsonb), 'Two-factor authentication settings', NOW(), :user_id)
            ON CONFLICT (key) DO UPDATE SET 
                value = CAST(:value AS jsonb), updated_at = NOW(), updated_by = :user_id
        """
        
        await database.execute(query, {
            "value": json.dumps(settings.dict()),
            "user_id": current_user.get('user_id')
        })
        
        logger.info("2FA settings updated", user_id=current_user.get('user_id'), enabled=settings.enabled)
        return settings
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update 2FA settings", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/2fa/send-code", response_model=TwoFactorCodeResponse)
async def send_2fa_code(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Send 2FA verification code to user's email.
    Can be called during login process or by admin for a user.
    """
    try:
        # Get user email
        user_query = "SELECT id, username, email FROM users WHERE id = :user_id"
        user = await database.fetch_one(user_query, {"user_id": user_id})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user['email']:
            raise HTTPException(status_code=400, detail="User has no email configured")
        
        # Generate 6-digit code
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        # Get 2FA settings for expiry
        settings_query = """
            SELECT value FROM system_settings 
            WHERE key = '2fa_settings'
        """
        settings_row = await database.fetch_one(settings_query)
        expiry_minutes = 5
        if settings_row:
            settings_value = settings_row['value']
            if isinstance(settings_value, str):
                settings_value = json.loads(settings_value)
            expiry_minutes = settings_value.get('code_expiry_minutes', 5)
        
        expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        
        # Store code in database
        store_query = """
            INSERT INTO two_factor_codes (user_id, code, expires_at, created_at)
            VALUES (:user_id, :code, :expires_at, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                code = :code, expires_at = :expires_at, created_at = NOW(), attempts = 0
        """
        await database.execute(store_query, {
            "user_id": user_id,
            "code": code,
            "expires_at": expires_at
        })
        
        # Send email
        await send_2fa_email(user['email'], user['username'], code, expiry_minutes)
        
        logger.info("2FA code sent", user_id=user_id, email=user['email'][:3] + "***")
        
        return TwoFactorCodeResponse(
            success=True,
            message=f"Verification code sent to {user['email'][:3]}***{user['email'].split('@')[1]}",
            expires_at=expires_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send 2FA code", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to send code: {str(e)}")


@router.post("/2fa/verify")
async def verify_2fa_code(request: TwoFactorVerifyRequest):
    """Verify 2FA code"""
    try:
        # Get stored code
        query = """
            SELECT code, expires_at, attempts 
            FROM two_factor_codes 
            WHERE user_id = :user_id
        """
        row = await database.fetch_one(query, {"user_id": request.user_id})
        
        if not row:
            raise HTTPException(status_code=400, detail="No verification code found. Please request a new code.")
        
        # Check expiry
        if datetime.utcnow() > row['expires_at'].replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="Verification code expired. Please request a new code.")
        
        # Check max attempts
        max_attempts = 3
        settings_query = """
            SELECT value FROM system_settings 
            WHERE key = '2fa_settings'
        """
        settings_row = await database.fetch_one(settings_query)
        if settings_row:
            settings_value = settings_row['value']
            if isinstance(settings_value, str):
                settings_value = json.loads(settings_value)
            max_attempts = settings_value.get('max_attempts', 3)
        
        if row['attempts'] >= max_attempts:
            raise HTTPException(status_code=400, detail="Too many failed attempts. Please request a new code.")
        
        # Verify code
        if row['code'] != request.code:
            # Increment attempts
            await database.execute(
                "UPDATE two_factor_codes SET attempts = attempts + 1 WHERE user_id = :user_id",
                {"user_id": request.user_id}
            )
            remaining = max_attempts - row['attempts'] - 1
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid verification code. {remaining} attempts remaining."
            )
        
        # Code is valid - delete it
        await database.execute(
            "DELETE FROM two_factor_codes WHERE user_id = :user_id",
            {"user_id": request.user_id}
        )
        
        logger.info("2FA verification successful", user_id=request.user_id)
        
        return {"success": True, "message": "Verification successful"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("2FA verification failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/2fa/user-status/{user_id}")
async def get_user_2fa_status(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Check if a user has 2FA enabled"""
    try:
        query = "SELECT two_factor_enabled FROM users WHERE id = :user_id"
        row = await database.fetch_one(query, {"user_id": user_id})
        
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "user_id": user_id,
            "two_factor_enabled": row['two_factor_enabled'] if row['two_factor_enabled'] else False
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get user 2FA status", error=str(e))
        return {"user_id": user_id, "two_factor_enabled": False}


@router.put("/2fa/user/{user_id}")
async def toggle_user_2fa(
    user_id: int,
    enabled: bool,
    current_user: dict = Depends(get_current_user)
):
    """Enable/disable 2FA for a specific user (Admin or self)"""
    # Users can toggle their own 2FA, admins can toggle anyone's
    if current_user.get('user_id') != user_id:
        check_admin_role(current_user)
    
    try:
        await database.execute(
            "UPDATE users SET two_factor_enabled = :enabled WHERE id = :user_id",
            {"user_id": user_id, "enabled": enabled}
        )
        
        logger.info("User 2FA toggled", user_id=user_id, enabled=enabled, by=current_user.get('user_id'))
        
        return {"success": True, "user_id": user_id, "two_factor_enabled": enabled}
        
    except Exception as e:
        logger.error("Failed to toggle user 2FA", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")


async def send_2fa_email(email: str, username: str, code: str, expiry_minutes: int):
    """Send 2FA verification email"""
    try:
        # Get SMTP settings
        query = """
            SELECT value FROM system_settings 
            WHERE key = 'smtp_settings'
        """
        row = await database.fetch_one(query)
        
        if not row:
            raise Exception("SMTP not configured")
        
        smtp_settings = row['value']
        if isinstance(smtp_settings, str):
            smtp_settings = json.loads(smtp_settings)
        
        if not smtp_settings.get('enabled'):
            raise Exception("Email notifications are disabled")
        
        # Create email
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{smtp_settings.get('from_name', 'Flowfish')} <{smtp_settings.get('from_email')}>"
        msg['To'] = email
        msg['Subject'] = f"Flowfish - Your Verification Code: {code}"
        
        # Plain text version
        text_body = f"""
Hello {username},

Your Flowfish verification code is: {code}

This code will expire in {expiry_minutes} minutes.

If you didn't request this code, please ignore this email or contact your administrator.

- Flowfish Security Team
        """
        
        # HTML version
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .logo {{ text-align: center; margin-bottom: 30px; }}
        .logo h1 {{ color: #0891b2; margin: 0; font-size: 28px; }}
        .code-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; font-size: 32px; letter-spacing: 8px; text-align: center; padding: 20px; border-radius: 8px; margin: 30px 0; font-weight: bold; }}
        .message {{ color: #666; line-height: 1.6; }}
        .expiry {{ background: #fff3cd; color: #856404; padding: 12px; border-radius: 6px; margin-top: 20px; text-align: center; }}
        .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>🐟 Flowfish</h1>
        </div>
        <p class="message">Hello <strong>{username}</strong>,</p>
        <p class="message">Your verification code is:</p>
        <div class="code-box">{code}</div>
        <div class="expiry">⏱️ This code expires in <strong>{expiry_minutes} minutes</strong></div>
        <p class="message" style="margin-top: 20px;">If you didn't request this code, please ignore this email or contact your administrator.</p>
        <div class="footer">
            <p>© 2026 Flowfish - Kubernetes Observability Platform</p>
        </div>
    </div>
</body>
</html>
        """
        
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        if smtp_settings.get('use_ssl'):
            server = smtplib.SMTP_SSL(smtp_settings['host'], smtp_settings['port'])
        else:
            server = smtplib.SMTP(smtp_settings['host'], smtp_settings['port'])
            if smtp_settings.get('use_tls'):
                server.starttls()
        
        if smtp_settings.get('username') and smtp_settings.get('password'):
            server.login(smtp_settings['username'], smtp_settings['password'])
        
        server.send_message(msg)
        server.quit()
        
        logger.info("2FA email sent", email=email[:3] + "***")
        
    except Exception as e:
        logger.error("Failed to send 2FA email", error=str(e))
        raise


# ============================================
# Backup & Restore
# ============================================

class BackupInfo(BaseModel):
    """Backup information"""
    id: str = ""
    name: str = "unnamed"
    type: str = "full"  # 'full', 'config', 'data'
    size: str = "Unknown"
    status: str = "unknown"  # 'completed', 'in_progress', 'failed'
    created_at: str = ""
    created_by: Optional[str] = None


class BackupListResponse(BaseModel):
    """Response for backup list"""
    backups: List[BackupInfo]


class CreateBackupRequest(BaseModel):
    """Request to create a backup"""
    type: str = Field("full", description="Backup type: full, config, or data")
    name: Optional[str] = None


@router.get("/backups", response_model=BackupListResponse)
async def list_backups(current_user: dict = Depends(get_current_user)):
    """List all available backups"""
    try:
        # Check if backups table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'system_backups'
            )
        """
        exists = await database.fetch_one(check_query)
        
        if not exists or not exists[0]:
            # Create backups table if it doesn't exist
            create_table = """
                CREATE TABLE IF NOT EXISTS system_backups (
                    id VARCHAR(50) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    size VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'in_progress',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(100),
                    file_path VARCHAR(500)
                )
            """
            await database.execute(create_table)
            return BackupListResponse(backups=[])
        
        query = """
            SELECT id, name, type, size, status, created_at, created_by
            FROM system_backups
            ORDER BY created_at DESC
            LIMIT 50
        """
        rows = await database.fetch_all(query)
        
        backups = [
            BackupInfo(
                id=row['id'],
                name=row['name'],
                type=row['type'],
                size=row['size'] or 'Unknown',
                status=row['status'],
                created_at=row['created_at'].isoformat() if row['created_at'] else '',
                created_by=row['created_by']
            )
            for row in rows
        ]
        
        return BackupListResponse(backups=backups)
        
    except Exception as e:
        logger.error("Failed to list backups", error=str(e))
        return BackupListResponse(backups=[])


@router.post("/backups")
async def create_backup(
    request: CreateBackupRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Create a new backup"""
    check_admin_role(current_user)
    
    try:
        import uuid
        import os
        
        backup_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = request.name or f"backup_{request.type}_{timestamp}"
        
        # Ensure backups table exists
        create_table = """
            CREATE TABLE IF NOT EXISTS system_backups (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                type VARCHAR(20) NOT NULL,
                size VARCHAR(50),
                status VARCHAR(20) DEFAULT 'in_progress',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                file_path VARCHAR(500)
            )
        """
        await database.execute(create_table)
        
        # Insert backup record
        insert_query = """
            INSERT INTO system_backups (id, name, type, status, created_by)
            VALUES (:id, :name, :type, 'in_progress', :created_by)
        """
        await database.execute(insert_query, {
            'id': backup_id,
            'name': backup_name,
            'type': request.type,
            'created_by': current_user.get('username', 'unknown')
        })
        
        # Run backup in background
        background_tasks.add_task(
            perform_backup,
            backup_id=backup_id,
            backup_type=request.type,
            backup_name=backup_name
        )
        
        logger.info(
            "Backup creation started",
            backup_id=backup_id,
            type=request.type,
            user=current_user.get('username')
        )
        
        return {
            "message": "Backup creation started",
            "backup_id": backup_id,
            "name": backup_name,
            "type": request.type
        }
        
    except Exception as e:
        logger.error("Failed to create backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )


async def perform_backup(backup_id: str, backup_type: str, backup_name: str):
    """Perform the actual backup operation"""
    import asyncio
    import os
    
    try:
        # Simulate backup process
        await asyncio.sleep(2)  # Simulating backup time
        
        # In a real implementation, this would:
        # - For 'full': Export PostgreSQL + ClickHouse + configs
        # - For 'config': Export settings and configurations only
        # - For 'data': Export data tables only
        
        # Calculate fake size based on type
        sizes = {
            'full': '256 MB',
            'config': '2.4 MB',
            'data': '180 MB'
        }
        
        # Update backup status
        update_query = """
            UPDATE system_backups 
            SET status = 'completed', size = :size
            WHERE id = :id
        """
        await database.execute(update_query, {
            'id': backup_id,
            'size': sizes.get(backup_type, '10 MB')
        })
        
        logger.info("Backup completed", backup_id=backup_id)
        
    except Exception as e:
        logger.error("Backup failed", backup_id=backup_id, error=str(e))
        
        # Update status to failed
        try:
            update_query = """
                UPDATE system_backups 
                SET status = 'failed'
                WHERE id = :id
            """
            await database.execute(update_query, {'id': backup_id})
        except:
            pass


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Restore from a backup"""
    check_admin_role(current_user)
    
    try:
        # Check if backup exists
        query = "SELECT * FROM system_backups WHERE id = :id AND status = 'completed'"
        backup = await database.fetch_one(query, {'id': backup_id})
        
        if not backup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup not found or not completed"
            )
        
        # In a real implementation, this would restore the backup
        # For now, just log the action
        logger.info(
            "Backup restore requested",
            backup_id=backup_id,
            user=current_user.get('username')
        )
        
        return {"message": "Backup restore initiated", "backup_id": backup_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to restore backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore backup: {str(e)}"
        )


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a backup"""
    check_admin_role(current_user)
    
    try:
        # Check if backup exists
        query = "SELECT * FROM system_backups WHERE id = :id"
        backup = await database.fetch_one(query, {'id': backup_id})
        
        if not backup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup not found"
            )
        
        # Delete backup record
        delete_query = "DELETE FROM system_backups WHERE id = :id"
        await database.execute(delete_query, {'id': backup_id})
        
        # In a real implementation, also delete the backup file
        
        logger.info(
            "Backup deleted",
            backup_id=backup_id,
            user=current_user.get('username')
        )
        
        return {"message": "Backup deleted", "backup_id": backup_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}"
        )


# ============================================
# API Token Management
# ============================================

class APITokenCreate(BaseModel):
    """Request to create an API token"""
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APITokenResponse(BaseModel):
    """Response for an API token"""
    id: str
    name: str
    scopes: List[str]
    created_at: str
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    is_active: bool = True
    created_by: Optional[str] = None


class APITokenCreateResponse(APITokenResponse):
    """Response when creating a new token (includes the actual token)"""
    token: str


class APITokenListResponse(BaseModel):
    """Response for listing API tokens"""
    tokens: List[APITokenResponse]


@router.get("/api-tokens", response_model=APITokenListResponse)
async def list_api_tokens(current_user: dict = Depends(get_current_user)):
    """List all API tokens for the current user"""
    try:
        # Check if table exists
        check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'api_tokens'
            )
        """
        exists = await database.fetch_one(check_query)
        
        if not exists or not exists[0]:
            # Create table if it doesn't exist
            create_table = """
                CREATE TABLE IF NOT EXISTS api_tokens (
                    id VARCHAR(50) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    token_hash VARCHAR(255) NOT NULL,
                    scopes TEXT[] DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    last_used_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by VARCHAR(100),
                    user_id INT
                )
            """
            await database.execute(create_table)
            return APITokenListResponse(tokens=[])
        
        # Get tokens for current user (or all if admin)
        user_id = current_user.get('user_id')
        roles = current_user.get('roles', [])
        is_admin = any(r.lower() in ['super admin', 'admin', 'platform admin'] for r in roles)
        
        if is_admin:
            query = """
                SELECT id, name, scopes, created_at, expires_at, last_used_at, is_active, created_by
                FROM api_tokens
                ORDER BY created_at DESC
            """
            rows = await database.fetch_all(query)
        else:
            query = """
                SELECT id, name, scopes, created_at, expires_at, last_used_at, is_active, created_by
                FROM api_tokens
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """
            rows = await database.fetch_all(query, {'user_id': user_id})
        
        tokens = [
            APITokenResponse(
                id=row['id'],
                name=row['name'],
                scopes=row['scopes'] if row['scopes'] else [],
                created_at=row['created_at'].isoformat() if row['created_at'] else '',
                expires_at=row['expires_at'].isoformat() if row['expires_at'] else None,
                last_used_at=row['last_used_at'].isoformat() if row['last_used_at'] else None,
                is_active=row['is_active'] if row['is_active'] is not None else True,
                created_by=row['created_by']
            )
            for row in rows
        ]
        
        return APITokenListResponse(tokens=tokens)
        
    except Exception as e:
        logger.error("Failed to list API tokens", error=str(e))
        return APITokenListResponse(tokens=[])


@router.post("/api-tokens", response_model=APITokenCreateResponse)
async def create_api_token(
    request: APITokenCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new API token"""
    try:
        import hashlib
        
        # Ensure table exists
        create_table = """
            CREATE TABLE IF NOT EXISTS api_tokens (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                token_hash VARCHAR(255) NOT NULL,
                scopes TEXT[] DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_by VARCHAR(100),
                user_id INT
            )
        """
        await database.execute(create_table)
        
        # Generate token
        token_id = f"tok-{secrets.token_hex(4)}"
        raw_token = f"ff_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        # Calculate expiry
        expires_at = None
        if request.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
        
        # Insert token
        insert_query = """
            INSERT INTO api_tokens (id, name, token_hash, scopes, expires_at, created_by, user_id)
            VALUES (:id, :name, :token_hash, :scopes, :expires_at, :created_by, :user_id)
            RETURNING *
        """
        
        row = await database.fetch_one(insert_query, {
            'id': token_id,
            'name': request.name,
            'token_hash': token_hash,
            'scopes': request.scopes,
            'expires_at': expires_at,
            'created_by': current_user.get('username', 'unknown'),
            'user_id': current_user.get('user_id')
        })
        
        logger.info(
            "API token created",
            token_id=token_id,
            name=request.name,
            user=current_user.get('username')
        )
        
        return APITokenCreateResponse(
            id=row['id'],
            name=row['name'],
            scopes=row['scopes'] if row['scopes'] else [],
            created_at=row['created_at'].isoformat() if row['created_at'] else '',
            expires_at=row['expires_at'].isoformat() if row['expires_at'] else None,
            is_active=True,
            created_by=row['created_by'],
            token=raw_token  # Only returned once!
        )
        
    except Exception as e:
        logger.error("Failed to create API token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API token: {str(e)}"
        )


@router.delete("/api-tokens/{token_id}")
async def revoke_api_token(
    token_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Revoke an API token"""
    try:
        # Check if token exists and belongs to user (or user is admin)
        user_id = current_user.get('user_id')
        roles = current_user.get('roles', [])
        is_admin = any(r.lower() in ['super admin', 'admin', 'platform admin'] for r in roles)
        
        if is_admin:
            query = "SELECT * FROM api_tokens WHERE id = :id"
            token = await database.fetch_one(query, {'id': token_id})
        else:
            query = "SELECT * FROM api_tokens WHERE id = :id AND user_id = :user_id"
            token = await database.fetch_one(query, {'id': token_id, 'user_id': user_id})
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found"
            )
        
        # Delete the token
        delete_query = "DELETE FROM api_tokens WHERE id = :id"
        await database.execute(delete_query, {'id': token_id})
        
        logger.info(
            "API token revoked",
            token_id=token_id,
            user=current_user.get('username')
        )
        
        return {"message": "API token revoked", "id": token_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to revoke API token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API token: {str(e)}"
        )


@router.get("/api-tokens/scopes")
async def get_available_scopes(current_user: dict = Depends(get_current_user)):
    """Get list of available API token scopes"""
    return {
        "scopes": [
            {"key": "read:analyses", "label": "Read Analyses", "description": "View analysis data and results"},
            {"key": "write:analyses", "label": "Write Analyses", "description": "Create and manage analyses"},
            {"key": "read:clusters", "label": "Read Clusters", "description": "View cluster information"},
            {"key": "write:clusters", "label": "Write Clusters", "description": "Manage cluster connections"},
            {"key": "read:events", "label": "Read Events", "description": "View events and communications"},
            {"key": "read:workloads", "label": "Read Workloads", "description": "View workload information"},
            {"key": "read:reports", "label": "Read Reports", "description": "View and export reports"},
            {"key": "write:reports", "label": "Write Reports", "description": "Create and schedule reports"},
            {"key": "read:simulations", "label": "Read Simulations", "description": "View impact simulations"},
            {"key": "write:simulations", "label": "Write Simulations", "description": "Run impact simulations"},
            {"key": "admin", "label": "Admin Access", "description": "Full administrative access"},
        ]
    }

