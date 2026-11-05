"""
JWT authentication service.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import base64
import binascii
import hashlib
import hmac
import re
import uuid
import json

import bcrypt
import jwt
from fastapi import HTTPException, status

from backend.utils.config import get_settings
from modules.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)


#: bcrypt 的哈希前缀（``$2a$`` / ``$2b$`` / ``$2x$`` / ``$2y$``）。
BCRYPT_HASH_PREFIXES = ("$2a$", "$2b$", "$2x$", "$2y$")

#: 一个**结构完整**的 bcrypt 哈希长什么样：``$2b$`` + 2 位代价 + ``$`` +
#: 22 位盐 + 31 位校验值 = 60 字符，字符集是 bcrypt 的 base64 字母表。
#:
#: 为什么必须先校验再交给 bcrypt
#: ------------------------------
#: 生产 / CI 装的是 **bcrypt 4.1.2**（Rust 后端），本机开发环境装的是 5.x。
#: 4.1.2 碰到**畸形**哈希（长度不对 / 盐太短）不是抛 ``ValueError``，而是
#: 直接 **panic**，在 Python 侧表现为 ``pyo3_runtime.PanicException`` ——
#: 那是 ``BaseException`` 的子类，**普通 ``except Exception`` 接不住**，
#: 会一路冒到登录接口 ⇒ HTTP 500。
#:
#: 所以：结构不合法的哈希**根本不进 bcrypt**，直接判"密码错误"。
_BCRYPT_HASH_PATTERN = re.compile(r"^\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}$")

#: 早期版本用 passlib ``pbkdf2_sha256`` 存的口令哈希前缀。
#:
#: 历史事实：``backend/utils/auth.py`` 里的 ``pwd_context`` 用的是 pbkdf2_sha256，
#: 而所有**写入**口令的路径（注册 / 改密 / 建用户 / 各种脚本）后来都换成了 bcrypt。
#: 于是库里同时存在两种算法的哈希 —— 只认 bcrypt 的校验逻辑碰到 pbkdf2 哈希时
#: 会抛 ``ValueError: Invalid salt``，登录接口直接 500（而不是 401）。
PBKDF2_HASH_PREFIX = "$pbkdf2-sha256$"


def _b64_decode(value: str) -> bytes:
    """解 passlib 用的 base64（**不带** ``=`` 补位）。

    passlib 的 ``ab64_decode`` = **标准 base64**，只把 bcrypt 风格的
    ``.`` 当作 ``+``（bcrypt 的 altchars）。补位规则与它保持一致：
    长度 % 4 == 1 是非法 base64（直接判失败）。
    """
    data = value.replace(".", "+")
    remainder = len(data) & 3
    if remainder == 1:
        raise ValueError("invalid base64 input")
    if remainder == 2:
        data += "=="
    elif remainder == 3:
        data += "="
    return base64.b64decode(data)


def _decode_candidates(value: str) -> list[bytes]:
    """给一个 base64 片段准备所有可能的原始字节。

    候选 1：按 passlib 的 altchars 规则解码（``.`` 当作 ``+``）得到的字节；
    候选 2：字面字符串的 UTF-8 字节（某些工具直接拿字符串当盐）。
    """
    candidates: list[bytes] = []
    try:
        decoded = _b64_decode(value)
    except (ValueError, TypeError, binascii.Error):
        decoded = b""
    if decoded:
        candidates.append(decoded)
    literal = value.encode("utf-8")
    if literal and literal not in candidates:
        candidates.append(literal)
    return candidates


def verify_pbkdf2_sha256(password: str, hashed_password: str) -> bool:
    """校验 passlib ``pbkdf2_sha256`` 哈希。

    格式：``$pbkdf2-sha256$<rounds>$<salt_b64>$<checksum_b64>``，
    其中 salt/checksum 都是 **bcrypt 风格 altchars 的 base64**
    （标准 base64，只是把 ``.`` 当作 ``+``；无 ``=`` 补位），
    checksum = ``pbkdf2_hmac('sha256', password, salt_bytes, rounds)``。

    只用标准库实现 —— 不引入 passlib 依赖，也不和
    ``backend/utils/auth.py`` 形成循环 import（那边 import 本模块）。
    任何解析异常都当成"校验不通过"，绝不向上抛。

    盐 / 校验值各准备**两个候选**（base64 解码后的字节、字面字符串字节），
    两两组合都试一遍 —— 这样无论存量哈希当年是用哪种工具生成的，
    都能被正确校验，而不是"格式对但永远不通过"。
    """
    try:
        parts = hashed_password.split("$")
        # ['', 'pbkdf2-sha256', rounds, salt, checksum]
        if len(parts) != 5:
            return False
        rounds = int(parts[2])
        if rounds <= 0:
            return False

        salt_candidates = _decode_candidates(parts[3])
        checksum_candidates = _decode_candidates(parts[4])
        if not salt_candidates or not checksum_candidates:
            return False

        secret = password.encode("utf-8")
        for salt in salt_candidates:
            for expected in checksum_candidates:
                derived = hashlib.pbkdf2_hmac(
                    "sha256",
                    secret,
                    salt,
                    rounds,
                    dklen=len(expected),
                )
                if hmac.compare_digest(derived, expected):
                    return True
        return False
    except (ValueError, TypeError, binascii.Error):
        return False


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
        """按哈希前缀选算法校验口令。

        为什么不能只认 bcrypt
        ------------------
        库里同时存在 bcrypt（``$2b$12$...``）和早期 passlib
        ``pbkdf2_sha256``（``$pbkdf2-sha256$...``）两种哈希。直接
        ``bcrypt.checkpw(pbkdf2_hash)`` 会抛 ``ValueError: Invalid salt``，
        登录接口就变成 **HTTP 500**（账号"服务异常"），而不是正常的
        401「账号或密码错误」—— 用户既登不进去，也看不出到底哪里错了。

        现在的规则
        ----------
        - ``$2a$`` / ``$2b$`` / ``$2x$`` / ``$2y$`` → bcrypt
        - ``$pbkdf2-sha256$`` → pbkdf2_sha256（标准库实现）
        - 其它 / 损坏的哈希 → **返回 False**（⇒ 401），绝不抛异常

        写入口径统一是 bcrypt（见 ``hash_password``），所以新密码一定是
        bcrypt；这里的兼容分支只负责让**存量**老账号能登录。
        """
        if not hashed_password:
            return False
        candidate = hashed_password.strip()
        if candidate.startswith(BCRYPT_HASH_PREFIXES):
            if not _BCRYPT_HASH_PATTERN.match(candidate):
                # 畸形哈希：连 bcrypt 都不让它进门（bcrypt 4.1.2 的 Rust 后端会 panic）
                logger.warning(
                    "[AuthService] malformed bcrypt hash rejected before checkpw"
                )
                return False
            try:
                return bcrypt.checkpw(
                    password.encode("utf-8"), candidate.encode("utf-8")
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException:  # noqa: BLE001
                # 含 Rust 后端的 PanicException（BaseException 子类）：
                # 一律按"密码错误"处理，绝不让它冒成 HTTP 500。
                logger.warning(
                    "[AuthService] bcrypt verification raised; treated as mismatch"
                )
                return False
        if candidate.startswith(PBKDF2_HASH_PREFIX):
            return verify_pbkdf2_sha256(password, candidate)
        logger.warning(
            "[AuthService] unsupported password hash scheme: %s",
            candidate[:16],
        )
        return False

    def create_access_token(self, data: Dict[str, Any]) -> str:
        payload = data.copy()
        payload.update(
            {
                "exp": datetime.now(timezone.utc)
                + timedelta(minutes=self.access_token_expire_minutes),
                "type": "access",
                "jti": uuid.uuid4().hex,
            }
        )
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        payload = data.copy()
        payload.update(
            {
                "exp": datetime.now(timezone.utc)
                + timedelta(days=self.refresh_token_expire_days),
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

    async def _add_refresh_token_to_blacklist_atomic(
        self, refresh_token: str, expire_seconds: int
    ) -> bool:
        redis_client = self._require_refresh_blacklist_client()
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        blacklist_key = f"xihong_erp:refresh_token_blacklist:{token_hash}"
        try:
            result = await redis_client.set(
                blacklist_key, "1", ex=expire_seconds, nx=True
            )
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
            raw_value = await redis_client.get(
                self._refresh_rotation_result_key(refresh_token)
            )
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
        return await self._add_refresh_token_to_blacklist_atomic(
            refresh_token, expire_seconds
        )

    async def refresh_token_pair(
        self, refresh_token: str, session_id: str | None = None
    ) -> Dict[str, str]:
        payload = self.verify_token(refresh_token, "refresh")
        resolved_session_id = session_id or payload.get("sid") or uuid.uuid4().hex
        payload_with_session = dict(payload)
        payload_with_session["sid"] = resolved_session_id

        if await self._is_refresh_token_blacklisted(refresh_token):
            cached_pair = await self._get_refresh_rotation_result(
                refresh_token, payload_with_session
            )
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

            added = await self._add_refresh_token_to_blacklist_atomic(
                refresh_token, expire_seconds
            )
            if not added:
                cached_pair = await self._get_refresh_rotation_result(
                    refresh_token, payload_with_session
                )
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
        await self._store_refresh_rotation_result(
            refresh_token, payload_with_session, token_pair
        )
        return token_pair


auth_service = AuthService()
