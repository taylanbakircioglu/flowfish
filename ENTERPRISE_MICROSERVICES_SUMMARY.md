# 🏢 Enterprise Mikroservis Mimarisi - Özet

## 🎯 Yapılan Değişiklikler

### ✅ Tamamlanan İşler

#### 1. **Protocol Abstraction Layer** ✅
- ✅ `AbstractGadgetClient` base class (protocol-agnostic)
- ✅ `GRPCGadgetClient` - Direct gRPC (in-cluster, high performance)
- ✅ `HTTPGadgetClient` - HTTP/REST (remote, firewall-friendly)
- ✅ `AgentGadgetClient` - Agent-based (secure remote, NAT-friendly)
- ✅ `GadgetClientFactory` - Factory pattern for client creation

#### 2. **Mikroservis Refactoring** ✅
- ✅ Protocol client'lar `services/ingestion-service/app/protocols/` klasörüne taşındı
- ✅ `TraceManager` oluşturuldu (trace lifecycle management)
- ✅ `Ingestion Service` gRPC server güncellendi
- ✅ Proto files güncellendi (protocol + auth fields eklendi)

#### 3. **Dokümantasyon** ✅
- ✅ `docs/architecture/ENTERPRISE_MULTI_CLUSTER.md` - Detaylı mimari
- ✅ Protocol karşılaştırması ve karar matrisi
- ✅ Security modelleri
- ✅ Use case'ler

---

## 🏗️ Doğru Mimari

### Önceki (Yanlış):
```
Frontend → Backend API → Backend GadgetCollector → Inspektor Gadget
```

### Şimdi (Doğru):
```
Frontend → Backend API (REST)
              ↓ gRPC
       Analysis Orchestrator
              ↓ gRPC
       Ingestion Service → Inspektor Gadget (gRPC/HTTP/Agent)
              ↓ RabbitMQ
       Timeseries Writer → ClickHouse
       Graph Writer → Neo4j
```

---

## 📋 Mikroservis Sorumlulukları

### 1. Backend API (Port 8000)
**Rol:** REST API Gateway (Stateless)
```
✅ REST endpoint'leri serve et
✅ Authentication/Authorization
✅ Request validation
✅ gRPC çağrıları mikroservislere
❌ Inspektor Gadget'a direkt bağlanma
❌ State tutma
❌ eBPF event collection
```

### 2. Analysis Orchestrator (Port 5002)
**Rol:** Analysis Lifecycle Management
```
✅ Analysis başlatma/durdurma koordinasyonu
✅ Ingestion Service'e trace başlat komutu
✅ Analysis durumunu track et
✅ Scheduled analysis yönetimi
```

### 3. Ingestion Service (Port 5000) ⭐ CORE
**Rol:** eBPF Event Collection & Publishing
```
✅ Inspektor Gadget'a gRPC/HTTP/Agent ile bağlan
✅ eBPF event stream'ini dinle
✅ Event'leri parse et
✅ RabbitMQ'ya publish et
✅ Batch processing
✅ Protocol abstraction (gRPC/HTTP/Agent)
```

### 4. Timeseries Writer (Port 5003)
**Rol:** ClickHouse Writer
```
✅ RabbitMQ'dan event'leri consume et
✅ Batch'ler halinde ClickHouse'a yaz
```

### 5. Graph Writer (Port 5004)
**Rol:** Neo4j Graph Builder
```
✅ Communication event'lerini al
✅ Dependency graph oluştur
✅ Neo4j'ye node/edge yaz
```

---

## 🔄 Event Flow (End-to-End)

### Analysis Start:
```
1. User → Frontend → POST /api/v1/analyses/{id}/start

2. Backend API
   ↓ gRPC: AnalysisOrchestrator.StartAnalysis()

3. Analysis Orchestrator
   - Database'e analysis durumu yaz
   ↓ gRPC: IngestionService.StartCollection()

4. Ingestion Service
   - Protocol'e göre client oluştur (Factory)
   - GRPCGadgetClient | HTTPGadgetClient | AgentGadgetClient
   ↓ gRPC/HTTP/Agent: Inspektor Gadget

5. Inspektor Gadget
   - StartTrace()
   - StreamEvents() başlat
   ↓ Event Stream

6. Ingestion Service
   - Event'leri al
   - Parse et
   ↓ RabbitMQ: Publish

7. Timeseries Writer
   - RabbitMQ'dan consume et
   ↓ ClickHouse: Insert

8. Graph Writer
   - Communication event'lerini al
   ↓ Neo4j: Node/Edge oluştur
```

### Analysis Stop:
```
1. User → Frontend → POST /api/v1/analyses/{id}/stop

2. Backend API → gRPC: AnalysisOrchestrator.StopAnalysis()

3. Analysis Orchestrator → gRPC: IngestionService.StopCollection()

4. Ingestion Service
   - StopTrace() çağrısı
   - gRPC/HTTP connection close
   - Stop signal RabbitMQ'ya

5. Writers
   - Son batch'leri yaz
   - Graceful shutdown
```

---

## 🔧 Protocol Selection Guide

### gRPC (Default - In-Cluster)
```yaml
cluster:
  name: "local-k8s"
  protocol: "grpc"
  gadget_endpoint: "inspektor-gadget.flowfish.svc.cluster.local:16060"
  use_tls: false
  auth_method: "token"
```

**Kullanım:**
- ✅ Aynı Kubernetes cluster
- ✅ High performance gerekli
- ✅ Low latency önemli
- ❌ Firewall arkasında değil

### HTTP/REST (Remote Clusters)
```yaml
cluster:
  name: "remote-eks"
  protocol: "http"
  gadget_endpoint: "https://gadget.remote-cluster.company.com"
  use_tls: true
  auth_method: "api_key"
  api_key: "<encrypted-key>"
```

**Kullanım:**
- ✅ Uzak cluster (farklı network/cloud)
- ✅ Firewall/proxy arkasında
- ✅ Standard port 443 kullanım
- ❌ gRPC blocked

### Agent-Based (Production/Secure)
```yaml
cluster:
  name: "prod-openshift"
  protocol: "agent"
  gadget_endpoint: "flowfish-agent.production.svc.cluster.local:16061"
  use_tls: true
  auth_method: "mtls"
  client_cert: "<cert>"
  client_key: "<key>"
  ca_cert: "<ca>"
```

**Kullanım:**
- ✅ Production environment
- ✅ Strict security requirements
- ✅ NAT/firewall arkasında
- ✅ Agent initiates connection (no inbound ports)
- ✅ Full audit trail gerekli

---

## 📦 Dosya Yapısı

### Yeni Dosyalar:
```
services/ingestion-service/app/
├── protocols/                           # NEW
│   ├── __init__.py
│   ├── abstract_gadget_client.py        # Base class
│   ├── grpc_client.py                   # gRPC implementation
│   ├── http_client.py                   # HTTP implementation
│   ├── agent_client.py                  # Agent implementation
│   └── client_factory.py                # Factory pattern
├── trace_manager.py                     # NEW - Trace lifecycle
└── grpc_server.py                       # UPDATED

proto/
├── ingestion_service.proto              # UPDATED - Protocol fields

docs/architecture/
└── ENTERPRISE_MULTI_CLUSTER.md          # NEW - Enterprise guide
```

### Backend (Geçici - Migrate Edilecek):
```
backend/collectors/
├── gadget_grpc_client.py               # DEPRECATED - Use Ingestion Service
├── gadget_collector.py                  # DEPRECATED - Use Ingestion Service
└── protocols/                           # MOVED to services/ingestion-service/
```

---

## 🚀 Deployment

### Senaryo 1: In-Cluster (gRPC)
```bash
# 1. Inspektor Gadget deploy (gRPC enabled)
kubectl apply -f deployment/kubernetes-manifests/10-inspektor-gadget.yaml

# 2. Mikroservisleri deploy et
kubectl apply -f deployment/kubernetes-manifests/10-ingestion-service.yaml
kubectl apply -f deployment/kubernetes-manifests/13-analysis-orchestrator.yaml

# 3. Cluster ekle (Frontend)
Protocol: gRPC
Endpoint: inspektor-gadget.flowfish.svc.cluster.local:16060
Auth: Token/None
```

### Senaryo 2: Remote Cluster (HTTP)
```bash
# 1. Remote cluster'da Inspektor Gadget + HTTP Adapter deploy
kubectl apply -f remote-cluster/inspektor-gadget-http.yaml

# 2. Flowfish'te cluster ekle
Protocol: HTTP
Endpoint: https://gadget.remote-cluster.company.com
Auth: API Key
API Key: <generate-and-use>
```

### Senaryo 3: Agent-Based (Production)
```bash
# 1. Remote cluster'da Flowfish Agent deploy
kubectl apply -f deployment/kubernetes-manifests/20-flowfish-agent.yaml

# 2. mTLS certificates generate
./scripts/generate-agent-certs.sh prod-cluster

# 3. Flowfish'te cluster ekle
Protocol: Agent
Endpoint: flowfish-agent.production.svc.cluster.local:16061
Auth: mTLS
Client Cert: <upload-cert>
Client Key: <upload-key>
CA Cert: <upload-ca>
```

---

## ⚡ Migration Path

### Phase 1: ✅ COMPLETED
- ✅ Protocol abstraction layer created
- ✅ Clients implemented (gRPC, HTTP, Agent)
- ✅ Ingestion Service refactored
- ✅ Proto files updated
- ✅ Documentation created

### Phase 2: 🔄 NEXT (Backend Migration)
- 🔲 Backend API'yi gRPC gateway'e çevir
- 🔲 `backend/collectors/` kod silme
- 🔲 `backend/routers/analyses.py` gRPC call ekle
- 🔲 Frontend'de protocol seçimi ekle

### Phase 3: 🔄 FUTURE (Agent Implementation)
- 🔲 Flowfish Agent service (DaemonSet)
- 🔲 Agent deployment manifests
- 🔲 Certificate management
- 🔲 Agent health monitoring

### Phase 4: 🔄 ENTERPRISE
- 🔲 mTLS certificate rotation
- 🔲 OAuth2/OIDC integration
- 🔲 Multi-tenancy
- 🔲 Geo-replication

---

## 🧪 Test Commands

### Test Ingestion Service gRPC:
```bash
# Port forward
kubectl port-forward svc/ingestion-service 5000:5000 -n flowfish

# Test with grpcurl
grpcurl -plaintext \
  -d '{"task_id": "test-1", "analysis_id": 1, "cluster_id": 1, "gadget_protocol": "grpc", "gadget_endpoint": "inspektor-gadget:16060", "gadget_modules": ["network_traffic"]}' \
  localhost:5000 \
  flowfish.ingestion.DataIngestion/StartCollection
```

### Test Protocol Clients:
```python
# Test gRPC client
from app.protocols import GRPCGadgetClient, TraceConfig

client = GRPCGadgetClient(endpoint="inspektor-gadget:16060")
await client.connect()
trace_id = await client.start_trace(TraceConfig(...))
async for event in client.stream_events(trace_id):
    print(event)

# Test HTTP client
from app.protocols import HTTPGadgetClient

client = HTTPGadgetClient(
    endpoint="https://gadget.remote.com",
    api_key="secret-key"
)
await client.connect()
health = await client.health_check()
print(health)
```

---

## 📊 Benefits

### ✅ Scalability
- Ingestion Service horizontal scale (multiple instances)
- Backend stateless (kolay scale)
- Dedicated workers per protocol

### ✅ Flexibility
- 3 protocol desteği (gRPC, HTTP, Agent)
- Easy protocol switching
- Protocol-agnostic architecture

### ✅ Security
- mTLS support
- API key authentication
- Certificate management
- Audit logging

### ✅ Reliability
- Graceful fallback (gRPC → HTTP)
- Connection retry logic
- Error handling per protocol
- Health monitoring

### ✅ Maintainability
- Separation of concerns
- Clear responsibilities
- Testable components
- Good documentation

---

## 🎯 Next Steps

### Immediate (Bu Session):
1. ✅ Protocol abstraction - DONE
2. ✅ Ingestion Service refactor - DONE
3. 🔲 Backend API migration
4. 🔲 Frontend protocol selection UI
5. 🔲 End-to-end test

### Short Term (Sprint 6):
1. Backend'deki deprecated code'u sil
2. Frontend cluster form'a protocol seçimi ekle
3. Multi-cluster test
4. Load testing

### Long Term (Sprint 7-8):
1. Agent implementation
2. WebSocket protocol
3. Certificate management UI
4. Advanced security features

---

**Status:** 🟢 **Phase 1 Complete - Ready for Phase 2**  
**Date:** 24 Kasım 2025  
**Sprint:** 5-6 (Analysis & Multi-Cluster)  

**Hazırlayan:** Flowfish Team  
**Review:** Enterprise Architecture Team

