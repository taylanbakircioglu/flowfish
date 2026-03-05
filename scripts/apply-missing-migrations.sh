#!/bin/bash
# Apply missing PostgreSQL migrations manually
# Run this on a machine with access to the OpenShift cluster

set -e

NAMESPACE="${OPENSHIFT_NAMESPACE:-flowfish}"

echo "========================================="
echo "Apply Missing PostgreSQL Migrations"
echo "Namespace: $NAMESPACE"
echo "========================================="

# Get PostgreSQL credentials
POSTGRES_HOST="postgresql"
POSTGRES_USER="flowfish"
POSTGRES_DB="flowfish"
POSTGRES_PASSWORD=$(oc get secret flowfish-secrets -n $NAMESPACE -o jsonpath='{.data.postgres-password}' | base64 -d)

echo "Connecting to PostgreSQL via port-forward..."

# Start port-forward in background
oc port-forward -n $NAMESPACE svc/postgresql 5432:5432 &
PF_PID=$!
sleep 3

cleanup() {
    echo "Cleaning up port-forward..."
    kill $PF_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "Running migrations..."

# Run migrations using psql
PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -U $POSTGRES_USER -d $POSTGRES_DB << 'EOSQL'

-- Add gadget_protocol column if missing
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS gadget_protocol VARCHAR(50) DEFAULT 'grpc';

-- Update localcluster gadget settings
UPDATE clusters SET 
    gadget_endpoint = 'inspektor-gadget.flowfish:16060',
    gadget_protocol = 'grpc'
WHERE name = 'localcluster';

-- Create namespaces table if not exists
CREATE TABLE IF NOT EXISTS namespaces (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}',
    annotations JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, name)
);

CREATE INDEX IF NOT EXISTS idx_namespaces_cluster ON namespaces(cluster_id);
CREATE INDEX IF NOT EXISTS idx_namespaces_name ON namespaces(name);
CREATE INDEX IF NOT EXISTS idx_namespaces_labels ON namespaces USING gin(labels);

-- Create workloads table if not exists
CREATE TABLE IF NOT EXISTS workloads (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    namespace_id INTEGER NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    workload_type VARCHAR(50) NOT NULL,
    uid VARCHAR(255),
    labels JSONB DEFAULT '{}',
    annotations JSONB DEFAULT '{}',
    replicas INTEGER,
    available_replicas INTEGER,
    image VARCHAR(500),
    status VARCHAR(50) DEFAULT 'Unknown',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cluster_id, namespace_id, workload_type, name)
);

CREATE INDEX IF NOT EXISTS idx_workloads_cluster ON workloads(cluster_id);
CREATE INDEX IF NOT EXISTS idx_workloads_namespace ON workloads(namespace_id);
CREATE INDEX IF NOT EXISTS idx_workloads_type ON workloads(workload_type);
CREATE INDEX IF NOT EXISTS idx_workloads_labels ON workloads USING gin(labels);

-- Verify tables exist
SELECT 'clusters' as table_name, count(*) as row_count FROM clusters
UNION ALL
SELECT 'namespaces', count(*) FROM namespaces
UNION ALL
SELECT 'workloads', count(*) FROM workloads;

EOSQL

echo ""
echo "========================================="
echo "✅ Migrations applied successfully!"
echo "========================================="
echo ""
echo "Now restart the backend pod to reload the schema:"
echo "  oc delete pod -l app=backend -n $NAMESPACE"

