#!/usr/bin/env python3
"""店铺身份「保未来」三件套在 **compose** 里的传递契约守护(纯 YAML, 不起容器)。

为什么守护 compose
------------------
环境变量配在 ``.env`` 里 ≠ 容器里读得到。
compose 只会把**显式声明**过的变量传进容器, 所以任何漏声明的 service
都会静默地用上「默认值」⇒ 看起来配了、其实没生效。

这三个键各自的失败后果不一样
---------------------------
* ``SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE``  —— 没传 ⇒ 语义层 unknown 全归
  「已知历史遗留」⇒ **巡检永远安静** ⇒ 「新增月份认不出」没人知道。
* ``SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD`` —— 没传 ⇒ 用默认 0.05,
  会放过「一个月只认不出 1~2 行」。
* ``SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`` —— 没传 ⇒ 矛盾行**没人通知**。

守护的底线
----------
1. **worker 与 beat 必须成对** —— 少一个就会出现「beat 调度了、worker 却跳过」;
2. **默认值必须为空** —— 空 = 未启用 = 不误报(宁可安静, 也不误报);
3. **同步侧必须拿到通知开关** —— 矛盾行通知由采集侧发起。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 店铺身份「保未来」三件套。
IDENTITY_ENV_KEYS = (
    "SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE",
    "SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD",
    "SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED",
)

#: 必须成对拿到三件套的 (compose 文件, service)。
CELERY_SERVICES = (
    ("docker-compose.dev.yml", "celery-worker"),
    ("docker-compose.dev.yml", "celery-beat"),
    ("docker-compose.prod.yml", "celery-worker"),
    ("docker-compose.prod.yml", "celery-beat"),
)

#: 同步侧 service —— 至少要拿到矛盾行通知开关。
SYNC_SERVICES = (
    ("docker-compose.collection-cloud-sync.yml", "backend-collector"),
    ("docker-compose.dev.yml", "backend-collector"),
)


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


@pytest.mark.parametrize("compose_name,service", CELERY_SERVICES)
def test_celery_services_receive_identity_env(compose_name: str, service: str) -> None:
    env = _environment(compose_name, service)
    missing = [key for key in IDENTITY_ENV_KEYS if key not in env]
    assert not missing, "%s/%s 少了店铺身份变量: %s" % (compose_name, service, missing)


@pytest.mark.parametrize("compose_name,service", CELERY_SERVICES)
def test_celery_services_default_to_disabled(compose_name: str, service: str) -> None:
    """默认值必须为空 —— 空 = 未启用 = 不会误报。"""
    env = _environment(compose_name, service)
    for key in IDENTITY_ENV_KEYS:
        value = str(env[key])
        assert value.endswith(":-}"), "%s/%s 的 %s 必须用空默认值(当前 %r)" % (
            compose_name,
            service,
            key,
            value,
        )


@pytest.mark.parametrize("compose_name,service", SYNC_SERVICES)
def test_sync_services_receive_conflict_notify_switch(
    compose_name: str, service: str
) -> None:
    env = _environment(compose_name, service)
    assert (
        "SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED" in env
    ), "%s/%s 没拿到矛盾行通知开关" % (compose_name, service)


def test_worker_and_beat_get_the_same_cloud_config() -> None:
    """worker 与 beat 的云端配置必须**完全一致**(否则一个跑一个跳)。"""
    for compose_name in ("docker-compose.dev.yml", "docker-compose.prod.yml"):
        worker = _environment(compose_name, "celery-worker")
        beat = _environment(compose_name, "celery-beat")
        assert "CLOUD_DATABASE_URL" in worker, (
            "%s/celery-worker 少了 CLOUD_DATABASE_URL" % compose_name
        )
        assert "CLOUD_DATABASE_URL" in beat, (
            "%s/celery-beat 少了 CLOUD_DATABASE_URL" % compose_name
        )
        # 生产上「云端」就是自己, 不走隧道 ⇒ 只要求**共有**的键取值一致。
        shared = [key for key in worker if key.startswith("CLOUD_") and key in beat]
        for key in shared:
            assert str(worker[key]) == str(
                beat[key]
            ), "%s 的 %s 在 worker 与 beat 里取值不同" % (compose_name, key)
