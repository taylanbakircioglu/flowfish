#!/bin/bash
#
# Flowfish Complete Deployment Script
# Deploys all components in correct order with automatic migrations
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🐟 Flowfish Deployment${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Create namespace
echo -e "\n${BLUE}1. Creating namespace...${NC}"
kubectl apply -f deployment/kubernetes-manifests/00-namespace.yaml

# 2. Create RBAC
echo -e "\n${BLUE}2. Creating RBAC...${NC}"
kubectl apply -f deployment/kubernetes-manifests/01-rbac.yaml

# 3. Create ConfigMaps
echo -e "\n${BLUE}3. Creating ConfigMaps...${NC}"
kubectl apply -f deployment/kubernetes-manifests/02-configmaps.yaml

# 4. Create Secrets
echo -e "\n${BLUE}4. Creating Secrets...${NC}"
kubectl apply -f deployment/kubernetes-manifests/04-secrets.yaml

# 5. Deploy PostgreSQL
echo -e "\n${BLUE}5. Deploying PostgreSQL...${NC}"
kubectl apply -f deployment/kubernetes-manifests/05-postgresql.yaml
echo "Waiting for PostgreSQL..."
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish --timeout=120s

# 6. Deploy Redis
echo -e "\n${BLUE}6. Deploying Redis...${NC}"
kubectl apply -f deployment/kubernetes-manifests/06-redis.yaml
kubectl wait --for=condition=ready pod -l app=redis -n flowfish --timeout=60s

# 7. Deploy RabbitMQ
echo -e "\n${BLUE}7. Deploying RabbitMQ...${NC}"
kubectl apply -f deployment/kubernetes-manifests/06-rabbitmq.yaml
echo "Waiting for RabbitMQ..."
kubectl wait --for=condition=ready pod -l app=rabbitmq -n flowfish --timeout=120s

# 8. Deploy ClickHouse
echo -e "\n${BLUE}8. Deploying ClickHouse...${NC}"
kubectl apply -f deployment/kubernetes-manifests/08-clickhouse.yaml
echo "Waiting for ClickHouse..."
kubectl wait --for=condition=ready pod -l app=clickhouse -n flowfish --timeout=120s

# 9. Deploy NebulaGraph
echo -e "\n${BLUE}9. Deploying NebulaGraph...${NC}"
kubectl apply -f deployment/kubernetes-manifests/07-neo4j.yaml
echo "Waiting for NebulaGraph metad..."
kubectl wait --for=condition=ready pod -l app=neo4j-metad -n flowfish --timeout=120s || true

# 10. Run Migrations (AUTOMATIC!)
echo -e "\n${BLUE}10. Running Database Migrations...${NC}"
kubectl delete job flowfish-migrations -n flowfish --ignore-not-found=true
kubectl apply -f deployment/kubernetes-manifests/03-migrations-job.yaml
echo "Waiting for migrations to complete..."
kubectl wait --for=condition=complete job/flowfish-migrations -n flowfish --timeout=300s

echo -e "${GREEN}✅ Migrations completed!${NC}"

# 11. Deploy Backend
echo -e "\n${BLUE}11. Deploying Backend...${NC}"
kubectl apply -f deployment/kubernetes-manifests/08-backend.yaml
kubectl wait --for=condition=ready pod -l app=backend -n flowfish --timeout=120s

# 12. Deploy Frontend
echo -e "\n${BLUE}12. Deploying Frontend...${NC}"
kubectl apply -f deployment/kubernetes-manifests/09-frontend.yaml
kubectl wait --for=condition=ready pod -l app=frontend -n flowfish --timeout=120s

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Flowfish Deployment Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "\n${BLUE}📊 Cluster Status:${NC}"
kubectl get pods -n flowfish

echo -e "\n${BLUE}🌐 Access URLs:${NC}"
echo "  Frontend: kubectl port-forward -n flowfish svc/frontend 3000:3000"
echo "  Backend:  kubectl port-forward -n flowfish svc/backend 8000:8000"

echo -e "\n${BLUE}✅ Database initialized with:${NC}"
echo "  - clusters table (with localcluster)"
echo "  - analysis_event_types table"
echo "  - ClickHouse event tables (network_flows, dns_queries, process_events)"

echo -e "\n${BLUE}🧪 Quick Test:${NC}"
echo "  kubectl exec -n flowfish postgresql-0 -- psql -U flowfish -d flowfish -c 'SELECT COUNT(*) FROM clusters;'"

