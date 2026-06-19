"""
Backend API routes aggregator.
Re-exports the aggregated router and public API contract from __init__.py.

This module serves as the main entry point for routes, delegating to domain-specific routers.
Do not define routes directly here.
"""
from backend.api import router
from backend.api.common import (
    update_embeddings_cache,
    embeddings_cache,
    limiter,
    HAS_SLOWAPI,
)

__all__ = [
    "router",
    "update_embeddings_cache",
    "embeddings_cache",
    "limiter",
    "HAS_SLOWAPI",
]
