"""
Base model class with common fields and utilities
"""

from sqlalchemy import Column, Integer, DateTime, func
from sqlalchemy.ext.declarative import declared_attr
from database.postgresql import Base


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    
    @declared_attr
    def created_at(cls):
        return Column(DateTime, default=func.current_timestamp(), nullable=False)
    
    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime,
            default=func.current_timestamp(),
            onupdate=func.current_timestamp(),
            nullable=False
        )


class BaseModel(Base, TimestampMixin):
    """Base model class with common fields"""
    
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def __repr__(self):
        """String representation"""
        return f"<{self.__class__.__name__}(id={self.id})>"
