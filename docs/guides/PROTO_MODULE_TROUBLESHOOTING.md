# Proto Module Troubleshooting Guide

## Problem: `ModuleNotFoundError: No module named 'proto'`

### Symptom
```
File "/app/grpc_clients/analysis_orchestrator_client.py", line 15, in <module>
    from proto import analysis_orchestrator_pb2
ModuleNotFoundError: No module named 'proto'
```

Backend pod crashes immediately after startup with the above error.

---

## Root Cause

The backend Docker image is missing the generated Python gRPC files (`*_pb2.py`, `*_pb2_grpc.py`). This happens when:

1. Proto files are not copied into the Docker build context
2. gRPC code generation is not performed during the Docker build
3. The generated files are not included in the final image

---

## Solution

### 1. **Ensure Dockerfile Includes Proto Generation**

The `backend/Dockerfile` must include these steps:

```dockerfile
# Copy proto source files
COPY proto/ ./proto_source/

# Generate gRPC Python code
RUN mkdir -p proto && \
    python -m grpc_tools.protoc \
    --proto_path=./proto_source \
    --python_out=./proto \
    --grpc_python_out=./proto \
    ./proto_source/*.proto

# Create __init__.py for proto module
RUN touch proto/__init__.py
```

### 2. **Verify requirements.txt**

Ensure `backend/requirements.txt` includes:

```txt
grpcio==1.60.0
grpcio-tools==1.60.0
```

### 3. **Rebuild Docker Image**

After making changes:

```bash
# Trigger build pipeline (will rebuild all images)
git add backend/Dockerfile backend/requirements.txt
git commit -m "fix: Add proto generation to backend Dockerfile"
git push origin pilot

# Or manually build locally:
docker build -t flowfish-backend:test -f backend/Dockerfile .
```

---

## Verification Steps

### After Deployment

#### 1. Check if Proto Module Exists in Pod

```bash
# List proto files in the pod
oc exec -it deployment/backend -n <namespace> -- ls -la /app/proto/

# Expected output:
# __init__.py
# analysis_orchestrator_pb2.py
# analysis_orchestrator_pb2_grpc.py
# ingestion_service_pb2.py
# ingestion_service_pb2_grpc.py
# common_pb2.py
# events_pb2.py
# ... etc
```

#### 2. Test Import

```bash
# Test if proto module can be imported
oc exec -it deployment/backend -n <namespace> -- python -c "
import proto
from proto import analysis_orchestrator_pb2
print('✅ Proto module imported successfully')
"
```

#### 3. Check Backend Logs

```bash
# Logs should show successful startup
oc logs -f deployment/backend -n <namespace>

# ✅ Expected:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete

# ❌ NOT Expected:
# ModuleNotFoundError: No module named 'proto'
```

---

## Common Issues

### Issue 1: Build Succeeds but Module Still Missing

**Cause**: Docker build cache or wrong image tag deployed

**Solution**:
```bash
# Delete old pods to force pull new image
oc delete pod -l app=backend -n <namespace>

# Or force restart deployment
oc rollout restart deployment/backend -n <namespace>

# Verify new image is used
oc describe pod <backend-pod> -n <namespace> | grep "Image:"
```

### Issue 2: Proto Files Not Found During Build

**Cause**: Build context doesn't include `proto/` directory

**Solution**:
```bash
# Ensure build context is workspace root
# In Azure Pipelines, verify BuildContext is "."
# Check Docker build task configuration
```

### Issue 3: Generated Files Have Import Errors

**Cause**: Incorrect `--proto_path` or missing dependencies

**Solution**:
```bash
# Ensure proto files have correct package declarations
# Check proto/*.proto files for:
syntax = "proto3";
package flowfish.v1;

# Regenerate locally to test:
cd /Users/U05395/Documents/flowfish
python -m grpc_tools.protoc \
  --proto_path=./proto \
  --python_out=./backend/proto \
  --grpc_python_out=./backend/proto \
  ./proto/*.proto
```

---

## Prevention

### Best Practices

1. **Always include proto generation in Dockerfile**
   - Don't rely on pre-generated files in the repo
   - Generate during build for consistency

2. **Version lock gRPC dependencies**
   ```txt
   grpcio==1.60.0
   grpcio-tools==1.60.0
   ```

3. **Test locally before pushing**
   ```bash
   # Build and run locally
   docker build -t test-backend -f backend/Dockerfile .
   docker run --rm test-backend python -c "import proto; print('OK')"
   ```

4. **Add health check endpoint**
   ```python
   # In backend/main.py
   @app.get("/api/v1/health")
   async def health():
       try:
           import proto
           return {"status": "healthy", "proto_module": "loaded"}
       except ImportError as e:
           return {"status": "unhealthy", "error": str(e)}
   ```

---

## Quick Fix Checklist

- [ ] `backend/Dockerfile` has `COPY proto/ ./proto_source/`
- [ ] `backend/Dockerfile` has proto generation step
- [ ] `backend/requirements.txt` includes `grpcio-tools`
- [ ] Build pipeline completed successfully
- [ ] New image deployed to cluster
- [ ] Backend pod is Running (not CrashLoopBackOff)
- [ ] Backend logs show no import errors
- [ ] `/api/v1/health` endpoint returns 200

---

## Related Files

- `backend/Dockerfile` - Build configuration
- `backend/requirements.txt` - Python dependencies
- `proto/*.proto` - Protocol Buffer definitions
- `backend/grpc_clients/*` - gRPC client implementations
- `services/*/app/grpc_server.py` - gRPC server implementations

---

## Build Pipeline Status

Current build includes proto generation:
- ✅ Proto files copied to build context
- ✅ gRPC tools installed via requirements.txt
- ✅ Python code generation during build
- ✅ Generated files included in final image

**Last Updated**: 2025-11-25
**Status**: Fix implemented, awaiting build pipeline completion

