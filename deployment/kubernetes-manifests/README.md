# Flowfish Kubernetes Manifests

This directory contains Kubernetes manifest files for deploying Flowfish platform.

## ⚠️ RBAC - Manuel Uygulama Gerekli

Pipeline **ClusterRole** ve **ClusterRoleBinding** oluşturmaz. Bu kaynaklar **cluster admin** tarafından manuel uygulanmalıdır.

### Pipeline'ın Uyguladığı RBAC (Namespace-scoped)
- ✅ `ServiceAccount` (flowfish, inspektor-gadget)
- ✅ `Role` (namespace içi izinler)
- ✅ `RoleBinding` (namespace içi bağlamalar)

### Manuel Uygulanması Gereken RBAC (Cluster-scoped)

| Kaynak | Dosya | Açıklama |
|--------|-------|----------|
| `ClusterRole: inspektor-gadget` | `10-inspektor-gadget-rbac-cluster.yaml` | Gadget DaemonSet izinleri |
| `ClusterRoleBinding: inspektor-gadget` | `10-inspektor-gadget-rbac-cluster.yaml` | Gadget SA bağlaması |
| `ClusterRole: flowfish-gadget-reader` | `../manual-rbac/flowfish-cluster-rbac.yaml` | kubectl-gadget izinleri |
| `ClusterRoleBinding: flowfish-gadget-reader-binding` | `../manual-rbac/flowfish-cluster-rbac.yaml` | Flowfish SA bağlaması |

### Manuel RBAC Uygulama Komutları

```bash
NS=pilot-flowfish

# 1. Inspektor Gadget ClusterRole (Gadget DaemonSet için)
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: inspektor-gadget
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces", "configmaps", "services", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: inspektor-gadget
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: inspektor-gadget
subjects:
- kind: ServiceAccount
  name: inspektor-gadget
  namespace: pilot-flowfish
EOF

# 2. Flowfish kubectl-gadget izinleri (ingestion-service için)
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flowfish-gadget-reader
rules:
- apiGroups: [""]
  resources: ["pods", "namespaces", "nodes"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flowfish-gadget-reader-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flowfish-gadget-reader
subjects:
- kind: ServiceAccount
  name: flowfish
  namespace: pilot-flowfish
EOF

# 3. Privileged SCC (Inspektor Gadget DaemonSet için)
oc adm policy add-scc-to-user privileged -z inspektor-gadget -n $NS
```

### RBAC Doğrulama

```bash
NS=pilot-flowfish

# ClusterRole'leri kontrol et
oc get clusterrole | grep -E "inspektor-gadget|flowfish-gadget"

# ClusterRoleBinding'leri kontrol et
oc get clusterrolebinding | grep -E "inspektor-gadget|flowfish-gadget"

# İzin testi
oc auth can-i list pods --as=system:serviceaccount:$NS:flowfish -A
oc auth can-i list pods --as=system:serviceaccount:$NS:inspektor-gadget -A
```

---

## 📋 Dosyalar

| Dosya | Açıklama | Pipeline |
|-------|----------|----------|
| `01-rbac.yaml` | ServiceAccount, Role, RoleBinding | ✅ Deploy eder |
| `02-rbac.yaml` | Backend/Frontend ServiceAccounts | ✅ Deploy eder |
| `03-configmaps.yaml` | Konfigürasyon verileri | ✅ Deploy eder |
| `03-migrations-job.yaml` | PostgreSQL/ClickHouse migrations | ✅ Deploy eder |
| `05-postgresql.yaml` | PostgreSQL StatefulSet | ✅ Deploy eder |
| `06-redis.yaml` | Redis Deployment | ✅ Deploy eder |
| `07-neo4j.yaml` | Neo4j StatefulSet | ✅ Deploy eder |
| `08-clickhouse.yaml` | ClickHouse StatefulSet | ✅ Deploy eder |
| `08-rabbitmq.yaml` | RabbitMQ StatefulSet | ✅ Deploy eder |
| `09-inspektor-gadget-config.yaml` | Gadget ConfigMap | ✅ Deploy eder |
| `10-inspektor-gadget.yaml` | Gadget DaemonSet + Service | ✅ Deploy eder |
| `10-inspektor-gadget-rbac-cluster.yaml` | Gadget ClusterRole | ❌ **Manuel** |
| `10-ingestion-service.yaml` | Ingestion Service Deployment | ✅ Deploy eder |
| `11-backend.yaml` | Backend Deployment | ✅ Deploy eder |
| `11-timeseries-writer.yaml` | Timeseries Writer (ClickHouse + Change Events) | ✅ Deploy eder |
| `12-frontend.yaml` | Frontend Deployment | ✅ Deploy eder |
| `18-change-detection-worker.yaml` | Change Detection Worker (Hybrid Architecture) 🆕 | ✅ Deploy eder |

---

## 🚀 Deployment Sırası

### İlk Kurulum (Cluster Admin)

```bash
# 1. Manuel RBAC uygula (yukarıdaki komutları çalıştır)
# 2. SCC izinleri ver
oc adm policy add-scc-to-user privileged -z inspektor-gadget -n pilot-flowfish
```

### Pipeline Deployment

Pipeline aşağıdaki sırayla deploy eder:
1. Namespace-scoped RBAC (ServiceAccount, Role, RoleBinding)
2. ConfigMaps ve Secrets
3. Databases (PostgreSQL, ClickHouse, Neo4j, Redis, RabbitMQ)
4. Migration Jobs
5. Inspektor Gadget DaemonSet
6. Application Services (ingestion-service, backend, frontend, timeseries-writer)
7. Change Detection Worker (18-change-detection-worker.yaml) 🆕

---

## 🔍 Troubleshooting

### Inspektor Gadget Pod'ları Başlamıyor

```bash
# SCC kontrolü
oc get pod -n $NS -l app=inspektor-gadget -o yaml | grep -A5 "securityContext"

# ClusterRole kontrolü
oc auth can-i list pods --as=system:serviceaccount:$NS:inspektor-gadget -A
```

### ingestion-service kubectl-gadget Çalışmıyor

```bash
# RBAC kontrolü
oc auth can-i create traces.gadget.kinvolk.io --as=system:serviceaccount:$NS:flowfish -A

# Pod içinden test
oc exec -n $NS $(oc get pods -n $NS -l app=ingestion-service -o jsonpath='{.items[0].metadata.name}') -- \
  kubectl gadget version
```

---

## 📚 Ek Dokümantasyon

- `../manual-rbac/README.md` - Manuel RBAC uygulama rehberi
- `OPENSHIFT_GADGET_FIX.md` - Inspektor Gadget troubleshooting
