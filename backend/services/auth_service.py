"""
JWT authentication service.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import uuid
import hashlib
import json

import bcrypt
import jwt
from fastapi import HTTPException, status

from backend.utils.config import get_settings
from modules.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


class AuthService:
    """Authentication service helpers."""

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS

    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))

    def create_access_token(self, data: Dict[str, Any]) -> str:
        payload = data.copy()
        payload.update(
            {
                "exp": datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes),
                "type": "access",
                "jti": uuid.uuid4().hex,
            }
        )
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        payload = data.copy()
        payload.update(
            {
                "exp": datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days),
                "type": "refresh",
                "jti": uuid.uuid4().hex,
            }
        )
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )

            exp = payload.get("exp")
            if exp is None or datetime.now(timezone.utc).timestamp() > exp:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired",
                )

            return payload
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            ) from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from exc

    def create_token_pair(
        self,
        user_id: int,
        username: str,
        roles: list,
        session_id: str | None = None,
    ) -> Dict[str, str]:
        resolved_session_id = session_id or uuid.uuid4().hex
        token_data = {
            "user_id": user_id,
            "username": username,
            "roles": roles,
            "sid": resolved_session_id,
        }
        return {
            "access_token": self.create_access_token(token_data),
            "refresh_token": self.create_refresh_token(token_data),
            "token_type": "bearer",
            "session_id": resolved_session_id,
        }

    def refresh_access_token(self, refresh_token: str) -> str:
        payload = self.verify_token(refresh_token, "refresh")
        token_data = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "roles": payload.get("roles"),
        }
        if payload.get("sid"):
            token_data["sid"] = payload.get("sid")
        return self.create_access_token(token_data)

    def _get_redis_client(self):
        try:
            from backend.services.cache_service import get_cache_service

            cache_service = get_cache_service()
            return cache_service.redis_client if cache_service else None
        except Exception as exc:
            logger.debug(f"[Auth] Redis client unavailable: {exc}")
            return None

    def _require_refresh_blacklist_client(self):
        redis_client = self._get_redis_client()
        if not redis_client:
            logger.error("[Auth] Redis unavailable during refresh token validation")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh token service unavailable",
            )
        return redis_client

    async def _is_refresh_token_blacklisted(self, refresh_token: str) -> bool:
        redis_client = self._require_refresh_blacklist_client()
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        blacklist_key = f"xihong_erp:refresh_token_blacklist:{token_hash}"
        try:
            exists = await redis_client.exists(blacklist_key)
            return exists > 0
        except Exception as exc:
            logger.error(f"[Auth] Failed to check refresh token blacklist: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh token service unavailable",
            ) from exc

    async def _add_refresh_token_to_blacklist_atomic(self, refresh_token: str, expire_seconds: int) -> bool:
        redis_client = self._require_refresh_blacklist_client()
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        blacklist_key = f"xihong_erp:refresh_token_blacklist:{token_hash}"
        try:
            result = await redis_client.set(blacklist_key, "1", ex=expire_seconds, nx=True)
            if result:
                return True
            logger.warning(f"[Auth] Refresh token already revoked: {token_hash[:8]}...")
            return False
        except Exception as exc:
            logger.error(f"[Auth] Failed to write refresh token blacklist: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh token service unavailable",
            ) from exc

    def _refresh_rotation_result_key(self, refresh_token: str) -> str:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        return f"xihong_erp:refresh_token_rotation_result:{token_hash}"

    async def _get_refresh_rotation_result(
        self,
        refresh_token: str,
        payload: Dict[str, Any],
    ) -> Dict[str, str] | None:
        redis_client = self._require_refresh_blacklist_client()
        try:
            raw_value = await redis_client.get(self._refresh_rotation_result_key(refresh_token))
        except Exception as exc:
            logger.error(f"[Auth] Failed to read refresh rotation result: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh token service unavailable",
            ) from exc

        if not raw_value:
            return None
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")

        try:
            cached = json.loads(raw_value)
        except (TypeError, ValueError):
            logger.warning("[Auth] Ignoring malformed refresh rotation result cache")
            return None

        if cached.get("user_id") != payload.get("user_id"):
            return None
        if cached.get("sid") != payload.get("sid"):
            return None

        tokens = cached.get("tokens")
        if not isinstance(tokens, dict):
            return None
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            return None
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": tokens.get("token_type", "bearer"),
            "session_id": tokens.get("session_id") or cached.get("sid"),
        }

    async def _store_refresh_rotation_result(
        self,
        refresh_token: str,
        payload: Dict[str, Any],
        token_pair: Dict[str, str],
    ) -> None:
        redis_client = self._require_refresh_blacklist_client()
        cache_payload = {
            "user_id": payload.get("user_id"),
            "sid": token_pair.get("session_id") or payload.get("sid"),
            "tokens": token_pair,
        }
        try:
            await redis_client.set(
                self._refresh_rotation_result_key(refresh_token),
                json.dumps(cache_payload),
                ex=settings.REFRESH_TOKEN_ROTATION_GRACE_SECONDS,
            )
        except Exception as exc:
            logger.error(f"[Auth] Failed to store refresh rotation result: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Refresh token service unavailable",
            ) from exc

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        payload = self.verify_token(refresh_token, "refresh")
        exp = payload.get("exp")
        if exp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        expire_seconds = int(exp - datetime.now(timezone.utc).timestamp())
        if expire_seconds <= 0:
            return False
        return await self._add_refresh_token_to_blacklist_atomic(refresh_token, expire_seconds)

    async def refresh_token_pair(self, refresh_token: str, session_id: str | None = None) -> Dict[str, str]:
        payload = self.verify_token(refresh_token, "refresh")
        resolved_session_id = session_id or payload.get("sid") or uuid.uuid4().hex
        payload_with_session = dict(payload)
        payload_with_session["sid"] = resolved_session_id

        if await self._is_refresh_token_blacklisted(refresh_token):
            cached_pair = await self._get_refresh_rotation_result(refresh_token, payload_with_session)
            if cached_pair:
                return cached_pair
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked",
            )

        exp = payload.get("exp")
        if exp is not None:
            current_time = datetime.now(timezone.utc).timestamp()
            expire_seconds = int(exp - current_time)
            if expire_seconds <= 0:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expired",
                )
            max_lifetime = self.refresh_token_expire_days * 24 * 60 * 60
            if expire_seconds > max_lifetime:
                logger.warning(
                    f"[Auth] Refresh token expiry exceeded configured lifetime: {expire_seconds}"
                )
                expire_seconds = max_lifetime

            added = await self._add_refresh_token_to_blacklist_atomic(refresh_token, expire_seconds)
            if not added:
                cached_pair = await self._get_refresh_rotation_result(refresh_token, payload_with_session)
                if cached_pair:
                    return cached_pair
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked (reuse detected)",
                )

        token_data = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "roles": payload.get("roles"),
            "sid": resolved_session_id,
        }
        token_pair = {
            "access_token": self.create_access_token(token_data),
            "refresh_token": self.create_refresh_token(token_data),
            "token_type": "bearer",
            "session_id": resolved_session_id,
        }
        await self._store_refresh_rotation_result(refresh_token, payload_with_session, token_pair)
        return token_pair


auth_service = AuthService()
