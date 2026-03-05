# 🛠️ Local Development & Test Workflow

## ⚠️ Important: macOS Limitations

**Inspektor Gadget eBPF macOS'te çalışmaz!**
- eBPF Linux kernel özelliği
- macOS/Docker Desktop Kubernetes'te desteklenmiyor
- **Inspektor Gadget testleri local'de SKIP edilecek**
- Diğer tüm bileşenler test edilebilir

## Amaç
Backend, Frontend, Database, API ve diğer kritik değişiklikleri **önce local Kubernetes'te test et** (Inspektor Gadget hariç), başarılı olduktan sonra **uzak OpenShift'e push et**.

---

## 📋 Workflow

```
1. Code Change (Local)
   ↓
2. Local Kubernetes Deploy
   ↓
3. Test & Verify (Local)
   ↓
4. Success? → Git Commit & Push → OpenShift Pipeline
   ↓
5. Fail? → Debug & Fix → Loop back to step 1
```

---

## 🏗️ Local Kubernetes Setup

### Prerequisites

```bash
# Docker Desktop Kubernetes veya Minikube
minikube start --cpus=4 --memory=8g --disk-size=50g
# veya
# Docker Desktop → Preferences → Kubernetes → Enable

# Gerekli tool'lar
brew install kubectl helm
```

### Deploy to Local Kubernetes

```bash
cd /Users/U05395/Documents/flowfish/deployment/kubernetes-manifests

# 1. Namespace oluştur
kubectl apply -f 01-namespace.yaml

# 2. RBAC & Secrets
kubectl apply -f 02-rbac.yaml
kubectl apply -f 03-configmaps.yaml
kubectl apply -f 04-secrets.yaml

# 3. Databases (Local için lightweight)
kubectl apply -f 05-postgresql.yaml
kubectl apply -f 06-redis.yaml

# ClickHouse ve Neo4j opsiyonel (resource-heavy)
# kubectl apply -f 08-clickhouse.yaml
# kubectl apply -f 07-neo4j.yaml

# 4. Run Migrations
kubectl apply -f 03-migrations-job.yaml
kubectl wait --for=condition=complete job/flowfish-migrations -n flowfish --timeout=300s

# 5. Build & Deploy Backend (local image)
cd ../../backend
docker build -t flowfish-backend:local -f Dockerfile ..
kubectl set image deployment/backend backend=flowfish-backend:local -n flowfish
# veya manifest'i local image kullanacak şekilde düzenle

# 6. Deploy Frontend (local image)
cd ../frontend
docker build -t flowfish-frontend:local .
kubectl set image deployment/frontend frontend=flowfish-frontend:local -n flowfish

# 7. Deploy Microservices (eğer değişiklik varsa)
cd ../services/ingestion-service
docker build -t flowfish-ingestion-service:local .
kubectl set image deployment/ingestion-service ingestion-service=flowfish-ingestion-service:local -n flowfish

cd ../analysis-orchestrator
docker build -t flowfish-analysis-orchestrator:local .
kubectl set image deployment/analysis-orchestrator analysis-orchestrator=flowfish-analysis-orchestrator:local -n flowfish

# 8. Inspektor Gadget (SKIP on macOS - eBPF not supported!)
# ❌ SKIP: Inspektor Gadget requires eBPF (Linux only)
# cd ../../deployment/kubernetes-manifests
# kubectl apply -f 09-inspektor-gadget-crds.yaml
# kubectl apply -f 10-inspektor-gadget-rbac-cluster.yaml
# kubectl apply -f 09-inspektor-gadget-config.yaml
# kubectl apply -f 10-inspektor-gadget.yaml

# 9. Ingress (opsiyonel - local)
kubectl apply -f 11-ingress.yaml
```

---

## 🧪 Local Testing

### 1. Check Pod Status

```bash
# Tüm pod'ları kontrol et
kubectl get pods -n flowfish -w

# Beklenecek durum:
# backend-xxx                    1/1     Running
# frontend-xxx                   1/1     Running
# ingestion-service-xxx          1/1     Running
# analysis-orchestrator-xxx      1/1     Running
# inspektor-gadget-xxx           1/1     Running (her node'da)
# postgresql-0                   1/1     Running
# redis-xxx                      1/1     Running
```

### 2. Check Logs

```bash
# Backend logs
kubectl logs -f deployment/backend -n flowfish

# Inspektor Gadget logs
kubectl logs -l app=inspektor-gadget -n flowfish --tail=50

# Migration job logs
kubectl logs job/flowfish-migrations -n flowfish | grep "Migration 006"
```

### 3. Port Forward for UI Access

```bash
# Frontend
kubectl port-forward -n flowfish deployment/frontend 3000:80

# Backend API
kubectl port-forward -n flowfish deployment/backend 8000:8000

# Inspektor Gadget gRPC
kubectl port-forward -n flowfish svc/inspektor-gadget 16060:16060

# Açık tarayıcı:
# http://localhost:3000  → Frontend
# http://localhost:8000  → Backend API
```

### 4. Test Database

```bash
# PostgreSQL'e bağlan
kubectl exec -it deployment/backend -n flowfish -- bash
psql postgresql://flowfish:flowfish123@postgresql:5432/flowfish

# Tabloları kontrol et
\dt

# Cluster'ı kontrol et
SELECT name, gadget_endpoint, gadget_protocol, gadget_health_status FROM clusters;

# Namespaces tablosu var mı?
SELECT * FROM namespaces LIMIT 5;
```

### 5. Test Inspektor Gadget gRPC (⚠️ SKIP on macOS)

```bash
# ❌ SKIP: Inspektor Gadget eBPF macOS'te çalışmaz
# Bu test sadece Linux (OpenShift/production) için geçerli

# grpcurl ile test (Linux'te)
# brew install grpcurl
# grpcurl -plaintext localhost:16060 list
```

### 6. Test Analysis Workflow (Partial on macOS)

#### UI'dan Test:
1. http://localhost:3000 aç
2. Login yap (admin/admin123)
3. **Clusters** sayfası
   - localcluster görünüyor mu?
   - ⚠️ Gadget Health: `UNKNOWN` (normal - Inspektor Gadget yok)
   - Resources: Node/Pod/Namespace sayıları doğru mu?
4. **New Analysis** oluştur
   - Target Cluster: localcluster seç
   - Scope Configuration açılıyor mu?
   - Namespace dropdown dolu mu?
   - ❌ Hata yok mu?
5. **Start Analysis** ⚠️ SKIP (Inspektor Gadget gerektirir)
   - ❌ Local'de analysis start etmeyin (fail eder)
   - ✅ Analysis CRUD işlemlerini test edin (create, read, update, delete)
   - ✅ Analysis configuration'ı test edin
   - ⚠️ Start/Stop işlemleri sadece OpenShift'te test edilecek

#### API'dan Test:
```bash
# Health check
curl http://localhost:8000/health

# Get clusters
curl http://localhost:8000/api/v1/clusters

# Get namespaces (scope configuration için)
curl "http://localhost:8000/api/v1/namespaces?cluster_id=1"
```

---

## ✅ Success Criteria (Local Test - macOS)

Tüm bunlar başarılıysa **git push** yapabilirsiniz:

- [ ] Pod'lar Running (backend, frontend, postgresql, redis)
- [ ] Migration job Completed
- [ ] Namespaces tablosu var
- [ ] Workloads tablosu var
- [ ] localcluster database'de var
- [ ] UI'da cluster görünüyor
- [ ] Scope Configuration çalışıyor (namespace dropdown dolu)
- [ ] Analysis CRUD işlemleri çalışıyor
- [ ] Backend log'ları hatasız (Inspektor Gadget connection errors normal)
- [ ] ⚠️ SKIP: Inspektor Gadget (macOS'te çalışmaz)
- [ ] ⚠️ SKIP: Analysis Start/Stop (Inspektor Gadget gerektirir)

**Not:** Analysis execution (start/stop) **sadece OpenShift'te test edilecek**

---

## 🚀 Deploy to OpenShift (After Local Success)

```bash
# Local test başarılıysa:
git add -A
git commit -m "feature: Your changes here"
git push origin pilot

# OpenShift'te pipeline otomatik tetiklenecek
# Aynı testleri OpenShift'te de yap
```

---

## 🐛 Debugging Local Issues

### Backend Crash Loop

```bash
# Logs
kubectl logs deployment/backend -n flowfish --previous

# Events
kubectl describe pod <backend-pod> -n flowfish

# Common issues:
# - Proto modules missing → Check Dockerfile proto generation
# - Database connection → Check postgresql pod status
# - Environment vars → Check configmap/secrets
```

### Inspektor Gadget Issues

```bash
# Logs
kubectl logs -l app=inspektor-gadget -n flowfish --tail=100

# Check CRD
kubectl get crd traces.gadget.kinvolk.io

# Check RBAC
kubectl get clusterrole inspektor-gadget
kubectl get clusterrolebinding inspektor-gadget

# Common issues:
# - CRD not installed → Apply 09-inspektor-gadget-crds.yaml
# - RBAC missing → Apply 10-inspektor-gadget-rbac-cluster.yaml
# - ConfigMap missing → Apply 09-inspektor-gadget-config.yaml
```

### Database Migration Issues

```bash
# Check job status
kubectl get jobs -n flowfish

# View logs
kubectl logs job/flowfish-migrations -n flowfish

# Re-run migration
kubectl delete job flowfish-migrations -n flowfish
kubectl apply -f 03-migrations-job.yaml
```

---

## 🔄 Quick Test Script

```bash
#!/bin/bash
# test-local.sh

echo "🧪 Testing Flowfish Local Deployment..."

# 1. Check pods
echo "1️⃣ Checking pods..."
kubectl get pods -n flowfish | grep -v "Running\|Completed" && echo "❌ Some pods not ready!" || echo "✅ All pods ready"

# 2. Check migrations
echo "2️⃣ Checking migrations..."
kubectl logs job/flowfish-migrations -n flowfish 2>/dev/null | grep -q "Migration 006 completed" && echo "✅ Migrations OK" || echo "❌ Migration failed"

# 3. Test backend API
echo "3️⃣ Testing backend API..."
kubectl port-forward -n flowfish deployment/backend 8000:8000 &
PF_PID=$!
sleep 2
curl -s http://localhost:8000/health | grep -q "ok" && echo "✅ Backend API OK" || echo "❌ Backend API failed"
kill $PF_PID

# 4. Test database
echo "4️⃣ Testing database tables..."
kubectl exec -it deployment/backend -n flowfish -- psql postgresql://flowfish:flowfish123@postgresql:5432/flowfish -c "\dt" | grep -q "namespaces" && echo "✅ Namespaces table exists" || echo "❌ Namespaces table missing"

# 5. Test Inspektor Gadget
echo "5️⃣ Testing Inspektor Gadget..."
kubectl get pods -l app=inspektor-gadget -n flowfish | grep -q "Running" && echo "✅ Inspektor Gadget running" || echo "❌ Inspektor Gadget not running"

echo ""
echo "🎯 Local test complete!"
```

---

## 📝 macOS Specific Notes

### ❌ Cannot Test on macOS (Linux/OpenShift Only)
- **Inspektor Gadget** - eBPF requires Linux kernel
- **Analysis Start/Stop** - Depends on Inspektor Gadget
- **eBPF Event Collection** - Requires Linux

### ✅ Can Test on macOS
- **Backend API** - All endpoints
- **Frontend UI** - All pages
- **Database** - PostgreSQL, Redis (ClickHouse/Neo4j optional)
- **Migrations** - All migrations
- **Cluster CRUD** - Create, Read, Update, Delete clusters
- **Analysis CRUD** - Create, Read, Update, Delete analyses
- **Namespace/Workload Discovery** - List namespaces, pods, etc.
- **User Authentication** - Login, JWT, RBAC
- **Scope Configuration** - Namespace dropdown, scope selection

### 💡 Testing Strategy
1. **Test locally** (macOS): Backend, Frontend, Database, APIs
2. **Push to OpenShift**: If local tests pass
3. **Test on OpenShift**: Inspektor Gadget, Analysis execution

## 📝 General Notes

- **Local Kubernetes** resources daha düşük olabilir (replica=1)
- **ClickHouse/Neo4j** local'de skip edilebilir (optional)
- **Ingress** local'de port-forward ile test edilebilir
- **Image pull policy**: Local'de `imagePullPolicy: Never` kullan
- **Volume mounts**: Local'de PV yerine `emptyDir` kullanılabilir

---

## 🎓 Best Practices

1. **Her değişiklikte local test et**
2. **Migration'ları önce local'de dene**
3. **Log'ları kaydet** (troubleshooting için)
4. **Success criteria'yı takip et**
5. **Local test başarısızsa push etme**
6. **OpenShift'te de aynı testleri yap**

---

**Local test başarılıysa → Git push → OpenShift deploy! 🚀**

