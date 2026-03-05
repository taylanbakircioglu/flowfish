"""
Notification Service - Change Detection Notifications

Provides integration hooks for:
- Slack
- Microsoft Teams
- Email
- Generic Webhooks

This service is responsible for:
1. Managing notification configurations
2. Sending notifications when critical changes are detected
3. Rate limiting to prevent notification flooding
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import structlog
import json
import httpx

from database.postgresql import database

logger = structlog.get_logger(__name__)


class HookType(str, Enum):
    """Supported notification hook types"""
    SLACK = "slack"
    TEAMS = "teams"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationService:
    """
    Notification service for change detection alerts
    """
    
    def __init__(self):
        self.db = database
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def get_hooks_for_cluster(
        self, 
        cluster_id: int, 
        enabled_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get notification hooks for a cluster
        """
        conditions = ["cluster_id = :cluster_id"]
        if enabled_only:
            conditions.append("is_enabled = true")
        
        query = f"""
        SELECT * FROM notification_hooks
        WHERE {' AND '.join(conditions)}
        ORDER BY name
        """
        
        results = await self.db.fetch_all(query, {"cluster_id": cluster_id})
        return [dict(r) for r in results] if results else []
    
    async def create_hook(
        self,
        cluster_id: int,
        name: str,
        hook_type: str,
        config: Dict[str, Any],
        trigger_on_critical: bool = True,
        trigger_on_high: bool = True,
        trigger_on_medium: bool = False,
        trigger_on_low: bool = False,
        trigger_change_types: Optional[List[str]] = None,
        created_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Create a new notification hook
        """
        query = """
        INSERT INTO notification_hooks (
            cluster_id, name, hook_type, config,
            trigger_on_critical, trigger_on_high, trigger_on_medium, trigger_on_low,
            trigger_change_types, created_by
        ) VALUES (
            :cluster_id, :name, :hook_type, :config,
            :trigger_on_critical, :trigger_on_high, :trigger_on_medium, :trigger_on_low,
            :trigger_change_types, :created_by
        )
        RETURNING id, name, hook_type, is_enabled, created_at
        """
        
        result = await self.db.fetch_one(query, {
            "cluster_id": cluster_id,
            "name": name,
            "hook_type": hook_type,
            "config": json.dumps(config),
            "trigger_on_critical": trigger_on_critical,
            "trigger_on_high": trigger_on_high,
            "trigger_on_medium": trigger_on_medium,
            "trigger_on_low": trigger_on_low,
            "trigger_change_types": trigger_change_types,
            "created_by": created_by
        })
        
        if result:
            logger.info("Notification hook created", hook_id=result["id"], name=name)
            return dict(result)
        
        return {}
    
    async def update_hook(
        self,
        hook_id: int,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update an existing notification hook
        """
        allowed_fields = [
            "name", "config", "is_enabled",
            "trigger_on_critical", "trigger_on_high", "trigger_on_medium", "trigger_on_low",
            "trigger_change_types", "rate_limit_per_hour"
        ]
        
        set_clauses = []
        params = {"hook_id": hook_id}
        
        for field, value in updates.items():
            if field in allowed_fields:
                if field == "config":
                    value = json.dumps(value)
                set_clauses.append(f"{field} = :{field}")
                params[field] = value
        
        if not set_clauses:
            return False
        
        set_clauses.append("updated_at = NOW()")
        
        query = f"""
        UPDATE notification_hooks
        SET {', '.join(set_clauses)}
        WHERE id = :hook_id
        """
        
        await self.db.execute(query, params)
        return True
    
    async def delete_hook(self, hook_id: int) -> bool:
        """
        Delete a notification hook
        """
        query = "DELETE FROM notification_hooks WHERE id = :hook_id RETURNING id"
        result = await self.db.fetch_one(query, {"hook_id": hook_id})
        return result is not None
    
    async def should_trigger(
        self,
        hook: Dict[str, Any],
        change: Dict[str, Any]
    ) -> bool:
        """
        Check if a hook should be triggered for a change
        """
        risk_level = change.get("risk_level", "low")
        change_type = change.get("change_type", "")
        
        # Check risk level triggers
        if risk_level == "critical" and not hook.get("trigger_on_critical", True):
            return False
        if risk_level == "high" and not hook.get("trigger_on_high", True):
            return False
        if risk_level == "medium" and not hook.get("trigger_on_medium", False):
            return False
        if risk_level == "low" and not hook.get("trigger_on_low", False):
            return False
        
        # Check change type triggers
        trigger_types = hook.get("trigger_change_types")
        if trigger_types and change_type not in trigger_types:
            return False
        
        # Check rate limiting
        rate_limit = hook.get("rate_limit_per_hour", 100)
        last_triggered = hook.get("last_triggered_at")
        
        if last_triggered and rate_limit > 0:
            # Simple rate check - in production, use proper rate limiting
            time_since = datetime.utcnow() - last_triggered
            if time_since < timedelta(seconds=3600 / rate_limit):
                logger.debug("Rate limited", hook_id=hook["id"])
                return False
        
        return True
    
    async def send_notification(
        self,
        hook: Dict[str, Any],
        change: Dict[str, Any]
    ) -> bool:
        """
        Send a notification through the specified hook
        """
        hook_type = hook.get("hook_type")
        config = hook.get("config", {})
        
        if isinstance(config, str):
            config = json.loads(config)
        
        try:
            if hook_type == HookType.SLACK.value:
                return await self._send_slack(config, change)
            elif hook_type == HookType.TEAMS.value:
                return await self._send_teams(config, change)
            elif hook_type == HookType.WEBHOOK.value:
                return await self._send_webhook(config, change)
            elif hook_type == HookType.EMAIL.value:
                return await self._send_email(config, change)
            else:
                logger.warning("Unknown hook type", hook_type=hook_type)
                return False
                
        except Exception as e:
            logger.error("Failed to send notification", hook_id=hook.get("id"), error=str(e))
            return False
        finally:
            # Update last triggered timestamp
            await self._update_last_triggered(hook["id"])
    
    async def _update_last_triggered(self, hook_id: int):
        """Update the last triggered timestamp"""
        query = "UPDATE notification_hooks SET last_triggered_at = NOW() WHERE id = :hook_id"
        await self.db.execute(query, {"hook_id": hook_id})
    
    async def _send_slack(self, config: Dict, change: Dict) -> bool:
        """Send Slack notification"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            logger.warning("Slack webhook URL not configured")
            return False
        
        # Build Slack message
        risk_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢"
        }.get(change.get("risk_level", "low"), "⚪")
        
        message = {
            "text": f"{risk_emoji} Change Detected: {change.get('target', 'Unknown')}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{risk_emoji} {change.get('change_type', 'Change').replace('_', ' ').title()}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Target:*\n{change.get('target', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Namespace:*\n{change.get('namespace', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Risk Level:*\n{change.get('risk_level', 'Unknown').title()}"},
                        {"type": "mrkdwn", "text": f"*Affected Services:*\n{change.get('affected_services', 0)}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:* {change.get('details', 'No details available')}"
                    }
                }
            ]
        }
        
        response = await self.http_client.post(webhook_url, json=message)
        return response.status_code == 200
    
    async def _send_teams(self, config: Dict, change: Dict) -> bool:
        """Send Microsoft Teams notification"""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            logger.warning("Teams webhook URL not configured")
            return False
        
        # Build Teams Adaptive Card
        risk_color = {
            "critical": "attention",
            "high": "warning", 
            "medium": "accent",
            "low": "good"
        }.get(change.get("risk_level", "low"), "default")
        
        message = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": f"Change Detected: {change.get('target', 'Unknown')}",
                            "weight": "bolder",
                            "size": "medium",
                            "color": risk_color
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Type", "value": change.get('change_type', 'Unknown')},
                                {"title": "Namespace", "value": change.get('namespace', 'Unknown')},
                                {"title": "Risk Level", "value": change.get('risk_level', 'Unknown')},
                                {"title": "Affected Services", "value": str(change.get('affected_services', 0))}
                            ]
                        },
                        {
                            "type": "TextBlock",
                            "text": change.get('details', 'No details available'),
                            "wrap": True
                        }
                    ]
                }
            }]
        }
        
        response = await self.http_client.post(webhook_url, json=message)
        return response.status_code in [200, 202]
    
    async def _send_webhook(self, config: Dict, change: Dict) -> bool:
        """Send generic webhook notification"""
        url = config.get("url")
        if not url:
            logger.warning("Webhook URL not configured")
            return False
        
        headers = config.get("headers", {})
        method = config.get("method", "POST").upper()
        
        payload = {
            "event": "change_detected",
            "timestamp": datetime.utcnow().isoformat(),
            "change": change
        }
        
        if method == "POST":
            response = await self.http_client.post(url, json=payload, headers=headers)
        elif method == "PUT":
            response = await self.http_client.put(url, json=payload, headers=headers)
        else:
            logger.warning("Unsupported webhook method", method=method)
            return False
        
        return response.status_code < 400
    
    async def _send_email(self, config: Dict, change: Dict) -> bool:
        """
        Send email notification
        
        Note: Email sending requires SMTP configuration.
        This is a placeholder that logs the intent.
        In production, integrate with your email service (SendGrid, SES, etc.)
        """
        recipients = config.get("recipients", [])
        if not recipients:
            logger.warning("No email recipients configured")
            return False
        
        # Log email intent - in production, send actual email
        logger.info(
            "Email notification would be sent",
            recipients=recipients,
            change_type=change.get("change_type"),
            target=change.get("target"),
            risk_level=change.get("risk_level")
        )
        
        # TODO: Implement actual email sending
        # This could use:
        # - SMTP directly
        # - SendGrid API
        # - AWS SES
        # - Azure Communication Services
        
        return True
    
    async def notify_change(
        self,
        cluster_id: int,
        change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send notifications for a change to all applicable hooks
        
        Returns summary of notification results
        """
        hooks = await self.get_hooks_for_cluster(cluster_id, enabled_only=True)
        
        results = {
            "total_hooks": len(hooks),
            "triggered": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        for hook in hooks:
            if await self.should_trigger(hook, change):
                results["triggered"] += 1
                if await self.send_notification(hook, change):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            else:
                results["skipped"] += 1
        
        logger.info("Notifications sent", cluster_id=cluster_id, results=results)
        return results


# Service factory
def get_notification_service() -> NotificationService:
    """Factory function for NotificationService"""
    return NotificationService()


# Export
__all__ = [
    "NotificationService",
    "HookType",
    "get_notification_service"
]
