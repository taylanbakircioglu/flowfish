# 🚀 Flowfish - Mevcut Durum ve Erişim Bilgileri

## ✅ Kurulum Durumu

**Tarih**: 21 Kasım 2025  
**Mevcut Sprint**: Sprint 5-6 (Analysis Wizard & Communication Discovery) - BAŞLAYACAK  
**Tamamlanan Sprintler**: Sprint 1-4 ✅

---

## 🌐 Erişim Bilgileri

### 🔗 Web Arayüzü
```
URL: http://localhost/
veya
URL: http://flowfish.local  (eğer hosts dosyasına eklediyseniz)
```

### 🔐 Login Bilgileri
```
Username: admin
Password: admin123
```

### 📡 Backend API
```
Base URL: http://localhost/api/v1/
Health Check: http://localhost/api/v1/health
API Docs (Swagger): http://localhost/api/v1/docs
```

---

## 📊 Test Senaryosu

### 1️⃣ Login ve Ana Sayfa
```bash
# 1. Tarayıcıda açın
open http://localhost/

# 2. Login sayfası açılacak
# Giriş bilgileri:
Username: admin
Password: admin123

# 3. Login olduğunuzda "Home" sayfası açılacak
# Burada 4 adet metrik kartı göreceksiniz:
- Total Clusters: 1
- Active Analyses: 0
- Active Anomalies: 0
- Risk Score: 0
```

### 2️⃣ Cluster Management (Tamamlanmış ✅)
```bash
# Sol menüden: Management → Clusters

İşlemler:
✅ Cluster listesi görme
✅ Yeni cluster ekleme (Add Cluster butonu)
✅ Cluster düzenleme (Edit butonu)
✅ Cluster silme (Delete butonu)
✅ Health status kontrolü

Test için:
1. "Add Cluster" butonuna tıklayın
2. Cluster bilgilerini doldurun:
   - Name: test-cluster
   - Type: kubernetes
   - API URL: https://kubernetes.default.svc
   - Description: Test cluster
3. "Create" butonuna tıklayın
```

### 3️⃣ Application Inventory (Tamamlanmış ✅)
```bash
# Sol menüden: Discovery → Application Inventory

Özellikler:
✅ Workload listesi (Pods, Deployments, Services, StatefulSets)
✅ Namespace filtreleme
✅ Workload type filtreleme
✅ Search functionality
✅ İstatistik kartları
✅ Discover Workloads butonu

Not: Şu anda workload verileri boş olabilir çünkü 
gerçek bir Kubernetes cluster'a bağlanmadık.
```

### 4️⃣ Diğer Sayfalar (Placeholder - Sprint 5+ için)
```bash
Şu anki durumları:

📊 Analysis → Analysis Wizard
   Status: "Coming Soon" (Sprint 5-6'da implement edilecek)
   
🌐 Discovery → Live Map
   Status: "Coming Soon" (Sprint 7-8'de implement edilecek)
   
⚠️ Security → Anomaly Detection
   Status: "Coming Soon" (Sprint 15-16'da implement edilecek)
   
🔄 Security → Change Detection
   Status: "Coming Soon" (Sprint 13-14'te implement edilecek)
```

---

## 🎯 Şu Anda Çalışan Özellikler (Sprint 1-4)

### ✅ Backend
- [x] **Authentication**: JWT login çalışıyor
- [x] **Health Check**: `/api/v1/health` endpoint aktif
- [x] **Cluster Management**: Full CRUD operations
- [x] **Database**: PostgreSQL, Redis, ClickHouse, Neo4j bağlantıları
- [x] **Kubernetes Integration**: K8s API client hazır
- [x] **Workload Discovery**: Pod, Deployment, Service, StatefulSet discovery

### ✅ Frontend
- [x] **Login Page**: Beautiful login interface
- [x] **Dashboard Layout**: Header + Sidebar + Content
- [x] **Navigation**: Tüm menü yapısı
- [x] **Cluster Management**: Full CRUD interface
- [x] **Application Inventory**: Workload explorer
- [x] **TypeScript**: Full type safety
- [x] **State Management**: Redux Toolkit + RTK Query

### ✅ DevOps
- [x] **Docker Containers**: Backend + Frontend
- [x] **Kubernetes Deployment**: All pods running
- [x] **Nginx Ingress**: Routing configured
- [x] **Local Development**: Node.js + npm installed

---

## 🧪 API Test Komutları

### Health Check
```bash
curl http://localhost/api/v1/health | jq .
```

### Login
```bash
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq .
```

### Get Clusters
```bash
# Login yapıp token alın
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# Cluster listesini çekin
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost/api/v1/clusters | jq .
```

### Create Cluster
```bash
curl -X POST http://localhost/api/v1/clusters \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-cluster",
    "cluster_type": "kubernetes",
    "api_url": "https://kubernetes.default.svc",
    "description": "Test cluster"
  }' | jq .
```

---

## 📋 Kubernetes Pod Durumu

```bash
# Tüm pod'ları kontrol et
kubectl get pods -n flowfish

Beklenen Çıktı:
NAME                          READY   STATUS    RESTARTS   AGE
backend-xxx                   1/1     Running   0          30m
frontend-xxx                  1/1     Running   0          30m
postgresql-0                  1/1     Running   0          30m
redis-xxx                     1/1     Running   0          30m
clickhouse-0                  1/1     Running   0          30m
```

---

## 🎨 UI Sayfaları ve Durumları

| Sayfa | URL | Durum | Sprint |
|-------|-----|-------|--------|
| Login | `/login` | ✅ Çalışıyor | 1-2 |
| Home | `/dashboard` | ✅ Çalışıyor | 1-2 |
| Cluster Management | `/clusters` | ✅ Çalışıyor | 3-4 |
| Application Inventory | `/inventory` | ✅ Çalışıyor | 3-4 |
| Analysis Wizard | `/analysis/wizard` | ⏳ Placeholder | 5-6 |
| Live Map | `/discovery/live-map` | ⏳ Placeholder | 7-8 |
| Historical Map | `/discovery/historical` | ⏳ Placeholder | 11-12 |
| Anomaly Detection | `/security/anomalies` | ⏳ Placeholder | 15-16 |
| Change Detection | `/security/changes` | ⏳ Placeholder | 13-14 |

---

## 🚀 Sıradaki Geliştirmeler (Sprint 5-6)

### Sprint 5-6: Analysis Wizard & Communication Discovery

**Backend Görevleri:**
- [ ] Analysis wizard API (4-step workflow)
- [ ] Gadget module configuration
- [ ] Analysis execution engine
- [ ] Communication discovery logic
- [ ] ClickHouse integration (gerçek veri)
- [ ] Data enricher (K8s metadata)

**Frontend Görevleri:**
- [ ] Analysis wizard (4 steps):
  1. Scope Selection (Cluster, Namespace, Workload seçimi)
  2. Gadget Modules (Network, DNS, TCP, Process, Syscall)
  3. Time & Profile (Continuous, Time Range, Periodic)
  4. Output & Integration (Dashboard, LLM, Alarms, Webhooks)
- [ ] Analysis list page
- [ ] Analysis detail page
- [ ] Communication list view

**Deliverables:**
- [ ] Create analysis via wizard
- [ ] Start/stop analysis
- [ ] View discovered communications
- [ ] Data flowing to databases

**Tahmini Süre**: 4 hafta (2 sprint)

---

## 📝 Sorun Giderme

### Frontend 404 Hatası
```bash
# Nginx ingress çalışıyor mu kontrol et
kubectl get svc -n ingress-nginx

# Ingress'i kontrol et
kubectl get ingress -n flowfish
```

### Backend Bağlanamıyor
```bash
# Backend pod logları
kubectl logs -n flowfish deployment/backend --tail=50

# Health check
curl http://localhost/api/v1/health
```

### Login Çalışmıyor
```bash
# PostgreSQL bağlantısı kontrol et
kubectl exec -it -n flowfish postgresql-0 -- psql -U flowfish -d flowfish -c "SELECT * FROM users;"

# Backend log kontrol et
kubectl logs -n flowfish deployment/backend | grep -i "login\|auth"
```

---

## 🎯 Development Workflow

### Local Development
```bash
# Frontend development (hot reload)
cd /Users/U05395/Documents/flowfish/frontend
npm start  # http://localhost:3000

# Backend development
cd /Users/U05395/Documents/flowfish/backend
uvicorn main:app --reload  # http://localhost:8000
```

### Kubernetes Deployment
```bash
# Build new images
cd /Users/U05395/Documents/flowfish
docker build -t flowfish/backend:local backend/
docker build -f frontend/Dockerfile.production -t flowfish/frontend:local frontend/

# Update deployments
kubectl set image deployment/backend -n flowfish backend=flowfish/backend:local
kubectl set image deployment/frontend -n flowfish frontend=flowfish/frontend:local
```

---

## ✅ Ready Status

**Status**: 🟢 **READY FOR SPRINT 5-6**

- ✅ Infrastructure (Sprint 1-2)
- ✅ Cluster Management (Sprint 3-4)
- ✅ Local Development Environment
- ✅ TypeScript IDE Support
- ✅ All Pods Running
- ✅ API Accessible
- ✅ UI Accessible

**Next**: Analysis Wizard implementation başlıyor! 🚀

---

**Last Updated**: 21 Kasım 2025, 21:30  
**Environment**: Docker Desktop Kubernetes  
**Namespace**: flowfish

