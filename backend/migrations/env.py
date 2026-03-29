"""Alembic migration environment configuration"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add the parent directory to path so we can import our models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all models here to ensure they're detected by Alembic
from models.base import BaseModel
from models.user import User, Role, Permission, RolePermission, UserRole, OAuthProvider, UserOAuthConnection
from models.cluster import Cluster, Namespace
from models.workload import Workload
from models.communication import Communication  
from models.analysis import Analysis, AnalysisRun

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata
target_metadata = BaseModel.metadata

# Get database URL from environment or config
database_url = os.getenv('DATABASE_URL') or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
