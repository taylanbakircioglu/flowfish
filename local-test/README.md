# Flowfish Local Kubernetes Deployment

Deploy the full Flowfish platform on any Kubernetes cluster (K3s, Docker Desktop, minikube, kind, etc.) using pre-built Docker Hub images.

## Quick Start

### One-Line Install

```bash
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/local-test/deploy.sh | bash -s install
```

### Manual Install

```bash
REPO="https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/local-test"

kubectl apply -f $REPO/00-namespace.yaml
kubectl apply -f $REPO/01-rbac.yaml
kubectl apply -f $REPO/02-databases.yaml

# Wait for databases
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish-local --timeout=120s
kubectl wait --for=condition=ready pod -l app=clickhouse -n flowfish-local --timeout=120s

kubectl apply -f $REPO/03-migrations.yaml

# Wait for migrations
kubectl wait --for=condition=complete job/flowfish-migrations -n flowfish-local --timeout=180s

kubectl apply -f $REPO/04-backend.yaml
kubectl apply -f $REPO/05-cluster-manager.yaml
kubectl apply -f $REPO/06-analysis-orchestrator.yaml
kubectl apply -f $REPO/07-ingestion-service.yaml
kubectl apply -f $REPO/08-graph-query.yaml
kubectl apply -f $REPO/09-timeseries-query.yaml
kubectl apply -f $REPO/10-graph-writer.yaml
kubectl apply -f $REPO/11-timeseries-writer.yaml
kubectl apply -f $REPO/12-change-detection-worker.yaml
kubectl apply -f $REPO/13-frontend.yaml
kubectl apply -f $REPO/14-nginx-proxy.yaml
```

## Access

| Interface | URL |
|-----------|-----|
| **UI** | `http://<NODE_IP>:30080` |
| **API Health** | `http://<NODE_IP>:30080/api/v1/health` |
| **API Docs** | `http://<NODE_IP>:30080/api/docs` |

**Login:** `admin` / `admin123`

For Docker Desktop or minikube, `<NODE_IP>` is `localhost`.

## Architecture

```
00-namespace          Namespace (flowfish-local)
01-rbac               ServiceAccount, ClusterRole, ClusterRoleBinding
02-databases          PostgreSQL, ClickHouse, Redis, Neo4j, RabbitMQ
03-migrations         Schema + seed data (PostgreSQL + ClickHouse)
04-backend            FastAPI REST API + WebSocket
05-cluster-manager    Kubernetes API gateway (gRPC)
06-analysis-orch.     Analysis lifecycle orchestrator (gRPC)
07-ingestion-svc      eBPF event ingestion (gRPC)
08-graph-query        Neo4j query service (REST)
09-timeseries-query   ClickHouse query service (REST)
10-graph-writer       Neo4j batch writer (worker)
11-timeseries-writer  ClickHouse batch writer (worker)
12-change-detection   Change detection worker
13-frontend           React UI
14-nginx-proxy        Reverse proxy (NodePort 30080)
```

## Commands

```bash
# Status
kubectl get pods -n flowfish-local

# Logs
kubectl logs -l app=backend -n flowfish-local -f

# Restart (re-pull latest images)
kubectl rollout restart deployment -n flowfish-local

# Uninstall
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/local-test/deploy.sh | bash -s uninstall
```

## Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Flowfish UI | admin | admin123 |
| PostgreSQL | flowfish | flowfish123 |
| Neo4j | neo4j | flowfish123 |
| ClickHouse | flowfish | flowfish123 |
| Redis | — | redis123 |
| RabbitMQ | flowfish | flowfish123 |

## Important: Inspektor Gadget (eBPF Data Collection)

Flowfish uses **Inspektor Gadget** to collect eBPF-based network, process, and security events.
Without it, analyses will start but **event counts will remain at 0**.

Inspektor Gadget runs as a privileged DaemonSet and requires:
- **Linux kernel 5.4+** with BTF support
- **amd64 (x86_64) architecture** — ARM64 (Apple Silicon) is not supported
- Privileged container access

**If your local cluster does not meet these requirements** (e.g. Docker Desktop on macOS/ARM),
the recommended approach is to **add a remote cluster** that has Inspektor Gadget installed.

### Adding a Remote Cluster (Recommended for Local Testing)

Instead of monitoring the local cluster, add an external K3s/K8s cluster:

1. On the **remote cluster**, create a read-only ServiceAccount:

```bash
kubectl create serviceaccount flowfish-reader -n default
kubectl create clusterrolebinding flowfish-reader-binding \
  --clusterrole=cluster-admin \
  --serviceaccount=default:flowfish-reader
TOKEN=$(kubectl create token flowfish-reader -n default --duration=8760h)
API_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
echo "API Server: $API_SERVER"
echo "Token: $TOKEN"
```

2. In Flowfish UI: **Clusters** > **Add Cluster** > Connection type: **Token**
3. Paste the **API Server URL** and **Token** from the output above

### Adding the Host Cluster (In-Cluster)

If Inspektor Gadget is installed on the same cluster:

1. Go to **Clusters** > **Add Cluster**
2. Select **In-Cluster** connection type
3. Enter a name and click **Save**

## Troubleshooting

```bash
# Check pod events
kubectl describe pod <pod-name> -n flowfish-local

# Database connectivity
kubectl exec -n flowfish-local deploy/postgresql -- pg_isready -U flowfish

# NodePort conflict (change 30080 in 14-nginx-proxy.yaml if needed)
kubectl get svc --all-namespaces | grep 30080
```
