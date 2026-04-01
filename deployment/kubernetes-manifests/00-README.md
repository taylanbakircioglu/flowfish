# 🐟 Flowfish - Kubernetes Manifests

Bu klasör, Flowfish platformunun Kubernetes/OpenShift deployment dosyalarını içerir.

## Deployment Sırası

Dosyalar **sırayla** deploy edilmelidir:

```bash
# 1. Namespace oluştur
kubectl apply -f 01-namespace.yaml

# 2. RBAC (ServiceAccount, Role, RoleBinding)
kubectl apply -f 02-rbac.yaml

# 3. ConfigMaps
kubectl apply -f 03-configmaps.yaml

# 4. Secrets (dikkat: production'da değiştirin!)
kubectl apply -f 04-secrets.yaml

# 5. Databases

# PostgreSQL (metadata DB)
kubectl apply -f 05-postgresql.yaml

# RabbitMQ (message queue)
kubectl apply -f 06-rabbitmq.yaml

# Redis (cache)
kubectl apply -f 07-redis.yaml

# ClickHouse (time-series DB)
kubectl apply -f 08-clickhouse.yaml

# Neo4j (graph DB)
kubectl apply -f 07-neo4j.yaml

# 6. Backend Microservices
# (Henüz hazır değil - geliştirilecek)
# kubectl apply -f 10-cluster-manager.yaml
# kubectl apply -f 11-analysis-orchestrator.yaml
# kubectl apply-f 12-ingestion-service.yaml
# kubectl apply -f 13-clickhouse-writer.yaml
# kubectl apply -f 14-dependency-graph.yaml

# 7. API Gateway (Backend - FastAPI)
kubectl apply -f 15-backend.yaml

# 8. Frontend (React)
kubectl apply -f 16-frontend.yaml

# 9. Inspektor Gadget (eBPF data collection)
kubectl apply -f 17-inspektor-gadget.yaml

# 10. Ingress (external access)
kubectl apply -f 18-ingress.yaml
```

---

## Tek Komutla Deployment

```bash
# Tüm manifestleri sırayla deploy et
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-rbac.yaml
kubectl apply -f 03-configmaps.yaml
kubectl apply -f 04-secrets.yaml
kubectl apply -f 05-postgresql.yaml
kubectl apply -f 06-rabbitmq.yaml
kubectl apply -f 07-redis.yaml
kubectl apply -f 08-clickhouse.yaml
kubectl apply -f 07-neo4j.yaml
kubectl apply -f 08-backend.yaml
kubectl apply -f 16-frontend.yaml
kubectl apply -f 17-inspektor-gadget.yaml
kubectl apply -f 18-ingress.yaml
```

Veya tüm klasörü deploy et (sıralama garantisiz):
```bash
kubectl apply -f deployment/kubernetes-manifests/
```

---

## Durumu Kontrol Et

```bash
# Tüm pod'ları listele
kubectl get pods -n flowfish

# Servisleri listele
kubectl get svc -n flowfish

# Ingress'i kontrol et
kubectl get ingress -n flowfish

# Persistent Volume Claims
kubectl get pvc -n flowfish

# Tüm kaynakları göster
kubectl get all -n flowfish
```

---

## Pods'ların Hazır Olmasını Bekle

```bash
# PostgreSQL
kubectl wait --for=condition=ready pod -l app=postgresql -n flowfish --timeout=300s

# RabbitMQ
kubectl wait --for=condition=ready pod -l app=rabbitmq -n flowfish --timeout=300s

# Redis
kubectl wait --for=condition=ready pod -l app=redis -n flowfish --timeout=180s

# ClickHouse
kubectl wait --for=condition=ready pod -l app=clickhouse -n flowfish --timeout=300s

# Neo4j (single statefulset)
kubectl wait --for=condition=ready pod -l app=neo4j -n flowfish --timeout=300s

# Backend
kubectl wait --for=condition=ready pod -l app=backend -n flowfish --timeout=300s

# Frontend
kubectl wait --for=condition=ready pod -l app=frontend -n flowfish --timeout=180s
```

---

## Logs

```bash
# Backend logs
kubectl logs -n flowfish deployment/backend -f

# Frontend logs
kubectl logs -n flowfish deployment/frontend -f

# PostgreSQL logs
kubectl logs -n flowfish statefulset/postgresql -f

# RabbitMQ logs
kubectl logs -n flowfish statefulset/rabbitmq -f

# ClickHouse logs
kubectl logs -n flowfish statefulset/clickhouse -f

# Neo4j logs
kubectl logs -n flowfish statefulset/neo4j -f
```

---

## Port Forwarding (Local Access)

```bash
# Frontend (React)
kubectl port-forward -n flowfish svc/frontend 3000:3000
# http://localhost:3000

# Backend API (FastAPI)
kubectl port-forward -n flowfish svc/backend 8000:8000
# http://localhost:8000/docs

# PostgreSQL
kubectl port-forward -n flowfish svc/postgresql 5432:5432
# postgresql://flowfish:flowfish123@localhost:5432/flowfish

# RabbitMQ Management UI
kubectl port-forward -n flowfish svc/rabbitmq 15672:15672
# http://localhost:15672 (flowfish / flowfish-rabbit-2024)

# Redis
kubectl port-forward -n flowfish svc/redis 6379:6379
# redis://localhost:6379

# ClickHouse
kubectl port-forward -n flowfish svc/clickhouse 8123:8123 9000:9000
# HTTP: http://localhost:8123
# Native: localhost:9000

# Neo4j
kubectl port-forward -n flowfish svc/neo4j 7474:7474 7687:7687
# Access browser: http://localhost:7474
# Bolt connection: bolt://localhost:7687
```

---

## Cleanup (Delete All)

```bash
# Tüm Flowfish kaynaklarını sil
kubectl delete namespace flowfish

# Veya tek tek:
kubectl delete -f deployment/kubernetes-manifests/
```

---

## Production Checklist

**Deployment öncesi kontrol edilmesi gerekenler:**

- [ ] Secrets dosyasındaki şifreleri değiştir (`04-secrets.yaml`)
- [ ] PostgreSQL persistent volume boyutunu ayarla
- [ ] ClickHouse persistent volume boyutunu ayarla
- [ ] Neo4j persistent volume boyutunu ayarla
- [ ] RabbitMQ persistent volume boyutunu ayarla
- [ ] Resource limits/requests ayarla (CPU, Memory)
- [ ] Ingress TLS sertifikası ekle (Let's Encrypt / cert-manager)
- [ ] Ingress domain adını değiştir
- [ ] Backend environment variables kontrol et
- [ ] Frontend environment variables kontrol et
- [ ] Monitoring ekle (Prometheus, Grafana)
- [ ] Backup stratejisi belirle (PostgreSQL, ClickHouse, Neo4j)
- [ ] High Availability (HA) yapılandırması (replicas, PodDisruptionBudget)

---

## Dependencies

```
┌─────────────────────────────────────────────────┐
│         Flowfish Deployment Dependencies        │
└─────────────────────────────────────────────────┘

1. Namespace & RBAC (temel altyapı)
   └─▶ ConfigMaps & Secrets (konfigürasyon)
       └─▶ Databases (veri katmanı)
           ├─▶ PostgreSQL (metadata)
           ├─▶ RabbitMQ (message queue)
           ├─▶ Redis (cache)
           ├─▶ ClickHouse (time-series)
           └─▶ Neo4j (graph)
               └─▶ Backend Services (uygulama katmanı)
                   ├─▶ API Gateway
                   ├─▶ Cluster Manager
                   ├─▶ Analysis Orchestrator
                   ├─▶ Ingestion Service
                   ├─▶ ClickHouse Writer
                   └─▶ Dependency Graph
                       └─▶ Frontend (UI katmanı)
                           └─▶ Ingress (external access)
```

---

## Troubleshooting

### Container Runtime Auto-Detection

Inspektor Gadget DaemonSet, pod başlangıcında bir init container aracılığıyla container runtime socket yolunu otomatik tespit eder. Desteklenen platformlar: K3s, RKE2, standard K8s, MicroK8s. Init container loglarında tespit edilen socket yolunu görebilirsiniz:

```bash
kubectl logs -n $NS -l app=inspektor-gadget -c detect-runtime
```

---

## Microservices Status

| Service | YAML Ready | Implementation | Status |
|---------|-----------|----------------|--------|
| PostgreSQL | ✅ | ✅ | Ready |
| RabbitMQ | ✅ | ✅ | Ready |
| Redis | ✅ | ✅ | Ready |
| ClickHouse | ✅ | ✅ | Ready |
| Neo4j | ✅ | ✅ | Ready |
| API Gateway | ⏳ | ⏳ | In Progress |
| Cluster Manager | ⏳ | 🔴 | Not Started |
| Analysis Orchestrator | ⏳ | 🔴 | Not Started |
| Ingestion Service | ⏳ | 🔴 | Not Started |
| ClickHouse Writer | ⏳ | 🔴 | Not Started |
| Dependency Graph | ⏳ | 🔴 | Not Started |
| Frontend | ✅ | ✅ | Ready |
| Inspektor Gadget | ✅ | ✅ | Ready |
| Ingress | ✅ | ✅ | Ready |

---

**Next Steps:**
1. ✅ RabbitMQ deployment eklendi
2. ⏳ Microservice implementations (Python gRPC services)
3. ⏳ Microservice deployment YAML'ları
4. ⏳ Integration tests

