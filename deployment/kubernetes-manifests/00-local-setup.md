# Flowfish Local Development Setup

Bu rehber, Flowfish'i minikube üzerinde local development için kurmanızı sağlar.

## 🚀 Hızlı Başlangıç

### Ön Gereksinimler

```bash
# Docker kurulu ve çalışıyor olmalı
docker --version

# Minikube kurulumu (if not installed)
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-darwin-amd64
sudo install minikube-darwin-amd64 /usr/local/bin/minikube

# kubectl kurulumu (if not installed)  
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/darwin/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/kubectl
```

### Minikube Başlatma

```bash
# Minikube'u başlat (yeterli resource ile)
minikube start \
  --cpus=4 \
  --memory=8g \
  --disk-size=50g \
  --driver=docker

# Ingress addon'unu etkinleştir
minikube addons enable ingress

# Dashboard (optional)
minikube addons enable dashboard
minikube addons enable metrics-server
```

### Flowfish Deployment

```bash
# Proje klasörüne git
cd flowfish/deployment/kubernetes-manifests

# Tüm manifest'leri uygula (sıralı)
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-rbac.yaml
kubectl apply -f 03-configmaps.yaml
kubectl apply -f 04-secrets.yaml

# Veritabanlarını başlat
kubectl apply -f 05-postgresql.yaml
kubectl apply -f 06-redis.yaml
kubectl apply -f 08-clickhouse.yaml
kubectl apply -f 07-neo4j.yaml

# Veritabanlarının hazır olmasını bekle
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n flowfish --timeout=120s
kubectl wait --for=condition=ready pod -l app=clickhouse -n flowfish --timeout=300s
kubectl wait --for=condition=ready pod -l app=neo4j -n flowfish --timeout=300s

# Uygulama katmanını başlat
kubectl apply -f 08-backend.yaml
kubectl apply -f 09-frontend.yaml

# Inspektor Gadget'ı başlat
kubectl apply -f 10-inspektor-gadget.yaml

# Ingress'i başlat
kubectl apply -f 11-ingress.yaml

# Uygulamanın hazır olmasını bekle
kubectl wait --for=condition=ready pod -l app=backend -n flowfish --timeout=300s
kubectl wait --for=condition=ready pod -l app=frontend -n flowfish --timeout=120s
```

### Hosts Dosyası Güncellemesi

```bash
# Minikube IP'sini öğren
minikube ip

# /etc/hosts dosyasını güncelle
echo "$(minikube ip) flowfish.local" | sudo tee -a /etc/hosts
```

### Erişim

```bash
# Web UI'ya erişim
open http://flowfish.local

# Alternatif: Port-forward kullanarak
kubectl port-forward svc/frontend -n flowfish 3000:3000
open http://localhost:3000

# Backend API'sine erişim
curl http://flowfish.local/api/v1/health
```

**Default Credentials:**
- Username: `admin`
- Password: `admin123`

## 📊 Monitoring ve Debug

### Pod Status Kontrolü

```bash
# Tüm pod'ları kontrol et
kubectl get pods -n flowfish

# Detaylı durum
kubectl get pods -n flowfish -o wide

# Pod loglarını görüntüle
kubectl logs -l app=backend -n flowfish -f
kubectl logs -l app=frontend -n flowfish -f
kubectl logs -l app=postgresql -n flowfish

# Service'leri kontrol et
kubectl get svc -n flowfish

# Ingress kontrol
kubectl get ingress -n flowfish
```

### Database Bağlantı Testleri

```bash
# PostgreSQL test
kubectl exec -it deployment/postgresql -n flowfish -- \
  psql -U flowfish -d flowfish -c "SELECT version();"

# Redis test  
kubectl exec -it deployment/redis -n flowfish -- \
  redis-cli -a redis123 ping

# ClickHouse test
kubectl exec -it statefulset/clickhouse -n flowfish -- \
  clickhouse-client --query "SELECT version()"

# Neo4j test
kubectl exec -it statefulset/neo4j -n flowfish -- \
  cypher-shell -u neo4j -p flowfish123 "RETURN 'Neo4j is ready!' AS status"
```

### Resource Usage

```bash
# Resource kullanımını kontrol et
kubectl top pods -n flowfish
kubectl top nodes

# Persistent Volumes
kubectl get pv
kubectl get pvc -n flowfish
```

## 🔧 Troubleshooting

### Yaygın Sorunlar

**1. Pod'lar başlamıyor:**
```bash
kubectl describe pod <pod-name> -n flowfish
kubectl logs <pod-name> -n flowfish
```

**2. Database bağlantı hatası:**
```bash
# PostgreSQL pod'un hazır olduğunu kontrol et
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish

# Connection string'i kontrol et
kubectl get secret database-credentials -n flowfish -o yaml
```

**3. Ingress çalışmıyor:**
```bash
# Nginx ingress controller'ı kontrol et
kubectl get pods -n ingress-nginx

# Minikube ingress addon'u aktif mi?
minikube addons list | grep ingress
```

**4. Resource yetersizliği:**
```bash
# Minikube resource'larını artır
minikube stop
minikube start --cpus=6 --memory=12g --disk-size=80g
```

### Log Toplama

```bash
# Tüm pod loglarını topla
mkdir -p logs
kubectl logs -l app=backend -n flowfish > logs/backend.log
kubectl logs -l app=frontend -n flowfish > logs/frontend.log
kubectl logs -l app=postgresql -n flowfish > logs/postgres.log
kubectl logs -l app=clickhouse -n flowfish > logs/clickhouse.log
```

## 🧹 Cleanup

```bash
# Tüm Flowfish kaynaklarını sil
kubectl delete -f . -n flowfish

# Namespace'i sil (tüm kaynaklar silinir)
kubectl delete namespace flowfish
kubectl delete namespace gadget

# Minikube'u durdur/sil
minikube stop
# minikube delete  # Tam olarak silmek için
```

## 🔄 Update/Restart

```bash
# Backend'i yeniden başlat
kubectl rollout restart deployment/backend -n flowfish

# Frontend'i yeniden başlat  
kubectl rollout restart deployment/frontend -n flowfish

# Veritabanını yeniden başlat
kubectl rollout restart statefulset/postgresql -n flowfish
```

## 📝 Development Tips

### Local Development İçin Image Build

```bash
# Backend image build (varsa)
eval $(minikube docker-env)
docker build -t flowfish/backend:dev ./backend

# Frontend image build (varsa)  
docker build -t flowfish/frontend:dev ./frontend

# Image'ları kullan
kubectl set image deployment/backend backend=flowfish/backend:dev -n flowfish
kubectl set image deployment/frontend frontend=flowfish/frontend:dev -n flowfish
```

### Configuration Değişiklikleri

```bash
# ConfigMap'i güncelle
kubectl apply -f 03-configmaps.yaml

# Pod'ları restart et (config değişiklikleri için)
kubectl rollout restart deployment/backend -n flowfish
kubectl rollout restart deployment/frontend -n flowfish
```

---

## 🎯 Next Steps

1. Web UI'ya giriş yap (`admin` / `admin123`)
2. İlk cluster'ı ekle (minikube local cluster)
3. İlk analizi oluştur
4. Live dependency map'i görüntüle

**Sorun olursa:** GitHub Issues'a yazabilirsiniz veya loglaru paylaşın.

**Happy Coding! 🐟🌊**
