"""Pytest configuration and shared fixtures."""
import os
import sys
import pytest

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Set test environment variables before any imports
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://agent:agentpass@localhost:5432/social_agent_test")
os.environ.setdefault("SYNC_DATABASE_URL", "postgresql://agent:agentpass@localhost:5432/social_agent_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("ELASTICSEARCH_URL", "http://localhost:9200")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENVIRONMENT", "test")
