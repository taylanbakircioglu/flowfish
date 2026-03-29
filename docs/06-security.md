# Flowfish - Güvenlik Tasarımı

## 🔒 Genel Bakış

Flowfish platform güvenliği, Defense in Depth (katmanlı savunma) prensipleriyle tasarlanmıştır.

---

## 🎯 Güvenlik İlkeleri

1. **Least Privilege**: Minimum yetki prensibi
2. **Defense in Depth**: Çok katmanlı güvenlik
3. **Zero Trust**: Her isteğin doğrulanması
4. **Encryption**: Veri şifreleme (at-rest & in-transit)
5. **Audit**: Tüm işlemlerin loglanması
6. **Isolation**: Multi-tenant izolasyon

---

## 🔐 Kimlik Doğrulama (Authentication)

### 1. JWT Token Authentication

**Token Structure**:
```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "user_id": 123,
    "username": "admin",
    "roles": ["Super Admin"],
    "exp": 1704067200,
    "iat": 1704063600
  }
}
```

**Token Lifecycle**:
- **Access Token**: 1 hour (short-lived)
- **Refresh Token**: 7 days (long-lived)
- **Storage**: HttpOnly cookie (XSS protection)
- **Transmission**: Authorization header

**Token Generation**:
```python
import jwt
from datetime import datetime, timedelta

def create_access_token(user_id, username, roles):
    payload = {
        'user_id': user_id,
        'username': username,
        'roles': roles,
        'exp': datetime.utcnow() + timedelta(hours=1),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')
```

**Token Validation**:
- Signature verification
- Expiration check
- Blacklist check (Redis)
- Role/permission check

### 2. OAuth 2.0 / SSO

**Supported Providers**:
- Google Workspace
- Microsoft Azure AD / Entra ID
- Okta
- Keycloak

**OAuth Flow** (Authorization Code):
```
User → Login Button → Flowfish Frontend
  → Redirect to OAuth Provider
  → User authenticates
  → Provider redirects with auth code
  → Flowfish exchanges code for token
  → Create/update user in database
  → Issue JWT token
  → Redirect to dashboard
```

**Security Controls**:
- State parameter (CSRF protection)
- PKCE (Proof Key for Code Exchange)
- Token validation
- User account linking

### 3. Kubernetes Service Account

**In-Cluster Authentication**:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: flowfish-backend
  namespace: flowfish
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flowfish-reader
rules:
- apiGroups: [""]
  resources: ["pods", "services", "namespaces"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flowfish-reader-binding
subjects:
- kind: ServiceAccount
  name: flowfish-backend
  namespace: flowfish
roleRef:
  kind: ClusterRole
  name: flowfish-reader
  apiGroup: rbac.authorization.k8s.io
```

---

## 👥 Yetkilendirme (Authorization)

### RBAC (Role-Based Access Control)

**Role Hierarchy**:
```
Super Admin (ALL permissions)
  └─ Platform Admin (Management + Analysis)
      └─ Security Analyst (Security + Read)
          └─ Developer (Read-only)
```

**Permission Model**:
```
Permission = Resource + Action
Example: clusters.view, analyses.execute, users.delete
```

**Permission Matrix**:

| Resource | Super Admin | Platform Admin | Security Analyst | Developer |
|----------|-------------|----------------|------------------|-----------|
| clusters.* | ✅ | ✅ | ❌ | ❌ |
| analyses.* | ✅ | ✅ | ❌ | ❌ |
| dependencies.view | ✅ | ✅ | ✅ | ✅ |
| anomalies.* | ✅ | ✅ | ✅ | ❌ |
| users.* | ✅ | ❌ | ❌ | ❌ |
| audit.view | ✅ | ✅ | ✅ | ❌ |

**Middleware Implementation**:
```python
async def require_permission(permission: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = request.state.user
            if not has_permission(user, permission):
                raise HTTPException(403, "Insufficient permissions")
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

@app.get("/api/v1/clusters")
@require_permission("clusters.view")
async def get_clusters():
    ...
```

### Multi-Tenant Isolation

**Tenant Separation**:
- **Cluster-level**: Users can only access assigned clusters
- **Namespace-level**: Namespace-based access control
- **Data-level**: SQL WHERE clauses filter by user

**Row-Level Security** (PostgreSQL):
```sql
-- Enable RLS
ALTER TABLE workloads ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see workloads from their clusters
CREATE POLICY workload_isolation ON workloads
    FOR SELECT
    USING (cluster_id IN (
        SELECT cluster_id FROM user_cluster_access
        WHERE user_id = current_user_id()
    ));
```

---

## 🔒 Veri Şifreleme

### 1. At-Rest Encryption

**Database Encryption**:

**PostgreSQL**:
```bash
# Transparent Data Encryption (TDE)
# Using encrypted volumes or PostgreSQL 15+ TDE
pgcrypto extension for column-level encryption
```

**Encryption Example**:
```sql
-- Encrypt sensitive fields
CREATE TABLE oauth_providers (
    id SERIAL PRIMARY KEY,
    client_secret_encrypted TEXT NOT NULL,
    ...
);

-- Encrypt on insert
INSERT INTO oauth_providers (client_secret_encrypted)
VALUES (pgp_sym_encrypt('secret_value', 'encryption_key'));

-- Decrypt on select
SELECT pgp_sym_decrypt(client_secret_encrypted::bytea, 'encryption_key')
FROM oauth_providers;
```

**ClickHouse**:
- Disk encryption via OS (LUKS)
- Column-level encryption (optional)

**Neo4j**:
- Volume encryption via Kubernetes PVC

**Redis**:
- Volume encryption
- No built-in encryption

**Key Management**:
- **Development**: Environment variables
- **Production**: Kubernetes Secrets + External Secrets Operator
- **Enterprise**: HashiCorp Vault, AWS KMS, Azure Key Vault

### 2. In-Transit Encryption

**TLS/SSL Everywhere**:

**Frontend ↔ User**:
```
HTTPS (TLS 1.3)
- Certificate: Let's Encrypt or corporate CA
- Strong ciphers only
- HSTS header enabled
```

**Frontend ↔ Backend**:
```
HTTPS (TLS 1.2+)
- Internal service mesh (optional: mTLS via Istio)
- Certificate rotation
```

**Backend ↔ Databases**:

**PostgreSQL**:
```python
# Connection string with SSL
DATABASE_URL = "postgresql://user:pass@host:5432/db?sslmode=require"
```

**ClickHouse**:
```xml
<clickhouse>
    <https_port>8443</https_port>
    <openSSL>
        <server>
            <certificateFile>/etc/clickhouse-server/server.crt</certificateFile>
            <privateKeyFile>/etc/clickhouse-server/server.key</privateKeyFile>
        </server>
    </openSSL>
</clickhouse>
```

**Neo4j**:
```yaml
# SSL enabled connection
ssl:
  enable: true
  cert_path: /path/to/cert.pem
  key_path: /path/to/key.pem
```

---

## 🛡️ Uygulama Güvenliği

### 1. Input Validation

**Backend Validation** (Pydantic):
```python
from pydantic import BaseModel, validator, constr

class ClusterCreate(BaseModel):
    name: constr(min_length=3, max_length=255)
    api_url: HttpUrl
    
    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Name must be lowercase alphanumeric with hyphens')
        return v
```

**SQL Injection Prevention**:
```python
# ✅ Good: Parameterized query
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# ❌ Bad: String concatenation
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

### 2. XSS Prevention

**React**:
- Default XSS protection (JSX escaping)
- DangerouslySetInnerHTML avoided

**Content Security Policy**:
```http
Content-Security-Policy: 
  default-src 'self';
  script-src 'self' 'unsafe-inline' 'unsafe-eval';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  connect-src 'self' wss:;
  frame-ancestors 'none';
```

### 3. CSRF Protection

**SameSite Cookies**:
```python
response.set_cookie(
    key="refresh_token",
    value=token,
    httponly=True,
    secure=True,
    samesite="strict"
)
```

**CSRF Token**:
```python
# Generate token
csrf_token = secrets.token_urlsafe(32)
session['csrf_token'] = csrf_token

# Validate token
if request.form['csrf_token'] != session['csrf_token']:
    raise HTTPException(403, "CSRF token mismatch")
```

### 4. Rate Limiting

**API Rate Limiting**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/v1/clusters")
@limiter.limit("100/hour")
async def get_clusters():
    ...
```

**Redis-based Rate Limiting**:
```python
def check_rate_limit(user_id, limit=100, window=3600):
    key = f"rate_limit:{user_id}"
    current = redis.incr(key)
    if current == 1:
        redis.expire(key, window)
    if current > limit:
        raise HTTPException(429, "Rate limit exceeded")
```

---

## 🔐 Kubernetes Security

### 1. Network Policies

**Default Deny**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: flowfish
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

**Allow Backend → Database**:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-to-postgres
  namespace: flowfish
spec:
  podSelector:
    matchLabels:
      app: postgresql
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: backend
    ports:
    - protocol: TCP
      port: 5432
```

### 2. Pod Security

**Pod Security Standards**:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: backend
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 2000
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: backend
    image: flowfish/backend:latest
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
        - ALL
    resources:
      limits:
        memory: "4Gi"
        cpu: "2000m"
      requests:
        memory: "1Gi"
        cpu: "500m"
```

### 3. Secrets Management

**Kubernetes Secrets**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: database-credentials
  namespace: flowfish
type: Opaque
stringData:
  username: flowfish_user
  password: <strong-password>
```

**External Secrets Operator**:
```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
  namespace: flowfish
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "flowfish"
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: database-secret
  namespace: flowfish
spec:
  refreshInterval: 15m
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: database-credentials
  data:
  - secretKey: password
    remoteRef:
      key: database/credentials
      property: password
```

---

## 📝 Audit Logging

### Comprehensive Logging

**Log Everything**:
- User login/logout
- API requests (method, path, user, IP)
- Database changes (CREATE, UPDATE, DELETE)
- Permission changes
- Configuration changes
- Anomaly detections
- Import/export operations

**Log Format** (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "user_id": 123,
  "username": "admin",
  "action": "create_cluster",
  "resource_type": "cluster",
  "resource_id": "cluster-prod-01",
  "ip_address": "10.0.1.50",
  "user_agent": "Mozilla/5.0...",
  "request_id": "abc-def-123",
  "success": true,
  "details": {...}
}
```

**Log Storage**:
- **Hot**: Last 30 days in PostgreSQL
- **Cold**: 30-365 days in object storage
- **Archive**: 1-7 years in compliance storage

**Log Analysis**:
- Elasticsearch/Splunk for search
- Grafana dashboards for visualization
- Alerting on suspicious patterns

---

## 🚨 Security Monitoring

### Threat Detection

**Suspicious Activities**:
- Multiple failed login attempts
- Unusual API access patterns
- Privilege escalation attempts
- Anomalous database queries
- Unauthorized access attempts

**Alerting Rules**:
```yaml
# Example: Alert on 5 failed logins in 5 minutes
- alert: MultipleFailedLogins
  expr: |
    sum(rate(failed_login_attempts[5m])) by (user) > 5
  annotations:
    summary: "Multiple failed login attempts detected"
    description: "User {{ $labels.user }} has {{ $value }} failed logins"
```

### Security Scanning

**Container Image Scanning**:
```bash
# Trivy scan before deployment
trivy image flowfish/backend:latest

# Fail build if HIGH/CRITICAL vulnerabilities
```

**Dependency Scanning**:
```bash
# Python
safety check

# Node.js
npm audit

# Automated with Dependabot/Renovate
```

**SAST (Static Analysis)**:
- **Python**: Bandit, pylint
- **JavaScript**: ESLint security rules
- **Secrets**: GitLeaks, TruffleHog

---

## 🔒 Compliance

### GDPR Compliance

- **Data Minimization**: Only collect necessary data
- **Right to Access**: API for data export
- **Right to Deletion**: Soft delete + purge mechanism
- **Data Portability**: Export in standard formats
- **Consent**: Explicit opt-in for data processing

### SOC 2 Compliance

- **Access Control**: RBAC enforced
- **Audit Logging**: All actions logged
- **Encryption**: At-rest and in-transit
- **Incident Response**: Documented procedures
- **Vulnerability Management**: Regular scans

---

## 🛠️ Security Best Practices

### Development

1. ✅ Code review mandatory
2. ✅ Security training for developers
3. ✅ Secure coding guidelines
4. ✅ Dependency updates (automated)
5. ✅ Secret scanning in Git

### Deployment

1. ✅ Least privilege containers
2. ✅ Network segmentation
3. ✅ Secrets in vault, not code
4. ✅ TLS everywhere
5. ✅ Regular security audits

### Operations

1. ✅ Patch management
2. ✅ Incident response plan
3. ✅ Backup & disaster recovery
4. ✅ Security monitoring 24/7
5. ✅ Penetration testing (annual)

---

**Versiyon**: 1.0.0  
**Son Güncelleme**: Ocak 2025

