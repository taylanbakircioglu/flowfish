#!/bin/bash
set -e

# Deploy Infrastructure Components
# PostgreSQL, ClickHouse, Neo4j, Redis, RabbitMQ

ns=$OPENSHIFT_NAMESPACE

echo "Deploying Infrastructure Components..."
echo "Namespace: $ns"

# Login to OpenShift
echo " Login to OpenShift..."
oc login -u $OPENSHIFT_USER -p $OPENSHIFT_PASSWORD $OPENSHIFT_API_URL --insecure-skip-tls-verify=true
oc project $ns || oc new-project $ns

# Apply manifests from artifact directory
MANIFEST_DIR="${PIPELINE_WORKSPACE}/manifests"

# Namespace & RBAC
echo " Applying Namespace & RBAC..."
oc apply -f $MANIFEST_DIR/01-namespace.yaml || true
oc apply -f $MANIFEST_DIR/01-rbac.yaml || true
oc apply -f $MANIFEST_DIR/02-rbac.yaml || true

# ConfigMaps & Secrets
echo "Applying ConfigMaps & Secrets..."
oc apply -f $MANIFEST_DIR/03-configmaps.yaml -n $ns
oc apply -f $MANIFEST_DIR/04-secrets.yaml -n $ns

# PostgreSQL
if [ "$RELEASE_ALL" = "true" ] || [ ! "$(oc get statefulset postgresql -n $ns 2>/dev/null)" ]; then
    echo " Deploying PostgreSQL..."
    
    # Delete existing init job if it exists
    echo "Cleaning up existing PostgreSQL init job if present..."
    oc delete job postgres-init -n $ns --ignore-not-found=true
    
    oc apply -f $MANIFEST_DIR/05-postgresql.yaml -n $ns
    echo "  Waiting for PostgreSQL..."
    oc rollout status statefulset/postgresql -n $ns --timeout=5m || true
    
    echo "  Waiting for PostgreSQL init job..."
    oc wait --for=condition=complete job/postgres-init -n $ns --timeout=3m || true
else
    echo "    PostgreSQL already deployed"
fi

# Redis
if [ "$RELEASE_ALL" = "true" ] || [ ! "$(oc get statefulset redis -n $ns 2>/dev/null)" ]; then
    echo "Deploying Redis..."
    oc apply -f $MANIFEST_DIR/06-redis.yaml -n $ns
    oc rollout status statefulset/redis -n $ns --timeout=3m || true
else
    echo "    Redis already deployed"
fi

# RabbitMQ
if [ "$RELEASE_ALL" = "true" ] || [ ! "$(oc get statefulset rabbitmq -n $ns 2>/dev/null)" ]; then
    echo " Deploying RabbitMQ..."
    
    # Delete existing init job if it exists
    echo "Cleaning up existing RabbitMQ init job if present..."
    oc delete job rabbitmq-init -n $ns --ignore-not-found=true
    
    oc apply -f $MANIFEST_DIR/06-rabbitmq.yaml -n $ns
    oc rollout status statefulset/rabbitmq -n $ns --timeout=5m || true
    
    echo "  Waiting for RabbitMQ init job..."
    oc wait --for=condition=complete job/rabbitmq-init -n $ns --timeout=3m || true
else
    echo "    RabbitMQ already deployed"
fi

# ClickHouse
if [ "$RELEASE_ALL" = "true" ] || [ ! "$(oc get statefulset clickhouse -n $ns 2>/dev/null)" ]; then
    echo "Deploying ClickHouse..."
    
    # Delete existing init job if it exists (Job specs are immutable)
    echo "Cleaning up existing ClickHouse init job if present..."
    oc delete job clickhouse-init -n $ns --ignore-not-found=true
    
    oc apply -f $MANIFEST_DIR/08-clickhouse.yaml -n $ns
    echo "  Waiting for ClickHouse StatefulSet..."
    oc rollout status statefulset/clickhouse -n $ns --timeout=5m || true
    
    echo "  Waiting for ClickHouse init job to complete..."
    oc wait --for=condition=complete job/clickhouse-init -n $ns --timeout=3m || true
    
    echo "ClickHouse deployment complete!"
else
    echo "    ClickHouse already deployed"
fi

# Neo4j
if [ "$RELEASE_ALL" = "true" ] || [ ! "$(oc get statefulset neo4j -n $ns 2>/dev/null)" ]; then
    echo "Deploying Neo4j Graph Database..."
    
    oc apply -f $MANIFEST_DIR/07-neo4j.yaml -n $ns
    echo "  Waiting for Neo4j to be ready..."
    oc rollout status statefulset/neo4j -n $ns --timeout=5m || true
    
    echo "Initializing Neo4j schema..."
    # Delete existing init job if it exists
    echo "Cleaning up existing Neo4j init job if present..."
    oc delete job neo4j-init -n $ns --ignore-not-found=true
    
    oc apply -f $MANIFEST_DIR/08-neo4j-init.yaml -n $ns
    oc wait --for=condition=complete job/neo4j-init -n $ns --timeout=3m || true
    
    echo "Neo4j deployment complete!"
else
    echo "    Neo4j already deployed"
fi

# Run Migrations
echo "Running Database Migrations..."
oc apply -f $MANIFEST_DIR/03-migrations-job.yaml -n $ns || true
sleep 10

echo "Infrastructure deployment completed!"
echo ""
echo " Infrastructure Status:"
oc get pods -l tier=database -n $ns || true

