#!/usr/bin/env python3
"""
Legacy JWT auth helpers.

This module is retained for backward compatibility only.
New runtime code should prefer:
- backend.dependencies.auth
- backend.services.rbac_service

The legacy permission helpers intentionally resolve permissions from the
current RBAC payload / system role defaults instead of maintaining a separate
stale role-permission table.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.services.auth_service import auth_service
from backend.services.rbac_service import normalize_role_code, parse_permission_ids
from backend.services.system_role_service import DEFAULT_SYSTEM_ROLES
from modules.core.db import User
from modules.core.logger import get_logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = get_logger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "xihong-erp-secret-key-2025-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

if SECRET_KEY == "xihong-erp-secret-key-2025-change-in-production":
    logger.warning("[WARN] Using default JWT secret. Set JWT_SECRET_KEY in production.")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as error:
        logger.error("Password verification failed: %s", error)
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.JWTError as error:
        logger.error("Token decode failed: %s", error)
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession | None = None,
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_info = {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "email": payload.get("email"),
        "role": payload.get("role", "user"),
        "is_active": payload.get("is_active", True),
        "permissions": payload.get("permissions", []),
    }

    if db and user_info["user_id"]:
        try:
            result = await db.execute(select(User).where(User.id == user_info["user_id"]))
            user = result.scalar_one_or_none()
            if user:
                user_info.update(
                    {
                        "email": user.email,
                        "is_active": user.is_active,
                        "role": user.role,
                    }
                )
        except Exception as error:
            logger.warning("Failed to load user info: %s", error)

    return user_info


def _resolve_legacy_role_permissions(role: str) -> list[str]:
    normalized_role = normalize_role_code(role or "")
    if normalized_role == "admin":
        return ["*"]
    return list(DEFAULT_SYSTEM_ROLES.get(normalized_role, {}).get("permissions", []))


def has_permission(user: Dict[str, Any], permission: str) -> bool:
    explicit_permissions = parse_permission_ids(user.get("permissions", []))
    permissions = explicit_permissions or _resolve_legacy_role_permissions(user.get("role", ""))

    if "*" in permissions:
        return True

    return permission in permissions


def require_permission(permission: str):
    """Legacy decorator kept for backward compatibility only."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user: Dict = Depends(get_current_user), **kwargs):
            if not has_permission(user, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions: requires '{permission}'",
                )
            return await func(*args, user=user, **kwargs)

        return wrapper

    return decorator


if __name__ == "__main__":
    password = "test_password_123"
    hashed = get_password_hash(password)
    print("Password verify:", verify_password(password, hashed))

    token = create_access_token(
        {
            "user_id": 1,
            "username": "admin",
            "email": "admin@xihong.com",
            "role": "admin",
        }
    )
    print("Token payload:", decode_access_token(token))
    print("Legacy permission check:", has_permission({"role": "admin"}, "anything"))
