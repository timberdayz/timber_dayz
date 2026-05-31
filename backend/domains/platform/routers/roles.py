"""
Legacy shim for role management routes.

The canonical admin RBAC routes now live in
`backend.domains.platform.routers.rbac_admin`.
"""

from backend.domains.platform.routers.rbac_admin import router

__all__ = ["router"]
