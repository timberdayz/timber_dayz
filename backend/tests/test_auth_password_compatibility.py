"""登录口令哈希兼容：bcrypt + 存量 pbkdf2_sha256。

背景
----
``core.dim_users.password_hash`` 里同时存在两种算法：

- bcrypt（``$2b$12$...``）—— 所有写入口径（注册 / 改密 / 建用户 / 脚本）都在用
- passlib ``pbkdf2_sha256``（``$pbkdf2-sha256$29000$...``）—— 早期版本留下的存量哈希

旧的 ``verify_password`` 只调 ``bcrypt.checkpw``，碰到 pbkdf2 哈希会抛
``ValueError: Invalid salt`` ⇒ 登录接口 500（账号"服务异常"），而不是 401。

这几条测试锁住三件事：

1. 两种算法都能校验通过；
2. **任何**畸形 / 未知 / 损坏的哈希都只返回 False，**绝不抛异常**
   （抛异常 = 500 = 用户看到"服务异常"，比"密码错误"糟糕得多）；
3. 新写入的哈希仍然是 bcrypt（口径不倒退）。
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from passlib.context import CryptContext

from backend.services.auth_service import AuthService, verify_pbkdf2_sha256

# 生产库真实存在的一条 pbkdf2 哈希（yehaichuan），用来锁住「存量哈希不会炸」
PRODUCTION_PBKDF2_HASH = (
    "$pbkdf2-sha256$29000$9z5HSGlN6V1rzfmf07oXYg"
    "$7e1kznx7SckC9Vr3IhwiCmYDxGXYmEu0aj3ds/vNY4k"
)

pbkdf2_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def _stdlib_pbkdf2_hash(password: str, rounds: int = 29000) -> str:
    """独立复刻 passlib 的格式（测试里用它当"另一种实现"的对照）。

    注意：PBKDF2 的盐是 **base64 解码后的原始字节**，不是 base64 字符串本身。
    """
    salt_bytes = hashlib.sha256(password.encode("utf-8")).digest()[:16]
    salt = base64.b64encode(salt_bytes).decode().rstrip("=")
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        rounds,
        dklen=32,
    )
    checksum = base64.b64encode(derived).decode().rstrip("=")
    return f"$pbkdf2-sha256${rounds}${salt}${checksum}"


def test_bcrypt_hash_round_trip():
    service = AuthService()
    hashed = service.hash_password("XhLocalTest!2026")

    assert hashed.startswith("$2")
    assert service.verify_password("XhLocalTest!2026", hashed) is True
    assert service.verify_password("wrong-password", hashed) is False


def test_pbkdf2_sha256_hash_is_accepted():
    """存量 pbkdf2 账号必须能登录。"""
    service = AuthService()
    hashed = pbkdf2_context.hash("legacy-password-2026")

    assert hashed.startswith("$pbkdf2-sha256$")
    assert service.verify_password("legacy-password-2026", hashed) is True
    assert service.verify_password("legacy-password-2025", hashed) is False


def test_pbkdf2_matches_independent_stdlib_implementation():
    """本实现必须和独立复刻的格式互相兼容（防格式理解偏差）。"""
    hashed = _stdlib_pbkdf2_hash("compat-probe")

    assert verify_pbkdf2_sha256("compat-probe", hashed) is True
    assert verify_pbkdf2_sha256("other", hashed) is False


def test_production_pbkdf2_hash_never_raises():
    """生产真实存量哈希：密码不对时返回 False，且**不抛异常**。"""
    service = AuthService()

    assert service.verify_password("any-guess", PRODUCTION_PBKDF2_HASH) is False


def test_malformed_hashes_return_false_without_raising():
    """畸形哈希 = 密码错误，不是服务异常。

    特别提醒：生产 / CI 装的是 **bcrypt 4.1.2**（Rust 后端），它碰到畸形
    哈希抛的是 ``pyo3_runtime.PanicException``（``BaseException`` 子类），
    普通 ``except Exception`` 接不住 ⇒ 会冒成 HTTP 500。
    所以实现必须**在调用 bcrypt 之前**就把结构不合法的哈希挡掉。
    """
    service = AuthService()
    malformed = [
        "",
        "   ",
        "$pbkdf2-sha256$",
        "$pbkdf2-sha256$notanumber$c2FsdA$aGFzaA",
        "$pbkdf2-sha256$29000$not-base64!!$aGFzaA",
        "$2b$12$broken",
        "$2b$12",
        "$2b$12$" + "a" * 53,
        "$2b$12$" + "!" * 53,
        "plaintext-password",
        "$argon2id$v=19$m=65536,t=3,p=4$aaaa$bbbb",
    ]

    for candidate in malformed:
        assert service.verify_password("whatever", candidate) is False, candidate


def test_none_hash_returns_false():
    service = AuthService()

    assert service.verify_password("whatever", None) is False  # type: ignore[arg-type]


def test_new_hashes_stay_bcrypt():
    """写入口径不倒退：新建的哈希必须是 bcrypt。"""
    service = AuthService()

    assert service.hash_password("another-password").startswith("$2")
