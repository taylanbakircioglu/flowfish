#!/bin/bash
set -e

echo "================================================"
echo "Deploying Infrastructure Components"
echo "================================================"

# Azure Pipelines downloads artifacts to $(Pipeline.Workspace)/artifactName
# Try multiple possible locations
if [ -d "${PIPELINE_WORKSPACE}/manifests" ]; then
  MANIFEST_DIR="${PIPELINE_WORKSPACE}/manifests"
elif [ -d "${BUILD_ARTIFACTSTAGINGDIRECTORY}/manifests" ]; then
  MANIFEST_DIR="${BUILD_ARTIFACTSTAGINGDIRECTORY}/manifests"
elif [ -d "${AGENT_BUILDDIRECTORY}/manifests" ]; then
  MANIFEST_DIR="${AGENT_BUILDDIRECTORY}/manifests"
else
  echo "ERROR: Manifests directory not found!"
  echo "  Tried:"
  echo "    ${PIPELINE_WORKSPACE}/manifests"
  echo "    ${BUILD_ARTIFACTSTAGINGDIRECTORY}/manifests"
  echo "    ${AGENT_BUILDDIRECTORY}/manifests"
  echo ""
  echo "Available directories:"
  ls -la ${PIPELINE_WORKSPACE}/ || true
  exit 1
fi

echo "Using manifests from: $MANIFEST_DIR"

cd $MANIFEST_DIR

# Login to OpenShift
echo "Logging into OpenShift..."

if [ -z "${OPENSHIFT_API_URL}" ] || [ -z "${OPENSHIFT_USER}" ] || [ -z "${OPENSHIFT_PASSWORD}" ] || [ -z "${OPENSHIFT_NAMESPACE}" ]; then
  echo "ERROR: OpenShift credentials not set!"
  echo "Required: OPENSHIFT_API_URL, OPENSHIFT_USER, OPENSHIFT_PASSWORD, OPENSHIFT_NAMESPACE"
  exit 1
fi

oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${OPENSHIFT_PASSWORD} --insecure-skip-tls-verify=true

# Create namespace if not exists
echo "Checking namespace ${OPENSHIFT_NAMESPACE}..."
# Check if namespace exists, create if not (ignore error if already exists or no permission)
if ! oc get project ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  echo "Namespace does not exist, attempting to create..."
  oc new-project ${OPENSHIFT_NAMESPACE} 2>/dev/null || echo "Cannot create namespace, assuming it exists or will be created by manifest..."
else
  echo "Namespace already exists"
fi

# Switch to namespace
oc project ${OPENSHIFT_NAMESPACE} || true

echo ""
echo "================================================"
echo "Deploying Base Resources"
echo "================================================"

# Apply namespace, RBAC, configmaps, secrets
# Skip namespace - it should already exist and TFSSERVICE user doesn't have permission to patch it
echo "Skipping namespace application (assuming it already exists)..."

echo "Applying RBAC..."
oc apply -f 01-rbac.yaml || echo "Warning: Could not apply RBAC (may require admin permissions)"
oc apply -f 02-rbac.yaml || echo "Warning: Could not apply RBAC (may require admin permissions)"
# Note: cluster-manager ClusterRole RBAC (13-cluster-manager-rbac.yaml) requires cluster-admin
# and must be applied manually. See docs for details.

echo "Applying configmaps with backup..."

# Backup directory for ConfigMaps
CONFIGMAP_BACKUP_DIR="/tmp/flowfish-configmap-backups-$(date +%s)"
mkdir -p "$CONFIGMAP_BACKUP_DIR"

echo "  Backup directory: $CONFIGMAP_BACKUP_DIR"
echo ""

# Function to safely apply ConfigMap with backup and rollback
apply_configmap_safe() {
  local file=$1
  local cm_names=$2  # Can be comma-separated list or single name
  
  echo "📦 Processing file: $file"
  
  # Check if file exists
  if [ ! -f "$file" ]; then
    echo "   ❌ File not found: $file"
    return 1
  fi
  
  # Extract ConfigMap names from file if not provided
  if [ -z "$cm_names" ]; then
    cm_names=$(grep "^  name:" "$file" | awk '{print $2}' | tr '\n' ',' | sed 's/,$//')
  fi
  
  if [ -z "$cm_names" ]; then
    echo "   ⚠️  No ConfigMap names found, applying file as-is..."
    oc apply -f "$file" -n ${OPENSHIFT_NAMESPACE}
    return $?
  fi
  
  # Backup existing ConfigMaps
  echo "   📋 ConfigMaps in file: $cm_names"
  IFS=',' read -ra CM_ARRAY <<< "$cm_names"
  
  for cm_name in "${CM_ARRAY[@]}"; do
    cm_name=$(echo "$cm_name" | xargs)  # Trim whitespace
    if oc get configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
      echo "   💾 Backing up: $cm_name"
      oc get configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} -o yaml > "$CONFIGMAP_BACKUP_DIR/${cm_name}.yaml"
    else
      echo "   📝 New ConfigMap: $cm_name (no backup needed)"
    fi
  done
  
  # Apply the file
  echo "   🔄 Applying ConfigMap(s)..."
  if oc apply -f "$file" -n ${OPENSHIFT_NAMESPACE}; then
    echo "   ✅ ConfigMap(s) applied successfully"
    
    # Verify each ConfigMap exists
    local all_verified=true
    for cm_name in "${CM_ARRAY[@]}"; do
      cm_name=$(echo "$cm_name" | xargs)
      if oc get configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
        echo "   ✅ Verified: $cm_name"
      else
        echo "   ❌ Verification failed: $cm_name"
        all_verified=false
      fi
    done
    
    if [ "$all_verified" = true ]; then
      echo "   ✅ All ConfigMaps verified"
      return 0
    else
      echo "   ⚠️  Some ConfigMaps failed verification"
      return 1
    fi
  else
    echo "   ❌ Failed to apply ConfigMap(s), restoring backups..."
    
    # Restore backups
    for cm_name in "${CM_ARRAY[@]}"; do
      cm_name=$(echo "$cm_name" | xargs)
      if [ -f "$CONFIGMAP_BACKUP_DIR/${cm_name}.yaml" ]; then
        echo "   🔄 Restoring: $cm_name"
        oc apply -f "$CONFIGMAP_BACKUP_DIR/${cm_name}.yaml" -n ${OPENSHIFT_NAMESPACE} || echo "   ❌ Failed to restore $cm_name"
      fi
    done
    
    return 1
  fi
}

# ==============================================================================
# ConfigMap Change Detection and Auto-Restart
# ==============================================================================

# Function to get ConfigMap data checksum (only .data field, not metadata/status)
# This avoids false positives from OpenShift-added fields
get_configmap_data_checksum() {
  local configmap_name=$1
  # Get only the .data field as JSON and hash it - ignores metadata, status, etc.
  oc get configmap "$configmap_name" -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data}' 2>/dev/null | md5sum | cut -d' ' -f1 || echo "none"
}

# Track which deployments need restart due to ConfigMap changes
declare -A RESTART_DEPLOYMENTS
declare -A RESTART_DAEMONSETS

# Apply main configmaps (backend-config, frontend-config)
echo "Applying main ConfigMaps (03-configmaps.yaml)..."

# Get checksums before applying (only .data field)
BACKEND_CONFIG_OLD=$(get_configmap_data_checksum "backend-config")
FRONTEND_CONFIG_OLD=$(get_configmap_data_checksum "frontend-config")

apply_configmap_safe "03-configmaps.yaml" "backend-config,frontend-config" || echo "⚠️  Warning: Some main ConfigMaps may have issues"

# Get checksums after applying (only .data field)
BACKEND_CONFIG_NEW=$(get_configmap_data_checksum "backend-config")
FRONTEND_CONFIG_NEW=$(get_configmap_data_checksum "frontend-config")

# Mark deployments for restart if ConfigMap changed
if [ "$BACKEND_CONFIG_OLD" != "$BACKEND_CONFIG_NEW" ]; then
  echo "  📝 backend-config changed"
  RESTART_DEPLOYMENTS["backend"]=1
  RESTART_DEPLOYMENTS["api-gateway"]=1
  RESTART_DEPLOYMENTS["analysis-orchestrator"]=1
  RESTART_DEPLOYMENTS["cluster-manager"]=1
  RESTART_DEPLOYMENTS["ingestion-service"]=1
  RESTART_DEPLOYMENTS["timeseries-writer"]=1
  RESTART_DEPLOYMENTS["graph-writer"]=1
  RESTART_DEPLOYMENTS["graph-query"]=1
else
  echo "  ✅ backend-config unchanged"
fi

if [ "$FRONTEND_CONFIG_OLD" != "$FRONTEND_CONFIG_NEW" ]; then
  echo "  📝 frontend-config changed"
  RESTART_DEPLOYMENTS["frontend"]=1
else
  echo "  ✅ frontend-config unchanged"
fi
echo ""

# Apply Inspektor Gadget ConfigMap
echo "Applying Inspektor Gadget ConfigMap..."
GADGET_CONFIG_CHANGED=false
if [ -f "09-inspektor-gadget-config.yaml" ]; then
  GADGET_CONFIG_OLD=$(get_configmap_data_checksum "inspektor-gadget-config")
  
  apply_configmap_safe "09-inspektor-gadget-config.yaml" "inspektor-gadget-config" || echo "⚠️  Warning: Inspektor Gadget ConfigMap may have issues"
  
  GADGET_CONFIG_NEW=$(get_configmap_data_checksum "inspektor-gadget-config")
  
  if [ "$GADGET_CONFIG_OLD" != "$GADGET_CONFIG_NEW" ]; then
    echo "  📝 inspektor-gadget-config changed"
    GADGET_CONFIG_CHANGED=true
    RESTART_DAEMONSETS["inspektor-gadget"]=1
  else
    echo "  ✅ inspektor-gadget-config unchanged"
  fi
else
  echo "⚠️  09-inspektor-gadget-config.yaml not found, skipping Inspektor Gadget ConfigMap"
fi
echo ""

echo "ConfigMap application complete!"
echo "Backup location: $CONFIGMAP_BACKUP_DIR"

# Show which resources will be restarted
if [ ${#RESTART_DEPLOYMENTS[@]} -gt 0 ] || [ ${#RESTART_DAEMONSETS[@]} -gt 0 ]; then
  echo ""
  echo "📋 Resources marked for restart due to ConfigMap changes:"
  for dep in "${!RESTART_DEPLOYMENTS[@]}"; do
    echo "   - Deployment: $dep"
  done
  for ds in "${!RESTART_DAEMONSETS[@]}"; do
    echo "   - DaemonSet: $ds"
  done
fi

echo "Applying secrets..."
oc apply -f 04-secrets.yaml

echo ""
echo "================================================"
echo "Deploying Database Services"
echo "================================================"

# Deploy PostgreSQL
echo "Deploying PostgreSQL..."

# Check if PostgreSQL is already running and healthy
if oc get statefulset/postgresql -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  READY_REPLICAS=$(oc get statefulset/postgresql -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY_REPLICAS" -ge "1" ]; then
    echo "  PostgreSQL already running and healthy (ready replicas: $READY_REPLICAS), skipping deployment"
  else
    echo "  PostgreSQL exists but not ready, re-deploying..."
    oc apply -f 05-postgresql.yaml
    oc rollout status statefulset/postgresql -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  fi
else
  echo "  PostgreSQL not found, deploying..."
  oc apply -f 05-postgresql.yaml
  sleep 5
  oc rollout status statefulset/postgresql -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  
  # Only run init job on first deployment
  echo "  Running PostgreSQL init job..."
  oc delete job postgres-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
  oc apply -f 05-postgresql.yaml  # This includes the init job
fi

# Deploy Redis
echo "Deploying Redis..."

# Check if Redis is already running and healthy
if oc get statefulset/redis -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  READY_REPLICAS=$(oc get statefulset/redis -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY_REPLICAS" -ge "1" ]; then
    echo "  Redis already running and healthy (ready replicas: $READY_REPLICAS), skipping deployment"
  else
    echo "  Redis exists but not ready, re-deploying..."
    oc apply -f 06-redis.yaml
    oc rollout status statefulset/redis -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  fi
else
  echo "  Redis not found, deploying..."
  oc apply -f 06-redis.yaml
  sleep 5
  oc rollout status statefulset/redis -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
fi

# Deploy RabbitMQ
echo "Deploying RabbitMQ..."

# Check if RabbitMQ is already running and healthy
if oc get statefulset/rabbitmq -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  READY_REPLICAS=$(oc get statefulset/rabbitmq -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY_REPLICAS" -ge "1" ]; then
    echo "  RabbitMQ already running and healthy (ready replicas: $READY_REPLICAS), skipping deployment"
  else
    echo "  RabbitMQ exists but not ready, re-deploying..."
    oc delete job rabbitmq-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
    oc apply -f 06-rabbitmq.yaml
    oc rollout status statefulset/rabbitmq -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  fi
else
  echo "  RabbitMQ not found, deploying..."
  oc delete job rabbitmq-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
  oc apply -f 06-rabbitmq.yaml
  sleep 5
  oc rollout status statefulset/rabbitmq -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
fi

# Deploy Neo4j
echo "Deploying Neo4j Graph Database..."
# NOTE: Neo4j requires anyuid SCC. Grant manually if not already done:
#   oc adm policy add-scc-to-user anyuid -z flowfish-neo4j -n ${OPENSHIFT_NAMESPACE}

# Check if Neo4j is already running and healthy
if oc get statefulset/neo4j -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  READY_REPLICAS=$(oc get statefulset/neo4j -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY_REPLICAS" -ge "1" ]; then
    echo "  Neo4j already running and healthy (ready replicas: $READY_REPLICAS), skipping deployment"
    
    # Check if schema is already initialized by querying Neo4j directly
    echo "  Checking if Neo4j schema is already initialized..."
    NEO4J_PASSWORD=$(oc get secret flowfish-secrets -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d)
    # Use head -1 to ensure single integer value, tr to remove newlines
    SCHEMA_CHECK=$(oc exec neo4j-0 -n ${OPENSHIFT_NAMESPACE} -- cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "SHOW CONSTRAINTS" 2>/dev/null | grep -E "workload_id|namespace_name|cluster_name" | wc -l | tr -d ' \n' || echo "0")
    SCHEMA_CHECK=${SCHEMA_CHECK:-0}
    
    if [ "$SCHEMA_CHECK" -ge "1" ] 2>/dev/null; then
      echo "  Neo4j schema already initialized (constraints exist), skipping init job"
    else
      echo "  Neo4j schema not initialized, running init job..."
      oc delete job neo4j-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
      sleep 2
      oc apply -f 08-neo4j-init.yaml
      oc wait --for=condition=complete job/neo4j-init -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
    fi
  else
    echo "  Neo4j exists but not ready, re-deploying..."
    oc apply -f 07-neo4j.yaml
    oc rollout status statefulset/neo4j -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
    
    echo "  Running Neo4j init job..."
    oc delete job neo4j-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
    oc apply -f 08-neo4j-init.yaml
    oc wait --for=condition=complete job/neo4j-init -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  fi
else
  echo "  Neo4j not found, deploying..."
  oc apply -f 07-neo4j.yaml
  sleep 5
  oc rollout status statefulset/neo4j -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  
  echo "  Running Neo4j init job..."
  oc delete job neo4j-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
  oc apply -f 08-neo4j-init.yaml
  oc wait --for=condition=complete job/neo4j-init -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
fi
echo "Neo4j deployment complete!"

# Deploy ClickHouse
echo "Deploying ClickHouse..."
# NOTE: ClickHouse requires anyuid SCC. Grant manually if not already done:
#   oc adm policy add-scc-to-user anyuid -z flowfish-clickhouse -n ${OPENSHIFT_NAMESPACE}

# Check if ClickHouse is already running and healthy
if oc get statefulset/clickhouse -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  READY_REPLICAS=$(oc get statefulset/clickhouse -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
  if [ "$READY_REPLICAS" -ge "1" ]; then
    echo "  ClickHouse already running and healthy (ready replicas: $READY_REPLICAS), skipping deployment"
    
    # Check if schema is already initialized by querying ClickHouse directly
    echo "  Checking if ClickHouse schema is already initialized..."
    CLICKHOUSE_PASSWORD=$(oc get secret database-credentials -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data.clickhouse-password}' | base64 -d)
    SCHEMA_CHECK=$(oc exec clickhouse-0 -n ${OPENSHIFT_NAMESPACE} -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASSWORD" --query "SHOW DATABASES" 2>/dev/null | grep -c "flowfish" || echo "0")
    
    if [ "$SCHEMA_CHECK" -ge "1" ]; then
      echo "  ClickHouse schema already initialized (database 'flowfish' exists), skipping init job"
    else
      echo "  ClickHouse schema not initialized, running init job..."
      oc delete job clickhouse-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
      sleep 2
      oc apply -f 08-clickhouse.yaml  # This includes the init job
      oc wait --for=condition=complete job/clickhouse-init -n ${OPENSHIFT_NAMESPACE} --timeout=3m || true
    fi
  else
    echo "  ClickHouse exists but not ready, re-deploying..."
    oc delete job clickhouse-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
    oc apply -f 08-clickhouse.yaml
    oc rollout status statefulset/clickhouse -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
    oc wait --for=condition=complete job/clickhouse-init -n ${OPENSHIFT_NAMESPACE} --timeout=3m || true
  fi
else
  echo "  ClickHouse not found, deploying..."
  oc delete job clickhouse-init -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
  oc apply -f 08-clickhouse.yaml
  sleep 5
  oc rollout status statefulset/clickhouse -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
  oc wait --for=condition=complete job/clickhouse-init -n ${OPENSHIFT_NAMESPACE} --timeout=3m || true
fi
echo "ClickHouse deployment complete!"

# Run database migrations
echo "Running database migrations..."

# ALWAYS delete and recreate migration job to ensure new migrations run
# Migration scripts use "CREATE TABLE IF NOT EXISTS" and "ON CONFLICT DO NOTHING"
# so they are idempotent and safe to run multiple times
echo "  Deleting any existing migration job..."
oc delete job flowfish-migrations -n ${OPENSHIFT_NAMESPACE} --ignore-not-found=true
sleep 2

echo "  Creating and running migration job..."
oc apply -f 03-migrations-job.yaml
sleep 5

echo "  Waiting for migration job to complete..."
if oc wait --for=condition=complete job/flowfish-migrations -n ${OPENSHIFT_NAMESPACE} --timeout=10m; then
  echo "  ✅ Database migrations completed successfully"
  
  # Show migration logs
  echo "  Migration logs:"
  oc logs job/flowfish-migrations -c postgres-migrations -n ${OPENSHIFT_NAMESPACE} --tail=20 || true
else
  echo "  ⚠️  Migration job may have issues, checking logs..."
  oc logs job/flowfish-migrations -c postgres-migrations -n ${OPENSHIFT_NAMESPACE} --tail=50 || true
fi

echo ""
echo "================================================"
echo "Deploying Inspektor Gadget (eBPF Observability)"
echo "================================================"

# NOTE: Cluster-scoped resources (CRDs, ClusterRoles) are NOT applied by pipeline
# They must be applied manually by cluster admin before first deployment
# See: deployment/manual-rbac/README.md

echo "ℹ️  Skipping cluster-scoped resources (applied manually by cluster admin):"
echo "   - CRDs (09-inspektor-gadget-crds.yaml)"
echo "   - ClusterRole/ClusterRoleBinding (10-inspektor-gadget-rbac-cluster.yaml)"
echo "   - ClusterRole/ClusterRoleBinding (flowfish-gadget-reader)"

# 3. Always apply DaemonSet manifest (to pick up any updates)
echo "Applying Inspektor Gadget DaemonSet..."

# Get current image before update
CURRENT_IMAGE=""
if oc get daemonset inspektor-gadget -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
  CURRENT_IMAGE=$(oc get daemonset inspektor-gadget -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "none")
  echo "  Current image: $CURRENT_IMAGE"
fi

# Apply the manifest (this will update if changed)
oc apply -f 10-inspektor-gadget.yaml

# Get new image after update
NEW_IMAGE=$(oc get daemonset inspektor-gadget -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "none")
echo "  Target image: $NEW_IMAGE"

# Check if image changed or ConfigMap changed
if [ "$CURRENT_IMAGE" != "$NEW_IMAGE" ] || [ -z "$CURRENT_IMAGE" ]; then
  echo "  🔄 Image changed, waiting for rollout..."
  oc rollout status daemonset/inspektor-gadget -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
elif [ "${RESTART_DAEMONSETS[inspektor-gadget]:-0}" = "1" ]; then
  echo "  🔄 ConfigMap changed, restarting DaemonSet to pick up new config..."
  oc rollout restart daemonset/inspektor-gadget -n ${OPENSHIFT_NAMESPACE}
  oc rollout status daemonset/inspektor-gadget -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
else
  echo "  ✅ Image and ConfigMap unchanged, checking pod health..."
  
  DESIRED=$(oc get daemonset inspektor-gadget -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.desiredNumberScheduled}')
  READY=$(oc get daemonset inspektor-gadget -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.status.numberReady}')
  
  if [ "$READY" = "$DESIRED" ] && [ "$READY" != "0" ]; then
    echo "  ✅ All $READY/$DESIRED pods ready"
  else
    echo "  ⚠️  Only $READY/$DESIRED pods ready, waiting..."
    oc rollout status daemonset/inspektor-gadget -n ${OPENSHIFT_NAMESPACE} --timeout=3m || true
  fi
fi

echo "  Inspektor Gadget pods:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -l app=inspektor-gadget -o wide

echo ""
echo "================================================"
echo "Infrastructure deployment complete"
echo "================================================"

# Show infrastructure status
echo "Infrastructure Pods:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -l tier=infrastructure

echo ""
echo "Infrastructure Services:"
oc get svc -n ${OPENSHIFT_NAMESPACE} -l tier=infrastructure

echo ""
echo "Inspektor Gadget DaemonSet:"
oc get daemonset -n ${OPENSHIFT_NAMESPACE} inspektor-gadget || echo "  Inspektor Gadget not found"

echo ""
echo "Inspektor Gadget Pods:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -l app=inspektor-gadget || echo "  No Inspektor Gadget pods found"

echo "================================================"

