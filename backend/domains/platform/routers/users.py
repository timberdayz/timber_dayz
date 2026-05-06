"""
用户管理API路由 - 聚合入口

将 users_admin 和 users_me 的子路由合并为单一 router，
供 backend/main.py 以 ``users.router`` 方式直接使用，保持向后兼容。
"""

from fastapi import APIRouter

import backend.routers.users_admin as legacy_admin_module
import backend.routers.users_me as legacy_me_module

# SSOT: 权限依赖已迁移至 backend.dependencies.auth，此处 re-export 保持向后兼容
from backend.dependencies.auth import require_admin  # noqa: F401


def _build_users_router() -> APIRouter:
    router = APIRouter()
    router.include_router(legacy_admin_module.router)
    router.include_router(legacy_me_module.router)
    return router


router = _build_users_router()


def _module_public_names(module: object) -> set[str]:
    module_all = getattr(module, "__all__", None)
    if module_all is not None:
        return set(module_all)
    return {name for name in vars(module) if not name.startswith("_")}


def __getattr__(name: str):
    if hasattr(legacy_admin_module, name):
        return getattr(legacy_admin_module, name)
    if hasattr(legacy_me_module, name):
        return getattr(legacy_me_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        set(globals())
        | set(dir(legacy_admin_module))
        | set(dir(legacy_me_module))
    )


__all__ = sorted(
    _module_public_names(legacy_admin_module)
    | _module_public_names(legacy_me_module)
    | {"require_admin", "router"}
)
