"""
User model and related models
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from passlib.context import CryptContext
from models.base import BaseModel

# Password hashing - bcrypt with truncate disabled to handle manually
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)


class User(BaseModel):
    """User account model"""
    
    __tablename__ = "users"
    
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # NULL for OAuth-only users
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    avatar_url = Column(Text, nullable=True)
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")
    is_active = Column(Boolean, default=True, index=True)
    is_locked = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    metadata = Column(JSONB, default={})
    
    # Relationships
    created_user = relationship("User", remote_side=[id])
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password: str):
        """Hash and set password (truncates to 72 chars for bcrypt)"""
        self.password_hash = pwd_context.hash(password[:72])
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        if not self.password_hash:
            return False
        return pwd_context.verify(password, self.password_hash)
    
    @property
    def full_name(self) -> str:
        """Get full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        else:
            return self.username
    
    def to_dict(self, include_sensitive: bool = False):
        """Convert to dictionary, optionally exclude sensitive fields"""
        data = super().to_dict()
        
        if not include_sensitive:
            data.pop("password_hash", None)
        
        data["full_name"] = self.full_name
        return data


class Role(BaseModel):
    """RBAC role model"""
    
    __tablename__ = "roles"
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_system_role = Column(Boolean, default=False)  # System roles cannot be deleted
    
    # Relationships
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class Permission(BaseModel):
    """Permission model"""
    
    __tablename__ = "permissions"
    
    resource = Column(String(100), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True) 
    description = Column(Text, nullable=True)
    
    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(BaseModel):
    """Role to permission mapping"""
    
    __tablename__ = "role_permissions"
    
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)
    
    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class UserRole(BaseModel):
    """User to role mapping"""
    
    __tablename__ = "user_roles"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="user_roles", foreign_keys=[user_id])
    role = relationship("Role", back_populates="user_roles")
    creator = relationship("User", foreign_keys=[created_by])


class OAuthProvider(BaseModel):
    """OAuth provider configuration"""
    
    __tablename__ = "oauth_providers"
    
    name = Column(String(100), unique=True, nullable=False)  # e.g., 'google', 'azure'
    display_name = Column(String(100), nullable=False)
    client_id = Column(String(255), nullable=False)
    client_secret_encrypted = Column(Text, nullable=False)  # Encrypted
    authorization_url = Column(Text, nullable=False)
    token_url = Column(Text, nullable=False)
    user_info_url = Column(Text, nullable=True)
    scope = Column(String(500), default="openid profile email")
    is_enabled = Column(Boolean, default=True)
    metadata = Column(JSONB, default={})


class UserOAuthConnection(BaseModel):
    """User OAuth connection tracking"""
    
    __tablename__ = "user_oauth_connections"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("oauth_providers.id"), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    access_token_encrypted = Column(Text, nullable=True)  # Encrypted
    refresh_token_encrypted = Column(Text, nullable=True)  # Encrypted
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User")
    provider = relationship("OAuthProvider")
