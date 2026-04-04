"""
认证与权限依赖 (Authentication & Authorization Dependencies)

从 backend/routers/auth.py 和 backend/routers/users.py 提取的
共享依赖函数，供所有 router 使用。

用法:
    from backend.dependencies.auth import get_current_user, require_admin
"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.database import get_async_db
from backend.services.auth_service import auth_service
from modules.core.db import DimUser
from modules.core.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


def is_admin_user(current_user: DimUser) -> bool:
    if getattr(current_user, "is_superuser", False):
        return True
    return any(
        (hasattr(role, "role_code") and role.role_code == "admin")
        or (hasattr(role, "role_name") and role.role_name == "admin")
        for role in getattr(current_user, "roles", []) or []
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db),
):
    """
    获取当前已认证用户。

    支持从 Cookie 和 Authorization Header 两种方式读取 token：
    - 优先从 Cookie 读取 (httpOnly Cookie，更安全)
    - 其次从 Header 读取 (向后兼容)
    """
    token = None

    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    elif credentials and credentials.credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication token",
        )

    try:
        payload = auth_service.verify_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

        result = await db.execute(
            select(DimUser)
            .where(DimUser.user_id == user_id)
            .options(selectinload(DimUser.roles))
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive",
            )

        if user.status != "active":
            raise HTTPException(
                status_code=403,
                detail=f"Account is {user.status}, access denied",
            )

        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )


async def require_admin(
    current_user: DimUser = Depends(get_current_user),
):
    """要求管理员权限。"""
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )
    return current_user
