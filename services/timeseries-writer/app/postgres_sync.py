"""
PostgreSQL Workload Sync Module
Syncs workload metadata from ClickHouse events to PostgreSQL workloads table

This enables change detection to work by keeping PostgreSQL workloads table
updated with current cluster state.

Feature Flag: WORKLOAD_SYNC_ENABLED=true
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import execute_values

from app.config import settings

logger = logging.getLogger(__name__)

# Cached connection
_connection = None


def get_connection():
    """Get or create PostgreSQL connection"""
    global _connection
    
    if _connection is None or _connection.closed:
        try:
            _connection = psycopg2.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                user=settings.postgres_user,
                password=settings.postgres_password,
                database=settings.postgres_database
            )
            _connection.autocommit = True
            logger.info(f"✅ Connected to PostgreSQL at {settings.postgres_host}:{settings.postgres_port}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            raise
    
    return _connection


def sync_workloads_to_postgresql(messages: List[Dict[str, Any]]) -> int:
    """
    Sync workload metadata to PostgreSQL workloads table
    
    This is called after writing to ClickHouse to keep PostgreSQL in sync.
    Uses UPSERT (ON CONFLICT UPDATE) for idempotency.
    
    Args:
        messages: List of workload metadata messages
        
    Returns:
        Number of rows synced
    """
    if not settings.workload_sync_enabled:
        return 0
    
    if not messages:
        return 0
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Prepare rows for upsert
        rows = []
        for msg in messages:
            data = msg.get('data', {})
            
            # Extract cluster_id (convert string to int)
            cluster_id_str = msg.get('cluster_id', '')
            try:
                cluster_id = int(cluster_id_str) if cluster_id_str else None
            except (ValueError, TypeError):
                cluster_id = None
            
            if not cluster_id:
                continue
            
            # Extract namespace info
            namespace = data.get('namespace', '')
            if not namespace:
                continue
            
            # Extract workload info
            workload_name = data.get('workload_name', '') or data.get('pod_name', '')
            workload_type = data.get('workload_type', 'Pod')
            
            if not workload_name:
                continue
            
            # Build row
            rows.append({
                'cluster_id': cluster_id,
                'namespace': namespace,
                'name': workload_name,
                'workload_type': workload_type,
                'uid': data.get('pod_uid', ''),
                'ip_address': data.get('pod_ip') if data.get('pod_ip') else None,
                'node_name': data.get('node_name', ''),
                'owner_kind': data.get('owner_kind', ''),
                'owner_name': data.get('owner_name', ''),
                'labels': data.get('labels', {}),
                'containers': [],
                'last_seen': datetime.now(timezone.utc),
                'is_active': True
            })
        
        if not rows:
            return 0
        
        # First, ensure namespaces exist (upsert)
        namespace_rows = []
        seen_namespaces = set()
        for row in rows:
            ns_key = (row['cluster_id'], row['namespace'])
            if ns_key not in seen_namespaces:
                namespace_rows.append({
                    'cluster_id': row['cluster_id'],
                    'name': row['namespace']
                })
                seen_namespaces.add(ns_key)
        
        if namespace_rows:
            namespace_sql = """
            INSERT INTO namespaces (cluster_id, name, updated_at)
            VALUES %s
            ON CONFLICT (cluster_id, name) DO UPDATE SET
                updated_at = NOW()
            RETURNING id, cluster_id, name
            """
            
            namespace_values = [(r['cluster_id'], r['name'], datetime.now(timezone.utc)) for r in namespace_rows]
            execute_values(cursor, namespace_sql, namespace_values)
        
        # Get namespace IDs - only query if we have namespaces
        if not seen_namespaces:
            return 0
        
        cursor.execute("""
            SELECT id, cluster_id, name FROM namespaces 
            WHERE (cluster_id, name) IN %s
        """, (tuple(seen_namespaces),))
        
        namespace_map = {}
        for ns_row in cursor.fetchall():
            namespace_map[(ns_row[1], ns_row[2])] = ns_row[0]
        
        # Now upsert workloads
        # CRITICAL: Deduplicate by unique constraint key (cluster_id, namespace_id, workload_type, name)
        # This prevents "ON CONFLICT DO UPDATE command cannot affect row a second time" error
        # which occurs when the same row appears multiple times in a single INSERT batch.
        unique_workloads = {}  # key: (cluster_id, namespace_id, workload_type, name) -> row data
        
        for row in rows:
            ns_id = namespace_map.get((row['cluster_id'], row['namespace']))
            if not ns_id:
                continue
            
            # Create unique key matching the ON CONFLICT constraint
            unique_key = (row['cluster_id'], ns_id, row['workload_type'], row['name'])
            
            # Keep the latest entry (overwrites previous duplicates)
            unique_workloads[unique_key] = (
                row['cluster_id'],
                ns_id,
                row['name'],
                row['workload_type'],
                row['uid'],
                row['ip_address'],
                row['node_name'],
                row['owner_kind'],
                row['owner_name'],
                json.dumps(row['labels']) if row['labels'] else '{}',  # JSONB requires JSON format
                '[]',  # containers
                row['last_seen'],
                True  # is_active
            )
        
        workload_values = list(unique_workloads.values())
        original_count = len(rows)
        deduplicated_count = len(workload_values)
        
        if not workload_values:
            return 0
        
        if original_count != deduplicated_count:
            logger.info(f"📋 Deduplicated workloads: {original_count} -> {deduplicated_count} (removed {original_count - deduplicated_count} duplicates)")
        
        workload_sql = """
        INSERT INTO workloads (
            cluster_id, namespace_id, name, workload_type, uid,
            ip_address, node_name, owner_kind, owner_name,
            labels, containers, last_seen, is_active
        )
        VALUES %s
        ON CONFLICT (cluster_id, namespace_id, workload_type, name) DO UPDATE SET
            uid = EXCLUDED.uid,
            ip_address = EXCLUDED.ip_address,
            node_name = EXCLUDED.node_name,
            owner_kind = EXCLUDED.owner_kind,
            owner_name = EXCLUDED.owner_name,
            labels = EXCLUDED.labels,
            last_seen = EXCLUDED.last_seen,
            is_active = true,
            updated_at = NOW()
        """
        
        execute_values(cursor, workload_sql, workload_values)
        
        cursor.close()
        
        logger.info(f"✅ Synced {deduplicated_count} unique workloads to PostgreSQL")
        return deduplicated_count
        
    except Exception as e:
        logger.error(f"❌ Failed to sync workloads to PostgreSQL: {e}")
        return 0


def mark_stale_workloads_inactive(cluster_id: int, active_workload_names: List[str]) -> int:
    """
    Mark workloads as inactive if they're not in the active list
    
    This handles workload removal detection by setting is_active=false
    for workloads that are no longer seen.
    
    Args:
        cluster_id: Cluster ID
        active_workload_names: List of currently active workload names
        
    Returns:
        Number of workloads marked inactive
    """
    if not settings.workload_sync_enabled:
        return 0
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Mark workloads not in active list as inactive
        cursor.execute("""
            UPDATE workloads 
            SET is_active = false, updated_at = NOW()
            WHERE cluster_id = %s 
              AND is_active = true
              AND name NOT IN %s
              AND last_seen < NOW() - INTERVAL '5 minutes'
        """, (cluster_id, tuple(active_workload_names) if active_workload_names else ('',)))
        
        marked_count = cursor.rowcount
        cursor.close()
        
        if marked_count > 0:
            logger.info(f"📦 Marked {marked_count} stale workloads as inactive for cluster {cluster_id}")
        
        return marked_count
        
    except Exception as e:
        logger.error(f"❌ Failed to mark stale workloads: {e}")
        return 0


def close_connection():
    """Close PostgreSQL connection"""
    global _connection
    
    if _connection and not _connection.closed:
        _connection.close()
        logger.info("PostgreSQL connection closed")
    
    _connection = None
