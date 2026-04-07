# Flowfish Classic Release Pipeline - Incremental Deployment

This directory contains task scripts for Azure DevOps Classic (UI-based) Release Pipeline to deploy Flowfish to OpenShift.

## 🆕 Incremental Deployment Özelliği (v2.0)

Release pipeline artık **sadece yeni build edilen servisleri** deploy ediyor:
- Deploy süreleri **%60-70 oranında kısalıyor**
- Gereksiz rollout'lar önleniyor
- Mevcut çalışan servisler etkilenmiyor

### Nasıl Çalışır?

Build pipeline'dan gelen output variables kullanılarak:
- `BACKEND_BUILT=true` → Backend deploy edilir
- `API_GATEWAY_BUILT=true` → API Gateway deploy edilir
- `RELEASE_ALL=true` → Tüm servisler deploy edilir (override)

## Directory Structure

```
classic-release/
├── README.md                      # This file
├── get-credentials/
│   └── task.sh                    # Fetch credentials from Vault
├── prepare-manifests/
│   └── task.sh                    # Prepare K8s manifests with placeholders
├── deploy-infrastructure/
│   └── task.sh                    # Deploy databases and infrastructure
├── deploy-application/
│   └── task.sh                    # Deploy backend and frontend
├── deploy-microservices/
│   └── task.sh                    # Deploy all microservices
└── health-check/
    └── task.sh                    # Run health checks
```

---

## Pipeline Setup

### 1. Create New Classic Release Pipeline

1. Azure DevOps → **Pipelines** → **Releases** → **New pipeline**
2. Select **Empty job** template
3. Pipeline name: `Flowfish-CD`

---

### 2. Add Build Artifact

**Artifacts Section:**
1. Click **Add an artifact**
2. Source type: **Build**
3. Project: `Flowfish`
4. Source (build pipeline): `Flowfish-CI`
5. Default version: **Latest**
6. Source alias: `_Flowfish-CI`

**Continuous Deployment Trigger:**
- Enable continuous deployment trigger
- Branch filter: `pilot`

---

### 3. Create Stage: Deploy to Pilot

**Stage Settings:**
- Stage name: `Deploy to Pilot`
- Pre-deployment approvals: Optional (add if needed)
- Post-deployment approvals: Optional

---

### 4. Configure Agent Pool

**Agent Job Settings:**
- Display name: `Deploy Flowfish`
- Agent pool: `BuildServers`
- Allow scripts to access the OAuth token: ✅ **Checked**

---

### 5. Link Variable Groups

**Variables Tab:**
1. Click **Variable groups**
2. Link variable group: `FlowfishVaultENV`
3. Link variable group: `FlowfishCompanyVariable`

---

### 6. Add Pipeline Variables

**Variables** tab → **Pipeline variables**:

| Name | Value | Scope | Secret |
|------|-------|-------|--------|
| `DEPLOYMENT_ENV` | `pilot` | Release | No |
| `BUILD_SOURCEVERSION` | `$(Build.SourceVersion)` | Release | No |
| `release-all` | `false` | Release | No |
| `GADGET_VERSION` | `v0.50.1` | Release | No |

> **GADGET_VERSION:** Inspektor Gadget image versiyonu. Build pipeline'daki değerle aynı olmalıdır.
> **v0.50.1 includes ring buffer fix + socket cleanup improvements.**

### 6.1 Build Pipeline Output Variables (Incremental Deploy İçin)

Build pipeline'dan gelen output variables'ları release'e bağlamak için:

**Variables** tab → **Pipeline variables**:

| Name | Value | Açıklama |
|------|-------|----------|
| `BACKEND_BUILT` | `$(Release.Artifacts._Flowfish-CI.BACKEND_BUILT)` | Backend derlendi mi |
| `BACKEND_TAG` | `$(Release.Artifacts._Flowfish-CI.BACKEND_TAG)` | Backend image tag |
| `FRONTEND_BUILT` | `$(Release.Artifacts._Flowfish-CI.FRONTEND_BUILT)` | Frontend derlendi mi |
| `FRONTEND_TAG` | `$(Release.Artifacts._Flowfish-CI.FRONTEND_TAG)` | Frontend image tag |
| `API_GATEWAY_BUILT` | `$(Release.Artifacts._Flowfish-CI.API_GATEWAY_BUILT)` | |
| `API_GATEWAY_TAG` | `$(Release.Artifacts._Flowfish-CI.API_GATEWAY_TAG)` | |
| `CLUSTER_MANAGER_BUILT` | `$(Release.Artifacts._Flowfish-CI.CLUSTER_MANAGER_BUILT)` | |
| `CLUSTER_MANAGER_TAG` | `$(Release.Artifacts._Flowfish-CI.CLUSTER_MANAGER_TAG)` | |
| `ANALYSIS_ORCHESTRATOR_BUILT` | `$(Release.Artifacts._Flowfish-CI.ANALYSIS_ORCHESTRATOR_BUILT)` | |
| `ANALYSIS_ORCHESTRATOR_TAG` | `$(Release.Artifacts._Flowfish-CI.ANALYSIS_ORCHESTRATOR_TAG)` | |
| `GRAPH_WRITER_BUILT` | `$(Release.Artifacts._Flowfish-CI.GRAPH_WRITER_BUILT)` | |
| `GRAPH_WRITER_TAG` | `$(Release.Artifacts._Flowfish-CI.GRAPH_WRITER_TAG)` | |
| `GRAPH_QUERY_BUILT` | `$(Release.Artifacts._Flowfish-CI.GRAPH_QUERY_BUILT)` | |
| `GRAPH_QUERY_TAG` | `$(Release.Artifacts._Flowfish-CI.GRAPH_QUERY_TAG)` | |
| `TIMESERIES_WRITER_BUILT` | `$(Release.Artifacts._Flowfish-CI.TIMESERIES_WRITER_BUILT)` | |
| `TIMESERIES_WRITER_TAG` | `$(Release.Artifacts._Flowfish-CI.TIMESERIES_WRITER_TAG)` | |
| `INGESTION_SERVICE_BUILT` | `$(Release.Artifacts._Flowfish-CI.INGESTION_SERVICE_BUILT)` | |
| `INGESTION_SERVICE_TAG` | `$(Release.Artifacts._Flowfish-CI.INGESTION_SERVICE_TAG)` | |

> **Not:** Artifact alias `_Flowfish-CI` varsayılmıştır. Farklı ise güncelleyin.

---

### 7. Add Tasks to Stage

Add the following tasks in order:

---

#### **TASK 1: Get OpenShift Credentials from Vault**

**Task Configuration:**
- Display name: `Get OpenShift Credentials`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/get-credentials/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Advanced → Fail on Standard Error: ✅ **Checked**
- Advanced → Environment Variables:
  ```
  VAULT_GATEWAY_URL=$(VAULT_GATEWAY_URL)
  VAULT_TOKEN=$(VAULT_TOKEN)
  OPENSHIFT_USER=$(OPENSHIFT_USER)
  ```

**Purpose:**
- Fetches OpenShift user password from Vault Gateway (`/api/TFSUsers` endpoint)
- Sets `OPENSHIFT_USER` and `OPENSHIFT_PASSWORD` for deployment tasks
- Enables `oc login` authentication for subsequent tasks

**Output Variables:**
- `OPENSHIFT_USER` (passed through from variable group)
- `OPENSHIFT_PASSWORD` (fetched from Vault)

---

#### **TASK 2: Prepare Kubernetes Manifests**

**Task Configuration:**
- Display name: `Prepare Kubernetes Manifests`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/prepare-manifests/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Advanced → Environment Variables:
  ```
  BUILD_ARTIFACTSTAGINGDIRECTORY=$(Build.ArtifactStagingDirectory)
  BUILD_SOURCESDIRECTORY=$(Build.SourcesDirectory)
  BUILD_SOURCEVERSION=$(Build.SourceVersion)
  DEPLOYMENT_ENV=$(DEPLOYMENT_ENV)
  HARBOR_REGISTRY=$(HARBOR_REGISTRY)
  OPENSHIFT_NAMESPACE=$(OPENSHIFT_NAMESPACE)
  STORAGE_CLASS=$(STORAGE_CLASS)
  DOMAIN_NAME=$(DOMAIN_NAME)
  FRONTEND_URL=$(FRONTEND_URL)
  API_BASE_URL=$(API_BASE_URL)
  TLS_SECRET_NAME=$(TLS_SECRET_NAME)
  GADGET_VERSION=$(GADGET_VERSION)
  POSTGRES_HOST=$(POSTGRES_HOST)
  REDIS_HOST=$(REDIS_HOST)
  CLICKHOUSE_HOST=$(CLICKHOUSE_HOST)
  RABBITMQ_HOST=$(RABBITMQ_HOST)
  NEO4J_HOST=$(NEO4J_HOST)
  NEO4J_BOLT_PORT=$(NEO4J_BOLT_PORT)
  NEO4J_HTTP_PORT=$(NEO4J_HTTP_PORT)
  POSTGRES_USER=$(POSTGRES_USER)
  POSTGRES_PASSWORD=$(POSTGRES_PASSWORD)
  REDIS_PASSWORD=$(REDIS_PASSWORD)
  CLICKHOUSE_USER=$(CLICKHOUSE_USER)
  CLICKHOUSE_PASSWORD=$(CLICKHOUSE_PASSWORD)
  RABBITMQ_USER=$(RABBITMQ_USER)
  RABBITMQ_PASSWORD=$(RABBITMQ_PASSWORD)
  RABBITMQ_ERLANG_COOKIE=$(RABBITMQ_ERLANG_COOKIE)
  NEBULA_USER=$(NEBULA_USER)
  NEBULA_PASSWORD=$(NEBULA_PASSWORD)
  NEBULA_CLUSTER_SECRET=$(NEBULA_CLUSTER_SECRET)
  JWT_SECRET_KEY=$(JWT_SECRET_KEY)
  WEBHOOK_SECRET=$(WEBHOOK_SECRET)
  DATA_ENCRYPTION_KEY=$(DATA_ENCRYPTION_KEY)
  ```

**Purpose:**
- Copies Kubernetes manifests to staging directory
- Replaces all placeholders with actual values (images, hosts, secrets)
- Prepares secrets with credentials from variable group
- Prepares manifests for deployment

---

#### **TASK 3: Deploy Infrastructure**

**Task Configuration:**
- Display name: `Deploy Infrastructure`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/deploy-infrastructure/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Timeout: **30 minutes**
- Advanced → Environment Variables:
  ```
  BUILD_ARTIFACTSTAGINGDIRECTORY=$(Build.ArtifactStagingDirectory)
  OPENSHIFT_API_URL=$(OPENSHIFT_API_URL)
  OPENSHIFT_USER=$(OPENSHIFT_USER)
  OPENSHIFT_PASSWORD=$(OPENSHIFT_PASSWORD)
  OPENSHIFT_NAMESPACE=$(OPENSHIFT_NAMESPACE)
  ```

**Purpose:**
- Logs into OpenShift cluster using credentials from Task 1
- Applies namespace, configmaps, and secrets manifests
- Deploys PostgreSQL, Redis, ClickHouse, RabbitMQ, Neo4j
- Runs database migrations

---

#### **TASK 4: Deploy Application (Incremental)**

**Task Configuration:**
- Display name: `Deploy Application`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/deploy-application/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Timeout: **20 minutes**
- Advanced → Environment Variables:
  ```
  RELEASE_ALL=$(release-all)
  BACKEND_BUILT=$(BACKEND_BUILT)
  BACKEND_TAG=$(BACKEND_TAG)
  FRONTEND_BUILT=$(FRONTEND_BUILT)
  FRONTEND_TAG=$(FRONTEND_TAG)
  ```

**Purpose:**
- Deploys **only** Backend/Frontend that were built in the CI pipeline
- If `RELEASE_ALL=true`, deploys both
- Ingress/Routes her zaman uygulanır (idempotent)

---

#### **TASK 5: Deploy Microservices (Incremental)**

**Task Configuration:**
- Display name: `Deploy Microservices`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/deploy-microservices/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Timeout: **20 minutes**
- Advanced → Environment Variables:
  ```
  RELEASE_ALL=$(release-all)
  API_GATEWAY_BUILT=$(API_GATEWAY_BUILT)
  API_GATEWAY_TAG=$(API_GATEWAY_TAG)
  CLUSTER_MANAGER_BUILT=$(CLUSTER_MANAGER_BUILT)
  CLUSTER_MANAGER_TAG=$(CLUSTER_MANAGER_TAG)
  ANALYSIS_ORCHESTRATOR_BUILT=$(ANALYSIS_ORCHESTRATOR_BUILT)
  ANALYSIS_ORCHESTRATOR_TAG=$(ANALYSIS_ORCHESTRATOR_TAG)
  GRAPH_WRITER_BUILT=$(GRAPH_WRITER_BUILT)
  GRAPH_WRITER_TAG=$(GRAPH_WRITER_TAG)
  GRAPH_QUERY_BUILT=$(GRAPH_QUERY_BUILT)
  GRAPH_QUERY_TAG=$(GRAPH_QUERY_TAG)
  TIMESERIES_WRITER_BUILT=$(TIMESERIES_WRITER_BUILT)
  TIMESERIES_WRITER_TAG=$(TIMESERIES_WRITER_TAG)
  INGESTION_SERVICE_BUILT=$(INGESTION_SERVICE_BUILT)
  INGESTION_SERVICE_TAG=$(INGESTION_SERVICE_TAG)
  ```

**Purpose:**
- Deploys **only** microservices that were built in the CI pipeline
- If `RELEASE_ALL=true`, deploys all 7 microservices:
  - API Gateway
  - Cluster Manager
  - Ingestion Service
  - Timeseries Writer
  - Graph Writer
  - Graph Query
  - Analysis Orchestrator

**Incremental Deployment Logic:**
```
┌─────────────────────────────────────────────────────────────┐
│  RELEASE_ALL=true?  ──────────────────→  Deploy all         │
│         ↓ (hayır)                                            │
│                                                              │
│  Her servis için:                                            │
│  • API_GATEWAY_BUILT=true?  → Deploy API Gateway             │
│  • CLUSTER_MANAGER_BUILT=true? → Deploy Cluster Manager      │
│  • ... (diğer servisler)                                     │
│                                                              │
│  BUILT=false olan servisler ATLANIR                          │
└─────────────────────────────────────────────────────────────┘
```

---

#### **TASK 6: Health Check**

**Task Configuration:**
- Display name: `Health Check`
- Type: **Bash**
- Script Path: `$(System.DefaultWorkingDirectory)/_Flowfish-CI/drop/pipelines/classic-release/health-check/task.sh`
- Working Directory: `$(System.DefaultWorkingDirectory)`
- Control Options:
  - Run this task: **Even if a previous task has failed**

**Purpose:**
- Checks all pod statuses
- Tests API endpoints
- Displays deployment URLs
- Shows recent errors/warnings

---

## Required Variables

### FlowfishVaultENV Group

| Variable | Description | Type |
|----------|-------------|------|
| `VAULT_GATEWAY_URL` | Gateway API URL for credentials | String |
| `VAULT_TOKEN` | Gateway API authentication token | Secret |

**Example:**
```
VAULT_GATEWAY_URL=https://your-gateway-api.company.com
VAULT_TOKEN=********
```

**Purpose:**
- Authenticate to Gateway API
- Fetch database credentials (PostgreSQL, Redis, ClickHouse, RabbitMQ, Neo4j)
- Fetch OpenShift credentials

---

### FlowfishCompanyVariable Group

| Variable | Description | Example | Secret |
|----------|-------------|---------|--------|
| `HARBOR_REGISTRY` | Harbor registry URL | `harbor.company.com` | No |
| `OPENSHIFT_API_URL` | OpenShift API server URL | `https://openshift-api.company.com:6443` | No |
| `OPENSHIFT_USER` | OpenShift username | `flowfish-deployer` | No |
| `OPENSHIFT_NAMESPACE` | Deployment namespace | `flowfish` | No |
| `STORAGE_CLASS` | Storage class name | `your-storage-class` | No |
| `DOMAIN_NAME` | Base domain | `company.com` | No |
| `FRONTEND_URL` | Frontend URL | `flowfish.example.com` | No |
| `API_BASE_URL` | API base URL | `flowfish.example.com/api` | No |
| `TLS_SECRET_NAME` | TLS secret name | `wildcard-tls` | No |
| `POSTGRES_HOST` | PostgreSQL host | `postgresql.flowfish.svc` | No |
| `POSTGRES_USER` | PostgreSQL username | `flowfish` | No |
| `POSTGRES_PASSWORD` | PostgreSQL password | `********` | **Yes** |
| `REDIS_HOST` | Redis host | `redis.flowfish.svc` | No |
| `REDIS_PASSWORD` | Redis password | `********` | **Yes** |
| `CLICKHOUSE_HOST` | ClickHouse host | `clickhouse.flowfish.svc` | No |
| `CLICKHOUSE_USER` | ClickHouse username | `flowfish` | No |
| `CLICKHOUSE_PASSWORD` | ClickHouse password | `********` | **Yes** |
| `RABBITMQ_HOST` | RabbitMQ host | `rabbitmq.flowfish.svc` | No |
| `RABBITMQ_USER` | RabbitMQ username | `flowfish` | No |
| `RABBITMQ_PASSWORD` | RabbitMQ password | `********` | **Yes** |
| `RABBITMQ_ERLANG_COOKIE` | RabbitMQ Erlang cookie | `********` | **Yes** |
| `NEO4J_HOST` | Neo4j host | `neo4j.flowfish.svc.cluster.local` | No |
| `NEO4J_BOLT_PORT` | Neo4j Bolt port | `7687` | No |
| `NEO4J_HTTP_PORT` | Neo4j HTTP port | `7474` | No |
| `NEBULA_USER` | Neo4j username | `root` | No |
| `NEBULA_PASSWORD` | Neo4j password | `********` | **Yes** |
| `NEBULA_CLUSTER_SECRET` | Neo4j cluster secret | `********` | **Yes** |
| `JWT_SECRET_KEY` | JWT signing key | `********` | **Yes** |
| `WEBHOOK_SECRET` | Webhook secret | `********` | **Yes** |
| `FLOWFISH_ENCRYPTION_KEY` | Fernet key for encrypting cluster credentials | See notes | **Recommended** |

**Notes:**
- `OPENSHIFT_PASSWORD` is fetched dynamically from Gateway API by Task 1
- All secret values should be marked as "Secret" in Azure DevOps variable group
- Generate strong random passwords for production environments

**⚠️ FLOWFISH_ENCRYPTION_KEY - Critical:**
- This key encrypts cluster credentials (tokens, kubeconfigs, CA certs)
- **MUST remain the same across all releases** - changing it makes existing data unreadable
- First deployment: Key is auto-generated and printed in logs - **save it immediately**
- Subsequent releases: Provide the saved key as pipeline variable
- Generate manually: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- If key is lost: All remote cluster connections must be re-configured

---

## Deployment Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Get OpenShift Credentials from Vault                 │
│    - Authenticate to Vault Gateway                      │
│    - Fetch OpenShift user password                      │
│    - Set OPENSHIFT_USER and OPENSHIFT_PASSWORD          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Prepare Kubernetes Manifests                         │
│    - Copy manifests to staging                          │
│    - Replace placeholders (image tags, hosts, etc.)     │
│    - Prepare for deployment                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Deploy Infrastructure (Tier 1)                       │
│    - PostgreSQL (StatefulSet)                           │
│    - Redis (Deployment)                                 │
│    - RabbitMQ (StatefulSet)                             │
│    - Neo4j (StatefulSet)                          │
│    - ClickHouse (StatefulSet)                           │
│    - Database Migrations (Job)                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Deploy Application (Tier 2)                          │
│    - Backend (Deployment)                               │
│    - Frontend (Deployment)                              │
│    - Ingress/Routes                                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Deploy Microservices (Tier 3)                        │
│    - API Gateway                                        │
│    - Cluster Manager                                    │
│    - Ingestion Service                                  │
│    - Timeseries Writer                                  │
│    - Graph Writer                                       │
│    - Graph Query                                        │
│    - Analysis Orchestrator                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 6. Health Check                                         │
│    - Check pod statuses                                 │
│    - Test API endpoints                                 │
│    - Display deployment URLs                            │
│    - Show recent warnings/errors                        │
└─────────────────────────────────────────────────────────┘
```

---

## OpenShift Prerequisites

### 1. OpenShift User with Deploy Permissions

Ensure you have a user account (e.g., `TFSSERVICE` or similar) with permissions to:
- Create and manage resources in the target namespace
- Create namespaces
- Deploy applications

The user's password will be fetched from Vault Gateway during deployment.

---

### 2. Create TLS Secret (REQUIRED - Manual Step)

**IMPORTANT:** TLS certificate is NOT deployed by pipeline. You must create it manually.

```bash
# Get your TLS_SECRET_NAME from FlowfishCompanyVariable group
# Example: TLS_SECRET_NAME=example.com

# Create TLS secret for ingress
oc create secret tls example.com \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  -n flowfish

# Or use existing wildcard certificate
# The secret name MUST match TLS_SECRET_NAME variable in FlowfishCompanyVariable group
```

**Verify:**
```bash
oc get secret example.com -n flowfish
```

---

### 3. Grant SCC Permissions (If Needed)

For Inspector Gadget or other privileged containers:

```bash
# Grant anyuid SCC
oc adm policy add-scc-to-user anyuid system:serviceaccount:flowfish:default

# Grant privileged SCC (only if required)
oc adm policy add-scc-to-user privileged system:serviceaccount:flowfish:default
```

---

## Vault Gateway API

The pipeline fetches OpenShift user password from Vault Gateway API.

**Endpoint:**
```
GET ${VAULT_GATEWAY_URL}/api/TFSUsers
Authorization: Basic ${VAULT_TOKEN}
```

**Expected Response:**
```json
[
  {
    "tfsservice": "openshift-user-password"
  }
]
```

**Database Credentials:**
Database credentials (PostgreSQL, Redis, ClickHouse, RabbitMQ, Neo4j) should be defined in the `04-secrets.yaml` manifest file, not fetched from Vault.

---

## Manifest Placeholders

The following placeholders are replaced during deployment:

### Image Related
- `{{HARBOR_REGISTRY}}` → Harbor registry URL
- `{{HARBOR_PROJECT}}` → `flowfish` (hardcoded)
- `{{IMAGE_TAG}}` → 7-char commit hash
- `{{GADGET_VERSION}}` → Inspektor Gadget version (e.g., `v0.50.1`)

### Service Hosts
- `{{POSTGRES_HOST}}` → PostgreSQL service host
- `{{REDIS_HOST}}` → Redis service host
- `{{CLICKHOUSE_HOST}}` → ClickHouse service host
- `{{RABBITMQ_HOST}}` → RabbitMQ service host
- `{{NEO4J_HOST}}` → Neo4j service host
- `{{NEO4J_BOLT_PORT}}` → Neo4j Bolt port (7687)
- `{{NEO4J_HTTP_PORT}}` → Neo4j HTTP port (7474)

### URLs and Domains
- `{{DOMAIN_NAME}}` → Base domain
- `{{FRONTEND_URL}}` → Frontend URL
- `{{API_BASE_URL}}` → API base URL
- `{{TLS_SECRET_NAME}}` → TLS secret name

### Infrastructure
- `{{NAMESPACE}}` → OpenShift namespace
- `{{STORAGE_CLASS}}` → Storage class
- `{{DEPLOYMENT_ENV}}` → Environment (pilot/staging/prod)

---

## Testing the Pipeline

### Manual Trigger

1. Pipelines → Releases → Flowfish-CD
2. **Create release**
3. Select artifact version (build number)
4. Stage: `Deploy to Pilot`
5. **Create**

### Monitor Deployment

1. Click on the release
2. Click on stage **Deploy to Pilot**
3. View logs for each task
4. Check for errors or warnings

---

## Troubleshooting

### Vault Authentication Failed

**Error:**
```
ERROR: OpenShift password not found in Vault
```

**Solution:**
1. Check `VAULT_GATEWAY_URL` and `VAULT_TOKEN` variables in FlowfishVaultENV group
2. Verify Vault Gateway is accessible from build agent
3. Test endpoint manually: `curl -H "Authorization: Basic ${VAULT_TOKEN}" ${VAULT_GATEWAY_URL}/api/TFSUsers`
4. Verify response contains `tfsservice` field with password

---

### OpenShift Login Failed

**Error:**
```
error: Login failed (401 Unauthorized)
```

**Solution:**
1. Verify `OPENSHIFT_USER` is correct in FlowfishCompanyVariable group
2. Check if password was successfully fetched from Vault (Task 1 logs)
3. Test login manually: `oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${PASSWORD}`
4. Verify user has permissions on the cluster

---

### Pod Not Starting

**Error:**
```
ImagePullBackOff or CrashLoopBackOff
```

**Solution:**
1. Check if images exist in Harbor:
   ```bash
   oc describe pod <pod-name> -n flowfish
   ```

2. Check image pull secrets:
   ```bash
   oc get secrets -n flowfish
   ```

3. Check pod logs:
   ```bash
   oc logs <pod-name> -n flowfish
   ```

---

### Database Connection Failed

**Error:**
```
FATAL: password authentication failed
```

**Solution:**
1. Check `04-secrets.yaml` manifest for correct database credentials
2. Verify secrets are created in namespace:
   ```bash
   oc get secrets -n flowfish
   ```
3. Verify database pods are running:
   ```bash
   oc get pods -n flowfish -l tier=infrastructure
   ```
4. Check pod logs for database startup errors

---

### Health Check Failed

**Error:**
```
✗ Backend health check: FAILED (HTTP 503)
```

**Solution:**
1. Check backend pod logs:
   ```bash
   oc logs deployment/backend -n flowfish
   ```

2. Check if all dependencies are ready:
   ```bash
   oc get pods -n flowfish
   ```

3. Check service endpoints:
   ```bash
   oc get endpoints -n flowfish
   ```

---

## Best Practices

### 1. Pre-Deployment Approvals

Add pre-deployment approvals for production stages:
- Stage settings → Pre-deployment conditions
- Add approvers
- Set timeout

### 2. Post-Deployment Approvals

Add post-deployment approvals to verify manually:
- Stage settings → Post-deployment conditions
- Add approvers

### 3. Rollback Strategy

If deployment fails:

```bash
# Rollback to previous version
oc rollout undo deployment/backend -n flowfish
oc rollout undo deployment/frontend -n flowfish

# Check rollout history
oc rollout history deployment/backend -n flowfish
```

### 4. Blue-Green Deployment

For zero-downtime deployments:
1. Deploy new version with different label
2. Test new version
3. Switch service selector to new version
4. Remove old version

### 5. Monitoring

After deployment:
- Monitor pod metrics in OpenShift console
- Check application logs
- Monitor resource usage
- Set up alerts for critical services

---

## Integration with CI Pipeline

The release pipeline automatically triggers when:
- Flowfish-CI build succeeds
- Branch is `pilot`
- Continuous deployment trigger is enabled

**Flow:**
```
Code Push → CI Build → Build Artifacts → CD Release → Deploy to OpenShift
```

---

## Environment Promotion

To promote to other environments (staging, production):

1. Clone `Deploy to Pilot` stage
2. Rename to `Deploy to Staging` or `Deploy to Production`
3. Update variables:
   - `DEPLOYMENT_ENV`
   - `OPENSHIFT_NAMESPACE`
   - `FRONTEND_URL`
   - etc.
4. Add pre-deployment approvals
5. Configure deployment order

---

## Maintenance

### Updating Scripts

1. Modify scripts in `pipelines/classic-release/`
2. Commit and push to `pilot` branch
3. CI pipeline builds and packages new scripts
4. Next release will use updated scripts

### Adding New Microservices

1. Create deployment manifest in `deployment/kubernetes-manifests/`
2. Add to `MICROSERVICES` array in `deploy-microservices/task.sh`
3. Commit and push

---

## Support

For issues or questions:
1. Check task logs in Azure DevOps
2. Check pod logs in OpenShift
3. Review manifest files in staging directory
4. Verify all variables are set correctly

---

## Security Notes

- Never hardcode credentials in scripts or manifests
- OpenShift user password is fetched from Vault Gateway at runtime
- Database credentials should be stored in Kubernetes secrets (04-secrets.yaml)
- Use OpenShift users with minimal required permissions
- Rotate passwords regularly
- Keep TLS certificates up to date
- Review and audit deployment logs
- Vault Gateway token should be marked as secret in variable group

---

## Future Improvements

- [ ] Add smoke tests after deployment
- [ ] Implement blue-green deployment
- [ ] Add rollback automation
- [ ] Integrate with monitoring/alerting
- [ ] Add performance testing stage
- [ ] Implement canary deployment
- [ ] Add database backup before migration
- [ ] Add security scanning stage

