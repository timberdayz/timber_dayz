"""
Legacy import shim for role management routes.
"""

from backend.domains.platform.routers.rbac_admin import router

__all__ = ["router"]
