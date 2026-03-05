"""
WebSocket router for real-time event streaming
Sprint 5-6: Live Map Updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from pydantic import BaseModel, Field
from typing import Dict, Set, Optional, List
import asyncio
import json
import structlog
from datetime import datetime

# JWT validation for WebSocket is handled inline (token passed as query param)
# from utils.jwt_utils import get_current_user_from_token

logger = structlog.get_logger()

router = APIRouter()


# ============================================
# Pydantic Models for Internal Broadcast API
# ============================================

class BroadcastMessage(BaseModel):
    """Message format for internal broadcast API"""
    type: str = Field(..., description="Message type (e.g., 'analysis_auto_stop_warning')")
    analysis_id: int = Field(..., description="Target analysis ID")
    analysis_name: str = Field(default="", description="Analysis name for display")
    remaining_minutes: float = Field(default=0, description="Time remaining before auto-stop")
    message: str = Field(default="", description="Human-readable message")


class ConnectionManager:
    """Manages WebSocket connections for live updates"""
    
    def __init__(self):
        # Connections grouped by analysis_id
        self.analysis_connections: Dict[int, Set[WebSocket]] = {}
        
        # Connections for all events (dashboard)
        self.global_connections: Set[WebSocket] = set()
        
        # Statistics
        self.total_connections = 0
        self.messages_sent = 0
    
    async def connect(self, websocket: WebSocket, analysis_id: Optional[int] = None, accept: bool = True):
        """Accept connection and add to appropriate group
        
        Args:
            websocket: The WebSocket connection
            analysis_id: Optional analysis ID to subscribe to
            accept: Whether to accept the connection (False for re-subscription)
        """
        if accept:
            await websocket.accept()
            self.total_connections += 1
        
        if analysis_id:
            if analysis_id not in self.analysis_connections:
                self.analysis_connections[analysis_id] = set()
            self.analysis_connections[analysis_id].add(websocket)
            logger.info("WebSocket connected to analysis",
                       analysis_id=analysis_id,
                       total_for_analysis=len(self.analysis_connections[analysis_id]))
        else:
            self.global_connections.add(websocket)
            logger.info("WebSocket connected globally",
                       total_global=len(self.global_connections))
    
    def disconnect(self, websocket: WebSocket, analysis_id: Optional[int] = None):
        """Remove connection from groups"""
        if analysis_id and analysis_id in self.analysis_connections:
            self.analysis_connections[analysis_id].discard(websocket)
            if not self.analysis_connections[analysis_id]:
                del self.analysis_connections[analysis_id]
        
        self.global_connections.discard(websocket)
        logger.info("WebSocket disconnected")
    
    async def send_to_analysis(self, analysis_id: int, message: dict):
        """Send message to all connections watching an analysis"""
        if analysis_id not in self.analysis_connections:
            return
        
        message_json = json.dumps(message, default=str)
        
        disconnected = set()
        for websocket in self.analysis_connections[analysis_id]:
            try:
                await websocket.send_text(message_json)
                self.messages_sent += 1
            except Exception as e:
                logger.warning("Failed to send to WebSocket", error=str(e))
                disconnected.add(websocket)
        
        # Clean up disconnected
        for ws in disconnected:
            self.disconnect(ws, analysis_id)
    
    async def send_to_all(self, message: dict):
        """Send message to all global connections"""
        message_json = json.dumps(message, default=str)
        
        disconnected = set()
        for websocket in self.global_connections:
            try:
                await websocket.send_text(message_json)
                self.messages_sent += 1
            except Exception:
                disconnected.add(websocket)
        
        # Clean up disconnected
        for ws in disconnected:
            self.global_connections.discard(ws)
    
    async def broadcast_event(self, analysis_id: int, event: dict):
        """Broadcast event to analysis watchers and global watchers"""
        # Send to analysis-specific connections
        await self.send_to_analysis(analysis_id, event)
        
        # Send to global connections (with analysis_id)
        global_event = {**event, "analysis_id": analysis_id}
        await self.send_to_all(global_event)
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "total_connections": self.total_connections,
            "active_analysis_connections": sum(
                len(conns) for conns in self.analysis_connections.values()
            ),
            "active_global_connections": len(self.global_connections),
            "messages_sent": self.messages_sent,
            "analyses_with_watchers": list(self.analysis_connections.keys())
        }


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/events")
async def websocket_events(
    websocket: WebSocket,
    analysis_id: Optional[int] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time event streaming.
    
    Query Parameters:
    - analysis_id: Filter events by analysis (optional)
    - token: JWT token for authentication
    
    Message Types:
    - communication_discovered: New workload communication
    - event_collected: Raw eBPF event
    - analysis_status: Analysis status change
    - stats_update: Statistics update
    """
    # Validate token (optional for now, can enforce in production)
    # user = None
    # if token:
    #     try:
    #         user = await get_current_user_from_token(token)
    #     except:
    #         await websocket.close(code=4001, reason="Invalid token")
    #         return
    
    await manager.connect(websocket, analysis_id)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connection established",
            "analysis_id": analysis_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages with timeout
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # Handle incoming messages
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif message.get("type") == "subscribe":
                    # Change subscription
                    new_analysis_id = message.get("analysis_id")
                    manager.disconnect(websocket, analysis_id)
                    await manager.connect(websocket, new_analysis_id)
                    analysis_id = new_analysis_id
                    
                    await websocket.send_json({
                        "type": "subscribed",
                        "analysis_id": analysis_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, analysis_id)
        logger.info("WebSocket client disconnected", analysis_id=analysis_id)
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        manager.disconnect(websocket, analysis_id)


@router.websocket("/ws/changes")
async def websocket_changes(
    websocket: WebSocket,
    analysis_id: Optional[int] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time change detection updates.
    
    Query Parameters:
    - analysis_id: Filter changes by analysis (optional)
    - token: JWT token for authentication
    
    Message Types (from server):
    - change_detected: New change detected
    - critical_change_alert: Critical change requiring attention
    - change_stats_update: Statistics update
    
    Message Types (from client):
    - ping: Heartbeat request
    - subscribe: Change analysis subscription
    """
    await manager.connect(websocket, analysis_id)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "Change detection WebSocket established",
            "analysis_id": analysis_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif message.get("type") == "subscribe":
                    new_analysis_id = message.get("analysis_id")
                    manager.disconnect(websocket, analysis_id)
                    await manager.connect(websocket, new_analysis_id, accept=False)  # Don't re-accept
                    analysis_id = new_analysis_id
                    
                    await websocket.send_json({
                        "type": "subscribed",
                        "analysis_id": analysis_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, analysis_id)
        logger.info("Changes WebSocket disconnected", analysis_id=analysis_id)
    except Exception as e:
        logger.error("Changes WebSocket error", error=str(e))
        manager.disconnect(websocket, analysis_id)


@router.websocket("/ws/live-map")
async def websocket_live_map(
    websocket: WebSocket,
    cluster_id: int = Query(...),
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for live map graph updates.
    
    Streams:
    - node_added: New workload discovered
    - node_updated: Workload status change
    - edge_added: New communication discovered
    - edge_updated: Communication metrics update
    - stats: Periodic statistics
    """
    await websocket.accept()
    
    try:
        # Send initial graph snapshot
        await websocket.send_json({
            "type": "snapshot",
            "cluster_id": cluster_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Waiting for events..."
        })
        
        # Simulation of live updates (in production, this comes from event processor)
        while True:
            # Wait for incoming messages or timeout
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=5.0
                )
                
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            except asyncio.TimeoutError:
                # Send heartbeat with stats
                await websocket.send_json({
                    "type": "heartbeat",
                    "cluster_id": cluster_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "stats": manager.get_stats()
                })
                
    except WebSocketDisconnect:
        logger.info("Live map WebSocket disconnected", cluster_id=cluster_id)
    except Exception as e:
        logger.error("Live map WebSocket error", error=str(e))


# Utility functions for event broadcasting

async def broadcast_communication_discovered(
    analysis_id: int,
    source: dict,
    destination: dict,
    protocol: str,
    port: int,
    metrics: dict = None
):
    """Broadcast when a new communication is discovered"""
    await manager.broadcast_event(analysis_id, {
        "type": "communication_discovered",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "port": port,
            "metrics": metrics or {}
        }
    })


async def broadcast_event_collected(
    analysis_id: int,
    event_type: str,
    event_data: dict
):
    """Broadcast raw event collection"""
    await manager.broadcast_event(analysis_id, {
        "type": "event_collected",
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "data": event_data
    })


async def broadcast_analysis_status(
    analysis_id: int,
    status: str,
    events_collected: int = 0,
    communications_discovered: int = 0
):
    """Broadcast analysis status change"""
    await manager.broadcast_event(analysis_id, {
        "type": "analysis_status",
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "events_collected": events_collected,
        "communications_discovered": communications_discovered
    })


# ============================================
# Internal Broadcast API (for Orchestrator)
# ============================================

@router.post("/ws/broadcast", include_in_schema=False)
async def broadcast_message(msg: BroadcastMessage):
    """
    Internal endpoint for orchestrator to broadcast messages to WebSocket clients.
    
    NOT exposed in API documentation (include_in_schema=False).
    Used by analysis-orchestrator to send auto-stop warnings.
    
    Message Types:
    - analysis_auto_stop_warning: Warning before analysis auto-stops
    """
    try:
        # Build the broadcast payload
        payload = {
            "type": msg.type,
            "analysis_id": msg.analysis_id,
            "analysis_name": msg.analysis_name,
            "remaining_minutes": msg.remaining_minutes,
            "message": msg.message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to analysis-specific connections
        await manager.send_to_analysis(msg.analysis_id, payload)
        
        # Also broadcast to global connections (dashboard)
        await manager.send_to_all(payload)
        
        logger.info(
            "Broadcast message sent",
            type=msg.type,
            analysis_id=msg.analysis_id,
            analysis_name=msg.analysis_name
        )
        
        return {
            "status": "ok",
            "sent_to_analysis": msg.analysis_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Broadcast failed", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }


# Export manager for use in other modules
def get_connection_manager() -> ConnectionManager:
    """Get global connection manager"""
    return manager


# ============================================
# Change Detection Broadcast Functions
# ============================================

async def broadcast_to_analysis(analysis_id: int, message: dict):
    """
    Broadcast a message to all clients watching an analysis.
    Used by the change detection worker for real-time updates.
    
    Args:
        analysis_id: Target analysis ID
        message: Message dictionary to broadcast
    """
    await manager.broadcast_event(analysis_id, message)


async def broadcast_change_detected(
    analysis_id: int,
    change_type: str,
    target: str,
    namespace: str,
    risk_level: str,
    details: str,
    affected_services: int = 0
):
    """
    Broadcast when a change is detected.
    
    Args:
        analysis_id: Analysis that detected the change
        change_type: Type of change (workload_added, connection_removed, etc.)
        target: Target workload/connection name
        namespace: Kubernetes namespace
        risk_level: Risk assessment (critical, high, medium, low)
        details: Human-readable description
        affected_services: Number of affected services (blast radius)
    """
    await manager.broadcast_event(analysis_id, {
        "type": "change_detected",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "change_type": change_type,
            "target": target,
            "namespace": namespace,
            "risk_level": risk_level,
            "details": details,
            "affected_services": affected_services
        }
    })


async def broadcast_critical_change(
    analysis_id: int,
    change: dict
):
    """
    Broadcast a critical change alert.
    
    Used for changes with risk_level=critical that require immediate attention.
    
    Args:
        analysis_id: Analysis that detected the change
        change: Full change dictionary
    """
    await manager.broadcast_event(analysis_id, {
        "type": "critical_change_alert",
        "timestamp": datetime.utcnow().isoformat(),
        "severity": "critical",
        "data": change
    })
    
    logger.warning(
        "Critical change broadcast",
        analysis_id=analysis_id,
        change_type=change.get("change_type"),
        target=change.get("target")
    )

