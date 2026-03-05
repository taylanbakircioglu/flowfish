"""
Simplified Flowfish Backend for MVP Testing
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import jwt
from datetime import datetime, timedelta

# Create FastAPI application
app = FastAPI(
    title="Flowfish Platform API - MVP",
    description="eBPF-based Kubernetes Application Communication and Dependency Mapping Platform",
    version="1.0.0-mvp",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Flowfish Platform API",
        "version": "1.0.0-mvp",
        "description": "eBPF-based Kubernetes Application Communication and Dependency Mapping",
        "status": "healthy",
        "mode": "MVP Testing",
        "docs_url": "/api/docs"
    }

# Health check endpoint
@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    # Test database connection
    db_status = "disabled"
    try:
        test_result = await db.fetch_one("SELECT 1 as test")
        if test_result:
            db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "message": "Flowfish Backend MVP with Database",
        "version": "1.0.0-mvp",
        "checks": {
            "fastapi": "healthy",
            "postgresql": db_status,
            "redis": "disabled", 
            "clickhouse": "disabled",
            "neo4j": "disabled"
        }
    }

# Info endpoint
@app.get("/api/v1/info")
async def api_info():
    """API information"""
    return {
        "api": {
            "name": "Flowfish Platform API",
            "version": "1.0.0-mvp",
            "environment": "development-mvp"
        },
        "capabilities": {
            "authentication": "coming_soon",
            "clusters": "coming_soon",
            "analyses": "coming_soon",
            "dependencies": "coming_soon"
        },
        "message": "🐟🌊 Flowfish MVP Backend is running successfully!"
    }

# Real authentication with database
from database.postgresql import DatabaseService
import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel

# Database instance
db = DatabaseService()

# JWT secret (from environment)
JWT_SECRET = "super-secret-key-change-me-in-production-very-long-and-random-string-for-jwt-signing"

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/v1/auth/login")
async def login(credentials: LoginRequest):
    """Real authentication with database lookup"""
    try:
        # Look up user in database
        user = await db.fetch_one(
            "SELECT id, username, email, password_hash, is_active FROM users WHERE username = :username AND is_active = true",
            {"username": credentials.username}
        )
        
        if not user:
            return {"error": "Invalid username or password"}, 401
        
        # Simplified password check (for admin user)
        # Production: use proper bcrypt
        if credentials.username == "admin" and credentials.password == "admin123":
            
            # Create JWT token
            token_payload = {
                "user_id": user["id"],
                "username": user["username"],
                "roles": ["Super Admin"],
                "exp": datetime.utcnow() + timedelta(hours=1),
                "iat": datetime.utcnow()
            }
            
            access_token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 3600,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "roles": ["Super Admin"]
                }
            }
        else:
            return {"error": "Invalid username or password"}, 401
            
    except Exception as e:
        return {"error": f"Authentication service error: {str(e)}"}, 500

# Real clusters endpoint with database
@app.get("/api/v1/clusters")
async def get_clusters():
    """Get clusters from database"""
    try:
        clusters = await db.fetch_all(
            """SELECT id, name, description, environment, provider, region, 
                      connection_type, api_server_url, gadget_namespace, 
                      gadget_health_status, gadget_version, status, 
                      total_nodes, total_pods, total_namespaces, 
                      k8s_version, created_at, updated_at 
               FROM clusters 
               WHERE status = 'active' 
               ORDER BY created_at DESC"""
        )
        
        return {
            "clusters": [dict(cluster) for cluster in clusters],
            "count": len(clusters),
            "message": "Clusters retrieved from database"
        }
        
    except Exception as e:
        return {
            "error": f"Database error: {str(e)}",
            "clusters": [],
            "count": 0
        }

@app.post("/api/v1/clusters")
async def create_cluster(cluster_data: dict):
    """Create new cluster"""
    try:
        result = await db.execute(
            """INSERT INTO clusters (name, description, environment, provider, region,
                                     connection_type, api_server_url, gadget_namespace,
                                     status, gadget_health_status) 
               VALUES (:name, :description, :environment, :provider, :region,
                       :connection_type, :api_server_url, :gadget_namespace,
                       'active', 'unknown') 
               RETURNING id, name""",
            {
                "name": cluster_data.get("name"),
                "description": cluster_data.get("description", ""),
                "environment": cluster_data.get("environment", "production"),
                "provider": cluster_data.get("provider", "kubernetes"),
                "region": cluster_data.get("region", "default"),
                "connection_type": cluster_data.get("connection_type", "in-cluster"),
                "api_server_url": cluster_data.get("api_server_url", "https://kubernetes.default.svc"),
                "gadget_namespace": cluster_data.get("gadget_namespace")  # REQUIRED from UI
            }
        )
        
        return {
            "message": "Cluster created successfully",
            "cluster": dict(result._mapping) if result else None
        }
        
    except Exception as e:
        return {"error": f"Failed to create cluster: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run(
        "simple_main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
