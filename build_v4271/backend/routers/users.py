"""
用户管理API路由 - 聚合入口

将 users_admin 和 users_me 的子路由合并为单一 router，
供 backend/main.py 以 ``users.router`` 方式直接使用，保持向后兼容。
"""

from fastapi import APIRouter

from backend.routers.users_admin import router as _admin_router
from backend.routers.users_me import router as _me_router

# SSOT: 权限依赖已迁移至 backend.dependencies.auth，此处 re-export 保持向后兼容
from backend.dependencies.auth import require_admin  # noqa: F401

router = APIRouter()
router.include_router(_admin_router)
router.include_router(_me_router)
