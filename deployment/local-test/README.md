# Flowfish Local Kubernetes Deployment

Deploy the full Flowfish platform on any Kubernetes cluster (K3s, Docker Desktop, minikube, kind, etc.) using pre-built Docker Hub images.

## Quick Start

### One-Line Install

```bash
# Standard install (Flowfish platform only)
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s install

# Full install with Inspektor Gadget (enables local eBPF analysis)
# Requires: amd64 Linux, kernel 5.4+
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s install-with-gadget
```

### Manual Install

```bash
REPO="https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test"

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

# OPTIONAL: Deploy Inspektor Gadget for local eBPF data collection
# Only on amd64 Linux clusters with kernel 5.4+
kubectl apply -f $REPO/15-inspektor-gadget.yaml
```

> **Tip:** You can also clone the repo and apply manifests directly from `deployment/local-test/`:
> ```bash
> kubectl apply -f deployment/local-test/00-namespace.yaml
> # ... etc.
> ```

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
03-migrations         Schema + seed data (PostgreSQL, ClickHouse, RabbitMQ)
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
15-inspektor-gadget   [OPTIONAL] eBPF DaemonSet (amd64 Linux only)
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
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s uninstall
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

## Inspektor Gadget (eBPF Data Collection)

Flowfish uses **Inspektor Gadget** to collect eBPF-based network, DNS, process, and security events.
Without it, analyses will complete but **all event counts will remain at 0** — this includes
the Dashboard (connections, traffic, DNS), Dependency Map, and Network Explorer.

### Supported Platforms

The Gadget DaemonSet automatically detects the container runtime socket path at pod startup
via an init container. No manual configuration is needed.

| Platform | Containerd Socket | Status |
|----------|------------------|--------|
| **Standard K8s** (kubeadm, GKE, EKS, AKS) | `/run/containerd/containerd.sock` | Auto-detected |
| **K3s** | `/run/k3s/containerd/containerd.sock` | Auto-detected |
| **RKE2** | `/run/k3s/containerd/containerd.sock` | Auto-detected |
| **MicroK8s** | `/var/snap/microk8s/common/run/containerd.sock` | Auto-detected |
| **OpenShift** (CRI-O) | `/run/crio/crio.sock` | Configured via `crio-socketpath` |

> **Docker Compose users:** Inspektor Gadget is a Kubernetes-native DaemonSet and cannot run
> in Docker Compose. It requires the Kubernetes API for pod/container discovery and metadata
> enrichment. If you deployed Flowfish via Docker Compose, add a remote Kubernetes cluster
> via **Token** method in the UI (Clusters > Add Cluster > Token) to collect eBPF events.

### Option A: Deploy Gadget Locally (amd64 Linux only)

If your cluster runs on **amd64 (x86_64) Linux** with **kernel 5.4+**, you can deploy
Inspektor Gadget directly alongside Flowfish:

```bash
# If you used the deploy.sh script:
curl -sL https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/deploy.sh | bash -s install-with-gadget

# Or apply the manifest manually:
kubectl apply -f https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test/15-inspektor-gadget.yaml

# Verify the DaemonSet is running:
kubectl get pods -l app=inspektor-gadget -n flowfish-local
```

After Gadget pods are Running, add your cluster as **In-Cluster**:
1. Go to **Clusters** > **Add Cluster**
2. Select **In-Cluster** connection type
3. Enter a name and click **Save**

You can now start analyses and see real eBPF network data.

**Important:** ARM64 (Apple Silicon / M-series Mac) is **not supported** by Inspektor Gadget.
If you are on ARM64, use Option B below.

### Option B: Add a Remote Cluster (any platform)

If your local machine is ARM64, or you want to analyze a different cluster:

1. Deploy Flowfish locally (standard install, without Gadget)
2. On the **target cluster** (the one you want to analyze), run the setup script
   generated by Flowfish, or manually create a ServiceAccount:

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

3. In Flowfish UI: **Clusters** > **Add Cluster** > Connection type: **Token**
4. Paste the **API Server URL** and **Token** from the output above
5. Inspektor Gadget must be installed on the target cluster for eBPF events

Alternatively, in the Flowfish UI cluster add screen, click **"Get Setup Scripts"** to
download an auto-generated script for your provider. This script automatically installs
Inspektor Gadget, creates the ServiceAccount/RBAC, and outputs the required values
(API Server URL, Token, CA Certificate, Gadget Namespace) to paste into the form.

### Option C: Full Production Install on Target Cluster

For comprehensive monitoring, deploy Flowfish directly on the cluster you want to analyze
using the production manifests (`deployment/kubernetes-manifests/`). This includes
Inspektor Gadget DaemonSet, and you can use **In-Cluster** connection type.

## Troubleshooting

```bash
# Check pod events
kubectl describe pod <pod-name> -n flowfish-local

# Database connectivity
kubectl exec -n flowfish-local deploy/postgresql -- pg_isready -U flowfish

# NodePort conflict (change 30080 in 14-nginx-proxy.yaml if needed)
kubectl get svc --all-namespaces | grep 30080
```
