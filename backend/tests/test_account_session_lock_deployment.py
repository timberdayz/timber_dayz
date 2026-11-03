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


def _environment_values(service: Dict[str, Any]) -> list:
    """取服务的环境变量值(兼容 dict / list 两种 compose 写法)。"""
    environment = service.get("environment") or {}
    if isinstance(environment, dict):
        return [str(value) for value in environment.values()]
    if isinstance(environment, list):
        return [str(item) for item in environment]
    return []


def _services_using_host_docker_internal(compose: Dict[str, Any]) -> list:
    """找出环境变量里出现 ``host.docker.internal`` 的服务。"""
    targets = []
    for name, service in (compose.get("services") or {}).items():
        if not isinstance(service, dict):
            continue
        if any("host.docker.internal" in value for value in _environment_values(service)):
            targets.append(name)
    return targets


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


# ---------------------------------------------------------------------------
# 评审 F4: host.docker.internal 在 Linux 上不解析 -> 锁静默降级为进程内锁
# ---------------------------------------------------------------------------


def test_collection_services_using_host_docker_internal_map_it_to_host_gateway() -> None:
    """用到 ``host.docker.internal`` 的服务必须显式映射到宿主网关。

    ``host.docker.internal`` 是 Docker Desktop(Win/macOS) 的特性, **Linux 宿主上
    根本不解析** → REDIS_URL 连不上 → 账号会话锁降级为进程内锁(只同进程互斥)
    → 同一主账号的 profile 目录仍可能被两个进程同时打开(违反 R6)。
    ``host-gateway`` 是 Docker 20.10+ 的内置 magic name, 在 Linux 上把
    ``host.docker.internal`` 指向宿主网关。
    """
    compose = _load_compose("docker-compose.collection.yml")
    services = compose["services"]

    targets = _services_using_host_docker_internal(compose)
    assert targets, "collection compose 里应当有用到 host.docker.internal 的服务"

    for service_name in targets:
        extra_hosts = services[service_name].get("extra_hosts") or []
        assert any(
            "host.docker.internal" in str(entry) and "host-gateway" in str(entry)
            for entry in extra_hosts
        ), (
            f"{service_name} 缺少 host.docker.internal -> host-gateway 的映射"
            "(Linux 上不解析 -> 账号会话锁会静默降级为进程内锁)"
        )


def test_prod_backend_services_map_host_docker_internal_to_host_gateway() -> None:
    """生产后端也补上同一条映射(防御性: 当前用内网服务名 redis:6379)。"""
    compose = _load_compose("docker-compose.prod.yml")

    for service_name in ("backend-api", "backend-collector"):
        extra_hosts = compose["services"][service_name].get("extra_hosts") or []
        assert any(
            "host.docker.internal" in str(entry) and "host-gateway" in str(entry)
            for entry in extra_hosts
        ), service_name


def test_collection_service_does_not_hardcode_production_environment() -> None:
    """``collection`` 服务不得把 ENVIRONMENT 写死成 production。

    这个 compose 同时用于开发(``up -d``)与生产(``--profile production up -d``):
    写死 production 会让**开发用法**在 Redis 不可达时从「降级继续跑」变成
    「拒绝采集」。fail-closed 的开关应交给 ``ACCOUNT_SESSION_LOCK_FAIL_CLOSED``
    由运维在生产侧显式设置。
    """
    compose = _load_compose("docker-compose.collection.yml")
    environment = compose["services"]["collection"]["environment"]

    value = str(environment.get("ENVIRONMENT", "")).strip().strip("\"'").lower()
    assert value != "production"


def test_collection_service_exposes_explicit_fail_closed_switch() -> None:
    """采集容器必须暴露 fail-closed 开关(生产侧显式打开)。"""
    compose = _load_compose("docker-compose.collection.yml")
    environment = compose["services"]["collection"]["environment"]

    assert "ACCOUNT_SESSION_LOCK_FAIL_CLOSED" in environment
