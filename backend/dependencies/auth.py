"""
认证与权限依赖 (Authentication & Authorization Dependencies)

从 backend/routers/auth.py 和 backend/routers/users.py 提取的
共享依赖函数，供所有 router 使用。

用法:
    from backend.dependencies.auth import get_current_user, require_admin
"""

import hashlib
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.database import get_async_db
from backend.services.rbac_service import normalize_role_code
from backend.services.auth_service import auth_service
from modules.core.db import DimUser, UserSession
from modules.core.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


def is_admin_user(current_user: DimUser) -> bool:
    return has_any_role_code(current_user, {"admin"})


def extract_role_codes(current_user: DimUser) -> set[str]:
    role_codes: set[str] = set()
    if getattr(current_user, "is_superuser", False):
        role_codes.add("admin")

    for role in getattr(current_user, "roles", []) or []:
        if isinstance(role, str):
            normalized = normalize_role_code(role)
            if normalized:
                role_codes.add(normalized)
            continue
        role_code = getattr(role, "role_code", None)
        role_name = getattr(role, "role_name", None)
        normalized_code = normalize_role_code(role_code)
        normalized_name = normalize_role_code(role_name)
        if normalized_code:
            role_codes.add(normalized_code)
        if normalized_name:
            role_codes.add(normalized_name)
    return role_codes


def has_any_role_code(current_user: DimUser, expected_codes: set[str]) -> bool:
    role_codes = extract_role_codes(current_user)
    return any(code in role_codes for code in expected_codes)


def is_admin_or_manager_user(current_user: DimUser) -> bool:
    return has_any_role_code(current_user, {"admin", "manager"})


def extract_access_token(
    request: Request | None = None,
    credentials: HTTPAuthorizationCredentials | None = None,
    websocket: WebSocket | None = None,
    query_token: str | None = None,
) -> str | None:
    """访问令牌的**唯一提取点**(SSOT)。

    历史背景
    --------
    登录优化把 access_token 搬进了 httpOnly cookie，前端不再持有 token。
    但令牌提取逻辑当时散落成 5 份副本(dependencies/auth.py、users_me.py、
    platform/routers/auth.py、通知 WS、采集 WS)，各自的来源优先级还不一样：

    - HTTP 三份:cookie → Authorization header
    - WebSocket 两份:query 参数 → cookie

    后果是同一套登录态在不同通道表现不一致(例如采集任务实时通道因为
    只认 query 参数而必然 close("Token required"))。

    现在统一到本函数，来源优先级：

    1. ``query_token``(WebSocket 握手 query 参数)
    2. httpOnly cookie ``access_token``
    3. ``Authorization: Bearer <token>`` header

    新增通道时**必须**调用本函数，不要再自己读 cookie/header。
    门禁: scripts/verify_access_token_extraction.py
    """
    if query_token:
        return query_token

    if request is not None and "access_token" in request.cookies:
        return request.cookies.get("access_token")

    if websocket is not None and "access_token" in websocket.cookies:
        return websocket.cookies.get("access_token")

    if credentials and credentials.credentials:
        return credentials.credentials

    if request is not None:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[len("Bearer ") :]

    return None


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
    token = extract_access_token(request, credentials)

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

        session_id = payload.get("sid")
        if not session_id:
            session_id = hashlib.sha256(token.encode()).hexdigest()
        session_result = await db.execute(
            select(UserSession).where(
                UserSession.session_id == session_id,
                UserSession.user_id == user_id,
            )
        )
        session = session_result.scalar_one_or_none()
        if not session or not session.is_active:
            raise HTTPException(
                status_code=401,
                detail="Session has been revoked",
            )
        if session.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=401,
                detail="Session has expired",
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


async def require_admin_or_manager(
    current_user: DimUser = Depends(get_current_user),
):
    if not is_admin_or_manager_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )
    return current_user
