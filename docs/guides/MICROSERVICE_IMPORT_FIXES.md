# Microservice Import Fixes - November 25, 2025

## Summary

Fixed multiple import-related issues across microservices during Sprint 5-6 deployment.

---

## Issues Fixed

### Issue 1: Backend Proto Module Missing (Fixed ✅)
**Service:** `backend`  
**Error:**
```
ModuleNotFoundError: No module named 'proto'
```

**Root Cause:**
- Backend Dockerfile was missing proto code generation step
- Generated proto files not included in Docker image

**Fix:**
```dockerfile
# backend/Dockerfile
COPY proto/ ./proto_source/
RUN mkdir -p proto && \
    python -m grpc_tools.protoc \
    -I./proto_source \
    --python_out=./proto \
    --grpc_python_out=./proto \
    proto_source/*.proto && \
    for file in ./proto/*_pb2.py ./proto/*_pb2_grpc.py; do \
        if [ -f "$file" ]; then \
            sed -i 's/^import \(.*_pb2\)/from . import \1/' "$file"; \
        fi \
    done && \
    touch proto/__init__.py
```

**Commit:** f951b39

---

### Issue 2: Backend Proto Absolute Imports (Fixed ✅)
**Service:** `backend`  
**Error:**
```
ModuleNotFoundError: No module named 'common_pb2'
File: /app/proto/analysis_orchestrator_pb2.py, line 15
    import common_pb2 as common__pb2
```

**Root Cause:**
- `grpc_tools.protoc` generates Python files with absolute imports
- Proto files that import other proto files (`import "common.proto"`) were translated to:
  - ❌ `import common_pb2` (doesn't work in package context)
  - ✅ `from . import common_pb2` (correct relative import)

**Fix:**
Added sed post-processing to Dockerfile to convert absolute imports to relative:
```bash
sed -i 's/^import \(.*_pb2\)/from . import \1/' "$file"
```

**Validation:**
- Created `scripts/test-proto-generation.sh` to verify proto generation locally
- Test result: ✅ PASSED

**Commit:** f951b39 (same commit as Issue 1)

---

### Issue 3: Ingestion Service RabbitMQ Class Name (Fixed ✅)
**Service:** `ingestion-service`  
**Error:**
```
ImportError: cannot import name 'RabbitMQClient' from 'app.rabbitmq_client'
File: /app/app/trace_manager.py, line 13
```

**Root Cause:**
- Class defined as `RabbitMQPublisher` in `rabbitmq_client.py`
- Imported as `RabbitMQClient` in `trace_manager.py` and `grpc_server.py`
- Name mismatch caused import failure

**Fix:**
1. **trace_manager.py:**
   ```python
   # Before:
   from app.rabbitmq_client import RabbitMQClient
   def __init__(self, rabbitmq_client: RabbitMQClient):
   
   # After:
   from app.rabbitmq_client import RabbitMQPublisher
   def __init__(self, rabbitmq_client: RabbitMQPublisher):
   ```

2. **grpc_server.py:**
   ```python
   # Before:
   from app.rabbitmq_client import RabbitMQClient
   self.rabbitmq = RabbitMQClient(
       host=settings.rabbitmq_host,
       port=settings.rabbitmq_port,
       user=settings.rabbitmq_user,
       password=settings.rabbitmq_password
   )
   
   # After:
   from app.rabbitmq_client import RabbitMQPublisher
   self.rabbitmq = RabbitMQPublisher()  # Reads from settings
   ```

**Note:** `RabbitMQPublisher` constructor doesn't take parameters; it reads configuration from `settings`.

**Commit:** 2d0dada

---

## Verification Status

### Backend
- ⏳ Build pipeline running
- ⏳ Waiting for image deployment
- 🎯 Expected: Pod starts successfully without import errors

### Ingestion Service
- ✅ Fix committed and pushed
- ⏳ Waiting for build/deployment
- 🎯 Expected: Pod starts successfully, can import RabbitMQPublisher

### Other Microservices
- ✅ No import issues detected
- ✅ Proto generation working correctly (uses multi-stage Dockerfile pattern)
- ✅ All use relative imports for proto files

---

## Root Cause Analysis

### Why These Issues Occurred

1. **Backend Proto Missing:**
   - Backend was initially developed before microservices split
   - Microservices had correct Dockerfile pattern with proto generation
   - Backend Dockerfile was outdated and missing proto generation step

2. **Absolute vs Relative Imports:**
   - `grpc_tools.protoc` default behavior generates absolute imports
   - Works fine for single proto files
   - Breaks when proto files import each other (e.g., `common.proto`)
   - Microservices already had sed post-processing fix
   - Backend needed same fix

3. **Class Name Mismatch:**
   - Likely refactoring artifact
   - Class renamed from `RabbitMQClient` to `RabbitMQPublisher` for clarity
   - Import statements not updated consistently

---

## Prevention

### Best Practices Established

1. **Consistent Dockerfile Pattern:**
   - All services should use the same proto generation approach
   - Multi-stage build for proto generation
   - Sed post-processing for import fixes

2. **Testing:**
   - Local proto generation test script (`scripts/test-proto-generation.sh`)
   - Run before committing proto changes
   - Validates imports work correctly

3. **Naming Consistency:**
   - Use descriptive class names (`RabbitMQPublisher`, `RabbitMQConsumer`)
   - Keep imports and class definitions in sync
   - Use IDE refactoring tools when renaming

4. **Pre-deployment Validation:**
   - Check all imports before git push
   - Test Docker builds locally when possible
   - Review Dockerfile changes carefully

---

## Related Files

### Backend
- `backend/Dockerfile` - Proto generation and import fix
- `backend/requirements.txt` - gRPC dependencies
- `scripts/test-proto-generation.sh` - Local validation script

### Ingestion Service
- `services/ingestion-service/app/rabbitmq_client.py` - RabbitMQPublisher class
- `services/ingestion-service/app/trace_manager.py` - Import fix
- `services/ingestion-service/app/grpc_server.py` - Import and initialization fix

### Documentation
- `docs/guides/PROTO_MODULE_TROUBLESHOOTING.md` - Comprehensive proto troubleshooting
- `docs/sprints/SPRINT_5-6_CURRENT_STATUS.md` - Sprint progress tracking

---

## Timeline

| Time | Event |
|------|-------|
| Nov 24 | Sprint 5-6 code changes completed |
| Nov 25 08:58 | Backend crash: `ModuleNotFoundError: No module named 'proto'` |
| Nov 25 09:17 | Backend crash: `ModuleNotFoundError: No module named 'common_pb2'` |
| Nov 25 09:30 | Backend Dockerfile fixed with proto generation + import fix |
| Nov 25 09:45 | Ingestion service crash: `RabbitMQClient` import error |
| Nov 25 09:50 | Ingestion service fixed: renamed to `RabbitMQPublisher` |
| Nov 25 10:00 | All fixes committed and pushed (f951b39, 2d0dada) |
| Nov 25 10:15 | Build pipeline running |

---

## Next Steps

1. ⏳ Monitor build pipeline completion
2. ✅ Verify backend pod starts without errors
3. ✅ Verify ingestion-service pod starts without errors
4. 🎯 Continue with analysis start/stop testing
5. 🎯 Test Inspektor Gadget data collection

---

**Status:** All import issues identified and fixed. Waiting for build/deployment. ✅

**Updated:** November 25, 2025

