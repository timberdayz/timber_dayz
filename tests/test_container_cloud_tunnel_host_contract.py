#!/usr/bin/env python3
"""容器侧云端隧道地址的 compose 契约守护(纯 YAML, 不起容器)。

为什么要有这个守护
------------------
2026-11-11 v7.21.0 上线后, 采集机上的「云端同步链路完整性巡检」**第一次真跑**
就报了 ``cloud_sync_integrity_check_unreachable``:
``ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 15433)``。

根因不是云端挂了, 是**变量名被两个语义相反的运行环境共用**:

* **宿主进程**(``scripts/start_collection_formal.ps1`` 拉起的后端):
  SSH 隧道跑在本机 => ``127.0.0.1`` 就是宿主自己 => 隧道地址**该是** ``127.0.0.1``;
* **容器内**(``celery-worker`` / ``celery-beat`` / ``backend-collector``):
  ``127.0.0.1`` 是**容器自己** => 隧道地址**必须**是 ``host.docker.internal``。

compose 变量插值**优先取进程环境变量**, 而采集机的启动脚本会把
``.env.collection.local``(里面就是 ``CLOUD_SYNC_TUNNEL_HOST=127.0.0.1``)导入进程环境
=> 容器最终拿到 ``127.0.0.1`` => 容器里的巡检**永远**连不上云端。

后果比"连不上"更严重: 巡检会**恒定**报「云端不可达」=> 假警报每小时一次 =>
真信号(云端真停更)被淹掉 => 守卫等于没有。

守护的底线
----------
1. **容器侧必须是字面量** ``host.docker.internal`` —— 不能插值, 否则宿主进程
   的同名环境变量随时会把它改回 ``127.0.0.1``;
2. **宿主侧仍然是** ``127.0.0.1`` —— 容器里的 ``host.docker.internal`` 对宿主进程
   无意义, 那边靠「非容器内 => 不改写主机名」的代码分支兜底;
3. **生产不受影响** —— 生产上「云端」就是自己(``postgres``), 不是回环地址,
   压根不走隧道改写; 隧道开关默认关。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 采集机上「隧道宿主必须是容器可达地址」的 (compose 文件, service)。
CONTAINER_SERVICES = (
    ("docker-compose.dev.yml", "celery-worker"),
    ("docker-compose.dev.yml", "celery-beat"),
    ("docker-compose.collection-cloud-sync.yml", "backend-collector"),
)

#: 容器里隧道宿主的**唯一**正确取值。
EXPECTED_CONTAINER_TUNNEL_HOST = "host.docker.internal"


def _compose(name: str) -> dict:
    path = PROJECT_ROOT / name
    assert path.exists(), "compose 文件缺失: %s" % path
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _environment(compose_name: str, service: str) -> dict:
    services = _compose(compose_name).get("services") or {}
    assert service in services, "%s 里没有 service %s" % (compose_name, service)
    env = services[service].get("environment") or {}
    assert isinstance(env, dict), "%s/%s 的 environment 不是字典" % (
        compose_name,
        service,
    )
    return env


@pytest.mark.parametrize("compose_name,service", CONTAINER_SERVICES)
def test_container_tunnel_host_is_pinned_literal(
    compose_name: str, service: str
) -> None:
    """容器侧必须是**字面量** —— 插值会被宿主进程的环境变量改回 127.0.0.1。"""
    env = _environment(compose_name, service)
    missing = "CLOUD_SYNC_TUNNEL_HOST" not in env
    msg = "%s/%s 少了 CLOUD_SYNC_TUNNEL_HOST" % (compose_name, service)
    assert not missing, msg

    value = str(env["CLOUD_SYNC_TUNNEL_HOST"])
    interpolated = "${" in value
    msg = "%s/%s 的 CLOUD_SYNC_TUNNEL_HOST 不能插值(当前 %r) —— 宿主进程会把 127.0.0.1 带进容器" % (
        compose_name,
        service,
        value,
    )
    assert not interpolated, msg

    msg = "%s/%s 的 CLOUD_SYNC_TUNNEL_HOST 必须是 %s(当前 %r)" % (
        compose_name,
        service,
        EXPECTED_CONTAINER_TUNNEL_HOST,
        value,
    )
    assert value == EXPECTED_CONTAINER_TUNNEL_HOST, msg


@pytest.mark.parametrize("compose_name,service", CONTAINER_SERVICES)
def test_container_tunnel_is_enabled(compose_name: str, service: str) -> None:
    """容器侧隧道必须默认**开** —— 关掉就等于永远连不上云端。"""
    env = _environment(compose_name, service)
    missing = "CLOUD_SYNC_TUNNEL_ENABLED" not in env
    msg = "%s/%s 少了 CLOUD_SYNC_TUNNEL_ENABLED" % (compose_name, service)
    assert not missing, msg

    value = str(env["CLOUD_SYNC_TUNNEL_ENABLED"])
    msg = "%s/%s 的 CLOUD_SYNC_TUNNEL_ENABLED 必须默认开(当前 %r)" % (
        compose_name,
        service,
        value,
    )
    assert value.endswith(":-true}"), msg


def test_dev_worker_and_beat_share_the_same_tunnel_host() -> None:
    """worker 与 beat 必须一致 —— 否则一个跑一个跳。"""
    worker = _environment("docker-compose.dev.yml", "celery-worker")
    beat = _environment("docker-compose.dev.yml", "celery-beat")
    for key in (
        "CLOUD_SYNC_TUNNEL_HOST",
        "CLOUD_SYNC_TUNNEL_PORT",
        "CLOUD_SYNC_TUNNEL_ENABLED",
    ):
        msg = "dev 的 %s 在 worker 与 beat 里取值不同" % key
        assert str(worker[key]) == str(beat[key]), msg


def test_production_never_rewrites_to_the_container_tunnel_host() -> None:
    """生产上「云端」就是自己 => 隧道改写必须默认关, 且不得指向容器隧道宿主。

    生产的云端连接串主机名是 ``postgres``(容器网络地址, **非回环**)=> 代码走
    ``not_loopback_host`` 分支, 压根不改写主机名 => 隧道开关开不开都无所谓;
    但默认关掉更保险: 万一哪天有人把云端地址写成回环, 也不会被改到容器隧道宿主上。
    """
    for service in ("backend-collector", "celery-worker", "celery-beat"):
        env = _environment("docker-compose.prod.yml", service)
        enabled = str(env.get("CLOUD_SYNC_TUNNEL_ENABLED", ""))
        if enabled:
            msg = "prod/%s 的 CLOUD_SYNC_TUNNEL_ENABLED 必须默认关(当前 %r)" % (
                service,
                enabled,
            )
            assert enabled.endswith(":-false}"), msg

        host = str(env.get("CLOUD_SYNC_TUNNEL_HOST", ""))
        msg = "prod/%s 不该指向容器隧道宿主 %s" % (
            service,
            EXPECTED_CONTAINER_TUNNEL_HOST,
        )
        assert EXPECTED_CONTAINER_TUNNEL_HOST not in host, msg


def test_host_process_env_example_keeps_loopback_host() -> None:
    """宿主侧仍然是 127.0.0.1 —— 容器里的 host.docker.internal 对宿主无意义。"""
    text = (PROJECT_ROOT / "env.collection.local.example").read_text(encoding="utf-8")
    missing = "CLOUD_SYNC_TUNNEL_HOST=127.0.0.1" not in text
    msg = "env.collection.local.example 的宿主侧隧道地址必须是 127.0.0.1"
    assert not missing, msg
