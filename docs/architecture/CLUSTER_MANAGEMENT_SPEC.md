# Cluster Management - Technical Specification

## 🎯 Overview

Flowfish's **cluster management** module manages Kubernetes/OpenShift clusters in multi-cluster environments and **enforces the Inspector Gadget requirement**.

---

## 📊 Database Schema

### Clusters Table

```sql
CREATE TABLE clusters (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    
    -- Classification
    environment VARCHAR(50) NOT NULL, -- production, staging, development, testing
    provider VARCHAR(50) NOT NULL,    -- kubernetes, openshift, eks, aks, gke, on-premise
    region VARCHAR(100),
    tags JSONB DEFAULT '{}',
    
    -- Connection
    connection_type VARCHAR(50) NOT NULL, -- in-cluster, kubeconfig, service-account
    api_server_url VARCHAR(500) NOT NULL,
    kubeconfig_encrypted TEXT,    -- Encrypted with Fernet/AES
    ca_cert_encrypted TEXT,
    token_encrypted TEXT,
    skip_tls_verify BOOLEAN DEFAULT FALSE,
    
    -- Inspector Gadget (REQUIRED)
    gadget_namespace VARCHAR(255) NOT NULL,  -- REQUIRED from UI
    gadget_endpoint VARCHAR(500),  -- Deprecated - auto-constructed from namespace
    gadget_auto_detect BOOLEAN DEFAULT TRUE,
    gadget_version VARCHAR(50),
    gadget_capabilities JSONB DEFAULT '[]',
    gadget_health_status VARCHAR(50) DEFAULT 'unknown', -- healthy, degraded, unavailable, unknown
    gadget_last_check TIMESTAMP,
    
    -- Validation & Status
    status VARCHAR(50) DEFAULT 'inactive', -- active, inactive, error, validating
    validation_status JSONB,
    last_sync TIMESTAMP,
    error_message TEXT,
    
    -- Statistics (cached for performance)
    total_namespaces INTEGER DEFAULT 0,
    total_pods INTEGER DEFAULT 0,
    total_nodes INTEGER DEFAULT 0,
    k8s_version VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),
    updated_by INTEGER REFERENCES users(id),
    
    -- Indexes
    CONSTRAINT chk_environment CHECK (environment IN ('production', 'staging', 'development', 'testing')),
    CONSTRAINT chk_connection_type CHECK (connection_type IN ('in-cluster', 'kubeconfig', 'service-account')),
    CONSTRAINT chk_gadget_health CHECK (gadget_health_status IN ('healthy', 'degraded', 'unavailable', 'unknown')),
    CONSTRAINT chk_status CHECK (status IN ('active', 'inactive', 'error', 'validating'))
);

CREATE INDEX idx_clusters_environment ON clusters(environment);
CREATE INDEX idx_clusters_status ON clusters(status);
CREATE INDEX idx_clusters_provider ON clusters(provider);
CREATE INDEX idx_clusters_gadget_health ON clusters(gadget_health_status);
CREATE INDEX idx_clusters_created_at ON clusters(created_at DESC);
```

### Example Data

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Production EKS US-East",
  "description": "Main production cluster in AWS US-East-1",
  "environment": "production",
  "provider": "eks",
  "region": "us-east-1",
  "tags": {
    "team": "platform",
    "cost-center": "engineering",
    "criticality": "high"
  },
  "connection_type": "kubeconfig",
  "api_server_url": "https://api-k8s.example.com:6443",
  "gadget_namespace": "kube-system",  // REQUIRED from UI
  "gadget_endpoint": "inspektor-gadget.kube-system:16060",  // Auto-constructed (deprecated)
  "gadget_auto_detect": true,
  "gadget_version": "v0.50.1",
  "gadget_capabilities": ["network", "dns", "tcp", "process"],
  "gadget_health_status": "healthy",
  "gadget_last_check": "2024-01-20T10:30:00Z",
  "status": "active",
  "validation_status": {
    "overall_status": "success",
    "checks": [
      {
        "name": "api_reachability",
        "status": "passed",
        "message": "Kubernetes API is reachable"
      },
      {
        "name": "inspector_gadget",
        "status": "passed",
        "message": "Inspector Gadget found and healthy",
        "details": {
          "version": "v0.19.0",
          "capabilities": ["network", "dns", "tcp"]
        }
      }
    ],
    "warnings": ["Process gadget not available"],
    "errors": []
  },
  "last_sync": "2024-01-20T10:32:00Z",
  "total_namespaces": 42,
  "total_pods": 387,
  "total_nodes": 12,
  "k8s_version": "v1.28.3",
  "created_at": "2024-01-15T09:00:00Z",
  "updated_at": "2024-01-20T10:32:00Z"
}
```

---

## 🔧 Backend Services

### 1. cluster-manager Service Updates

**File: `services/cluster-manager/app/cluster_validator.py`** (NEW)

```python
"""
Cluster Validation Logic
Validates cluster connection and Inspector Gadget availability
"""

import logging
import httpx
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Dict, List, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ClusterValidator:
    """
    Validates Kubernetes cluster and Inspector Gadget
    """
    
    async def validate_cluster(
        self,
        api_server_url: str,
        kubeconfig: str = None,
        token: str = None,
        ca_cert: str = None,
        skip_tls_verify: bool = False
    ) -> Dict[str, Any]:
        """
        Run full cluster validation
        
        Returns:
            {
                "overall_status": "success" | "warning" | "error",
                "checks": [...],
                "warnings": [...],
                "errors": [],
                "cluster_info": {...}
            }
        """
        results = {
            "overall_status": "success",
            "checks": [],
            "warnings": [],
            "errors": [],
            "cluster_info": {}
        }
        
        # 1. Kubernetes API Reachability
        api_check = await self._check_api_reachability(
            api_server_url, kubeconfig, token, ca_cert, skip_tls_verify
        )
        results["checks"].append(api_check)
        
        if api_check["status"] != "passed":
            results["overall_status"] = "error"
            results["errors"].append(api_check["message"])
            return results
        
        # Get K8s client for further checks
        k8s_client = self._get_k8s_client(kubeconfig, token, ca_cert, skip_tls_verify)
        
        # 2. Authentication & Authorization
        auth_check = await self._check_authentication(k8s_client)
        results["checks"].append(auth_check)
        
        if auth_check["status"] != "passed":
            results["overall_status"] = "error"
            results["errors"].append(auth_check["message"])
            return results
        
        # 3. Required Permissions
        perm_check = await self._check_permissions(k8s_client)
        results["checks"].append(perm_check)
        
        if perm_check["status"] == "failed":
            results["overall_status"] = "error"
            results["errors"].append(perm_check["message"])
        elif perm_check["status"] == "warning":
            results["warnings"].append(perm_check["message"])
            if results["overall_status"] == "success":
                results["overall_status"] = "warning"
        
        # 4. Inspector Gadget Detection (CRITICAL!)
        gadget_check = await self._detect_inspector_gadget(k8s_client)
        results["checks"].append(gadget_check)
        
        if gadget_check["status"] == "failed":
            results["overall_status"] = "error"
            results["errors"].append(gadget_check["message"])
            results["errors"].append("Inspector Gadget is REQUIRED for Flowfish")
            return results
        elif gadget_check["status"] == "warning":
            results["warnings"].append(gadget_check["message"])
            if results["overall_status"] == "success":
                results["overall_status"] = "warning"
        
        # Store Gadget info
        if "details" in gadget_check:
            results["gadget_info"] = gadget_check["details"]
        
        # 5. Gather cluster statistics
        stats = await self._gather_cluster_stats(k8s_client)
        results["cluster_info"] = stats
        
        return results
    
    async def _check_api_reachability(
        self, api_server_url, kubeconfig, token, ca_cert, skip_tls_verify
    ) -> Dict:
        """Check if Kubernetes API is reachable"""
        try:
            k8s_client = self._get_k8s_client(kubeconfig, token, ca_cert, skip_tls_verify)
            version_api = client.VersionApi(k8s_client)
            version_info = version_api.get_code()
            
            return {
                "name": "api_reachability",
                "status": "passed",
                "message": f"Kubernetes API is reachable (v{version_info.git_version})",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "version": version_info.git_version,
                    "platform": version_info.platform
                }
            }
        except Exception as e:
            return {
                "name": "api_reachability",
                "status": "failed",
                "message": f"Cannot reach Kubernetes API: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _check_authentication(self, k8s_client) -> Dict:
        """Check if authentication is valid"""
        try:
            # Try to list namespaces as auth test
            v1 = client.CoreV1Api(k8s_client)
            v1.list_namespace(limit=1)
            
            return {
                "name": "authentication",
                "status": "passed",
                "message": "Authentication successful",
                "timestamp": datetime.utcnow().isoformat()
            }
        except ApiException as e:
            if e.status == 401:
                return {
                    "name": "authentication",
                    "status": "failed",
                    "message": "Authentication failed: Invalid credentials",
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "name": "authentication",
                    "status": "failed",
                    "message": f"Authentication error: {e.reason}",
                    "timestamp": datetime.utcnow().isoformat()
                }
    
    async def _detect_inspector_gadget(self, k8s_client) -> Dict:
        """
        Detect Inspector Gadget DaemonSet and endpoint
        
        Strategy:
        1. Search for DaemonSet named "gadget" or "inspektor-gadget" in common namespaces
        2. Look for Service with label "app=inspektor-gadget"
        3. Construct endpoint and test health
        """
        try:
            apps_v1 = client.AppsV1Api(k8s_client)
            core_v1 = client.CoreV1Api(k8s_client)
            
            # Search namespaces
            search_namespaces = ["kube-system", "gadget", "inspektor-gadget", "monitoring"]
            
            gadget_found = False
            gadget_namespace = None
            gadget_daemonset = None
            
            for ns in search_namespaces:
                try:
                    daemonsets = apps_v1.list_namespaced_daemon_set(ns)
                    for ds in daemonsets.items:
                        if "gadget" in ds.metadata.name.lower():
                            gadget_found = True
                            gadget_namespace = ns
                            gadget_daemonset = ds.metadata.name
                            break
                    
                    if gadget_found:
                        break
                except ApiException:
                    # Namespace might not exist
                    continue
            
            if not gadget_found:
                return {
                    "name": "inspector_gadget",
                    "status": "failed",
                    "message": "Inspector Gadget DaemonSet not found in cluster",
                    "timestamp": datetime.utcnow().isoformat(),
                    "help": "Install Inspector Gadget: kubectl gadget deploy"
                }
            
            # Find Service
            try:
                services = core_v1.list_namespaced_service(gadget_namespace)
                gadget_service = None
                
                for svc in services.items:
                    if "gadget" in svc.metadata.name.lower():
                        gadget_service = svc.metadata.name
                        break
                
                if not gadget_service:
                    # Construct default endpoint (gRPC, no http:// prefix)
                    gadget_endpoint = f"{gadget_daemonset}.{gadget_namespace}:16060"
                else:
                    gadget_endpoint = f"{gadget_service}.{gadget_namespace}:16060"
                
            except:
                # Fallback endpoint
                gadget_endpoint = f"inspektor-gadget.{gadget_namespace}:16060"
            
            # Test Gadget health
            gadget_health = await self._test_gadget_health(gadget_endpoint)
            
            if gadget_health["healthy"]:
                return {
                    "name": "inspector_gadget",
                    "status": "passed",
                    "message": f"Inspector Gadget found and healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": {
                        "namespace": gadget_namespace,
                        "daemonset": gadget_daemonset,
                        "endpoint": gadget_endpoint,
                        "version": gadget_health.get("version"),
                        "capabilities": gadget_health.get("capabilities", [])
                    }
                }
            else:
                return {
                    "name": "inspector_gadget",
                    "status": "warning",
                    "message": f"Inspector Gadget found but health check failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": {
                        "namespace": gadget_namespace,
                        "endpoint": gadget_endpoint,
                        "error": gadget_health.get("error")
                    }
                }
        
        except Exception as e:
            logger.error(f"Gadget detection failed: {e}")
            return {
                "name": "inspector_gadget",
                "status": "failed",
                "message": f"Failed to detect Inspector Gadget: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _test_gadget_health(self, endpoint: str) -> Dict:
        """Test Inspector Gadget health endpoint"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint}/health")
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "healthy": True,
                        "version": data.get("version"),
                        "capabilities": data.get("capabilities", [])
                    }
                else:
                    return {
                        "healthy": False,
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }
```

---

## 📡 gRPC API

### Proto Definition Updates

**File: `proto/cluster_manager.proto`**

```protobuf
syntax = "proto3";

package flowfish.cluster_manager;

import "google/protobuf/timestamp.proto";
import "google/protobuf/struct.proto";

service ClusterManager {
    // Cluster CRUD
    rpc CreateCluster(CreateClusterRequest) returns (CreateClusterResponse);
    rpc GetCluster(GetClusterRequest) returns (GetClusterResponse);
    rpc ListClusters(ListClustersRequest) returns (ListClustersResponse);
    rpc UpdateCluster(UpdateClusterRequest) returns (UpdateClusterResponse);
    rpc DeleteCluster(DeleteClusterRequest) returns (DeleteClusterResponse);
    
    // Validation
    rpc ValidateCluster(ValidateClusterRequest) returns (ValidateClusterResponse);
    rpc TestClusterConnection(TestClusterConnectionRequest) returns (TestClusterConnectionResponse);
    
    // Inspector Gadget
    rpc DetectGadget(DetectGadgetRequest) returns (DetectGadgetResponse);
    rpc TestGadgetHealth(TestGadgetHealthRequest) returns (TestGadgetHealthResponse);
    
    // Cluster Operations
    rpc SyncCluster(SyncClusterRequest) returns (SyncClusterResponse);
    rpc GetClusterStats(GetClusterStatsRequest) returns (GetClusterStatsResponse);
}

message CreateClusterRequest {
    string name = 1;
    string description = 2;
    string environment = 3;  // production, staging, development, testing
    string provider = 4;     // kubernetes, openshift, eks, aks, gke
    string region = 5;
    google.protobuf.Struct tags = 6;
    
    // Connection
    string connection_type = 7;  // in-cluster, kubeconfig, service-account
    string api_server_url = 8;
    string kubeconfig = 9;      // Will be encrypted
    string token = 10;          // Will be encrypted
    string ca_cert = 11;        // Will be encrypted
    bool skip_tls_verify = 12;
    
    // Inspector Gadget
    bool gadget_auto_detect = 13;
    string gadget_endpoint = 14;  // Optional if auto-detect=true
}

message ValidateClusterResponse {
    string overall_status = 1;  // success, warning, error
    repeated ValidationCheck checks = 2;
    repeated string warnings = 3;
    repeated string errors = 4;
    ClusterInfo cluster_info = 5;
    GadgetInfo gadget_info = 6;
}

message ValidationCheck {
    string name = 1;
    string status = 2;  // passed, warning, failed
    string message = 3;
    google.protobuf.Timestamp timestamp = 4;
    google.protobuf.Struct details = 5;
}

message GadgetInfo {
    string endpoint = 1;
    string version = 2;
    repeated string capabilities = 3;
    string health_status = 4;
    google.protobuf.Timestamp last_check = 5;
}
```

---

## 🎨 Frontend (React + TypeScript)

### Page Structure

```
frontend/src/pages/Management/Clusters/
├── index.tsx                    # Main cluster list page
├── ClusterList.tsx              # List component
├── ClusterCard.tsx              # Individual cluster card
├── AddClusterWizard/
│   ├── index.tsx                # Wizard container
│   ├── Step1BasicInfo.tsx       # Name, env, provider
│   ├── Step2Connection.tsx      # Kubeconfig, API server
│   ├── Step3Gadget.tsx          # Inspector Gadget config
│   └── Step4Review.tsx          # Review & confirm
├── EditClusterModal.tsx         # Edit modal
├── ClusterDetailsDrawer.tsx     # Details side drawer
└── types.ts                     # TypeScript types
```

---

## 🔄 Implementation Roadmap

### Phase 1: Backend (Week 1)
- [ ] Update PostgreSQL schema (migrations)
- [ ] Implement `ClusterValidator` class
- [ ] Add Inspector Gadget detection logic
- [ ] Update gRPC proto definitions
- [ ] Implement cluster-manager gRPC methods
- [ ] Add encryption for sensitive data (kubeconfig, tokens)

### Phase 2: API Gateway (Week 1)
- [ ] Add REST endpoints for clusters
- [ ] Implement validation endpoint
- [ ] Add test connection endpoint
- [ ] Add Gadget detection endpoint

### Phase 3: Frontend (Week 2)
- [ ] Cluster list page with filters
- [ ] Add Cluster wizard (4 steps)
- [ ] Edit cluster modal
- [ ] Cluster details drawer
- [ ] Test connection UI feedback
- [ ] Gadget status indicators

### Phase 4: Testing & Integration (Week 2)
- [ ] Unit tests for validation logic
- [ ] Integration tests with test clusters
- [ ] E2E tests for wizard flow
- [ ] Inspector Gadget integration tests
- [ ] Documentation updates

---

## ✅ Validation Checklist Summary

| Check | Criticality | Action on Failure |
|-------|-------------|-------------------|
| **API Reachability** | CRITICAL | Block cluster addition |
| **Authentication** | CRITICAL | Block cluster addition |
| **Permissions** | HIGH | Warn but allow |
| **Inspector Gadget Detection** | **CRITICAL** | **Block cluster addition** |
| **Gadget Health** | HIGH | Warn but allow (retry later) |
| **Gadget Capabilities** | MEDIUM | Warn if missing gadgets |
| **K8s Version** | LOW | Warn if <1.24 |

---

**🎯 Key Principle: Inspector Gadget is MANDATORY. Cluster cannot be added without it.**

