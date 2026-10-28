"""测试环境护栏的单元测试。

护栏本身也需要被测试保护 —— 一旦它失效, 回归测试就会连上真实业务库,
把真实文件的入库状态改坏(2026-10-28 真实事故)。

覆盖四件事:
1. 护栏开启时, ``DATABASE_URL`` 被强制成隔离库(无视 .env / 环境变量)
2. 护栏开启时, ``load_project_env`` 不覆盖护栏保护的变量
3. 护栏关闭时, 生产路径完全不受影响
4. 隔离库地址本身必须是可用且不指向真实业务库的
"""

from __future__ import annotations

import importlib
import os

import pytest

from backend.utils import project_env


# ---------------------------------------------------------------------------
# 1. 源头拦截: 护栏开启 => DATABASE_URL 强制隔离
# ---------------------------------------------------------------------------


def test_guard_forces_isolated_database_url(monkeypatch):
    """护栏开启时, 即使环境变量指向真实库, 配置也必须是隔离库。"""
    monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp",
    )
    monkeypatch.setenv(
        project_env.TEST_DATABASE_URL_VAR,
        "postgresql://test:test@127.0.0.1:15445/test",
    )

    config_module = importlib.reload(importlib.import_module("backend.utils.config"))
    try:
        settings = config_module.get_settings()
        assert "15432" not in settings.DATABASE_URL
        assert settings.DATABASE_URL == (
            "postgresql://test:test@127.0.0.1:15445/test"
        )
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)


def test_guard_ignores_database_url_even_when_it_looks_like_a_test_db(monkeypatch):
    """护栏开启时**只认** ``XIHONG_TEST_DATABASE_URL``。

    连环境变量里的 ``DATABASE_URL`` 都不采信 —— 否则改一下环境变量
    就能把测试指回真实业务库(护栏形同虚设)。
    """
    monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp",
    )
    monkeypatch.delenv(project_env.TEST_DATABASE_URL_VAR, raising=False)

    config_module = importlib.reload(importlib.import_module("backend.utils.config"))
    try:
        settings = config_module.get_settings()
        assert "15432" not in settings.DATABASE_URL
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)


def test_guard_off_keeps_production_database_url(monkeypatch):
    """护栏关闭时, 生产路径完全不受影响。"""
    monkeypatch.delenv(project_env.TEST_ENV_GUARD_VAR, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp",
    )

    config_module = importlib.reload(importlib.import_module("backend.utils.config"))
    try:
        settings = config_module.get_settings()
        assert settings.DATABASE_URL == (
            "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
        )
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)


def test_is_test_env_guarded_accepts_common_truthy_values(monkeypatch):
    for raw in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, raw)
        assert project_env.is_test_env_guarded() is True

    for raw in ("0", "false", "", "no"):
        monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, raw)
        assert project_env.is_test_env_guarded() is False


# ---------------------------------------------------------------------------
# 2. 防覆盖: 护栏开启 => load_project_env 不覆盖护栏保护的变量
# ---------------------------------------------------------------------------


def test_load_project_env_does_not_override_under_guard(tmp_path, monkeypatch):
    """护栏开启时, .env 不能把隔离库地址覆盖回真实库。

    这条最关键 —— ``backend/main.py`` 在 import 时会调用
    ``load_project_env(project_root)``, 若它覆盖了, 护栏就形同虚设。
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp\n"
        "XIHONG_TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:15445/test\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:15445/test")
    monkeypatch.setenv(
        project_env.TEST_DATABASE_URL_VAR,
        "postgresql://test:test@127.0.0.1:15445/test",
    )

    project_env.load_project_env(tmp_path)

    assert "15432" not in os.environ.get("DATABASE_URL", "")
    assert "15432" not in os.environ.get(project_env.TEST_DATABASE_URL_VAR, "")


def test_load_project_env_overrides_without_guard(tmp_path, monkeypatch):
    """护栏关闭时, .env 照常覆盖(生产行为不变)。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp\n",
        encoding="utf-8",
    )

    monkeypatch.delenv(project_env.TEST_ENV_GUARD_VAR, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:15445/test")

    project_env.load_project_env(tmp_path)

    assert "15432" in os.environ.get("DATABASE_URL", "")


def test_load_project_env_keeps_other_variables_override_semantics(tmp_path, monkeypatch):
    """护栏只保护自己的变量, **不改变** load_dotenv 的其它覆盖语义。

    ``.env.local`` 必须能覆盖 ``.env``, 也能覆盖既有环境变量 ——
    这是 ``load_project_env`` 的既有契约, 护栏不能顺手改掉。
    """
    (tmp_path / ".env").write_text("REDIS_URL=redis://base\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("REDIS_URL=redis://local\n", encoding="utf-8")

    monkeypatch.setenv(project_env.TEST_ENV_GUARD_VAR, "1")
    monkeypatch.setenv("REDIS_URL", "redis://preset")

    project_env.load_project_env(tmp_path)

    assert os.getenv("REDIS_URL") == "redis://local"


# ---------------------------------------------------------------------------
# 3. 引擎侧: 隔离库 URL 必须能被 SQLAlchemy 解析
# ---------------------------------------------------------------------------


def test_isolated_database_url_is_parseable():
    """护栏用的隔离库 URL 必须能被 SQLAlchemy 解析, 且不指向真实业务库。

    隔离库是**一次性 PostgreSQL 容器**(固定端口), 不是 SQLite ——
    本项目的表分布在 PG 的 schema 命名空间里, SQLite 建不出来。
    """
    from sqlalchemy.engine import url as sa_url

    from backend.utils.config import _TEST_ISOLATED_DATABASE_URL

    parsed = sa_url.make_url(_TEST_ISOLATED_DATABASE_URL)
    assert parsed.drivername.startswith("postgresql")
    assert "15432" not in parsed.render_as_string()


def test_isolated_database_url_is_not_the_real_database():
    """隔离库地址绝不能与真实业务库地址相同。"""
    from backend.utils.project_env import isolated_database_url

    url = isolated_database_url()
    assert "15432" not in url
    assert "xihong_erp" not in url.replace("xihong_erp_test", "")


@pytest.mark.parametrize(
    "raw",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite+aiosqlite://",
        "sqlite+aiosqlite:///:memory:",
        "sqlite:///./temp/isolated.db",
    ],
)
def test_get_async_database_url_keeps_double_slash(raw):
    """``get_async_database_url`` 必须保留 ``//`` 分隔符。

    单斜杠形式 SQLAlchemy 解析不了, 会让测试进程连不上任何库。
    """
    from backend.models.database import get_async_database_url

    converted = get_async_database_url(raw)
    assert "//" in converted.split(":", 1)[1], converted

    from sqlalchemy.engine import url as sa_url

    sa_url.make_url(converted)


def test_get_async_database_url_keeps_sqlite_path():
    """``sqlite:///path/to.db`` 转换后路径不能被当成 host。"""
    from backend.models.database import get_async_database_url

    converted = get_async_database_url("sqlite:///./temp/isolated.db")
    assert converted == "sqlite+aiosqlite:///./temp/isolated.db"


def test_get_async_database_url_converts_postgres():
    from backend.models.database import get_async_database_url

    converted = get_async_database_url(
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
    )
    assert converted.startswith("postgresql+asyncpg://")
    assert "15432/xihong_erp" in converted


def test_get_async_database_url_converts_postgres_with_explicit_driver():
    """带驱动后缀的 URL 也要换成 asyncpg, 且不能残留旧驱动。"""
    from backend.models.database import get_async_database_url

    converted = get_async_database_url(
        "postgresql+psycopg2://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
    )
    assert converted.startswith("postgresql+asyncpg://")
    assert "psycopg2" not in converted
