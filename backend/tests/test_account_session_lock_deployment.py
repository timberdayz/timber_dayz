"""账号会话锁(Task 3)的**部署契约**测试。

守住两件很容易被改坏、且一旦坏掉就是**灾难性**的事:

* **锁后端必须显式是 Redis** —— 采集容器若没显式声明
  ``ACCOUNT_SESSION_LOCK_BACKEND``, 就靠 ``ENVIRONMENT`` 的隐式推断,
  非生产部署会静默降级为进程内锁: 只在同进程内互斥, 跨进程仍然可能
  **双开同一个 profile 目录** -> 两条采集链路互相覆盖登录态。

* **持久 profile 目录必须挂载到宿主机** —— profile 是登录态的**唯一载体**
  (D5), 若只存在于容器的临时文件系统里, 容器一重建/重新部署,
  **所有账号的 Chromium 登录态全部丢失**, 每次都要重新人工登录 + 过验证码。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

yaml = pytest.importorskip("yaml")

#: 仓库根目录(backend/tests/xxx.py -> 仓库根)
REPO_ROOT = Path(__file__).resolve().parents[2]

#: 持久 profile 目录在容器内的路径(REPO_ROOT/profiles, REPO_ROOT=/app)
PROFILES_MOUNT = "./profiles:/app/profiles"


def _load_compose(file_name: str) -> Dict[str, Any]:
    """解析 compose 文件(只读, 不做任何变量插值)。"""
    path = REPO_ROOT / file_name
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_collection_service_declares_redis_lock_backend() -> None:
    """采集服务必须**显式**使用 Redis 后端(不得靠 ENVIRONMENT 隐式推断)。"""
    compose = _load_compose("docker-compose.collection.yml")
    environment = compose["services"]["collection"]["environment"]

    assert environment["ACCOUNT_SESSION_LOCK_BACKEND"] == (
        "${ACCOUNT_SESSION_LOCK_BACKEND:-redis}"
    )
    # Redis 连接信息必须齐全: URL 不带密码时由 REDIS_PASSWORD 注入
    assert "REDIS_URL" in environment
    assert "REDIS_PASSWORD" in environment


def test_collection_service_mounts_persistent_profiles() -> None:
    """采集服务必须把持久 profile 目录挂到宿主机。"""
    compose = _load_compose("docker-compose.collection.yml")
    volumes = compose["services"]["collection"]["volumes"]

    assert PROFILES_MOUNT in volumes


def test_prod_backend_services_declare_redis_lock_backend() -> None:
    """生产后端(API / 采集)必须**显式**使用 Redis 后端。"""
    compose = _load_compose("docker-compose.prod.yml")

    for service_name in ("backend-api", "backend-collector"):
        environment = compose["services"][service_name]["environment"]
        assert environment["ACCOUNT_SESSION_LOCK_BACKEND"] == (
            "${ACCOUNT_SESSION_LOCK_BACKEND:-redis}"
        ), service_name


def test_prod_backend_services_mount_persistent_profiles() -> None:
    """生产后端必须把持久 profile 目录挂到宿主机。"""
    compose = _load_compose("docker-compose.prod.yml")

    for service_name in ("backend-api", "backend-collector"):
        volumes = compose["services"][service_name]["volumes"]
        assert PROFILES_MOUNT in volumes, service_name
