"""采集机上「云端连接串主机名规整」+ compose 传参的守护。

事故背景
--------
2026-11-07 的采集同步丢数事故里, 采集机一切正常, 云端停在 11-06 再也没动过 ——
「云端同步链路完整性巡检」本该报 ``partial_failed``, 但它**永远 skipped**:
采集机上的 celery 容器没有 ``CLOUD_DATABASE_URL``。

补上环境变量之后还有第二个坑
----------------------------
采集机的 ``.env`` 里 ``CLOUD_DATABASE_URL`` 指向 ``127.0.0.1:15433``,
那是**宿主机**上的 SSH 隧道。而**容器里的 ``127.0.0.1`` 是容器自己**,
原样透传必然 ``Connection refused``(实测: ``host.docker.internal:15433`` 才连得上)。

所以这里守两件事
--------------
1. **代码侧**: 主机名规整只有一个入口, 规则正确(口令不被破坏、幂等、
   关掉隧道时**明确说没改**);
2. **compose 侧**: worker 与 beat **都**拿到同一份配置, 且隧道落点默认**不是**
   回环地址(否则等于把上面那个坑固化进配置文件)。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from backend.tasks.cloud_sync_integrity_tasks import (
    CloudDatabaseUrlResolution,
    _resolve_cloud_database_url_from_env,
    _running_in_container,
    _tunnel_enabled_from_env,
    normalize_cloud_database_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.dev.yml"

#: compose 里必须成对出现、且取值必须一致的四个变量。
CLOUD_SYNC_ENV_KEYS = (
    "CLOUD_DATABASE_URL",
    "CLOUD_SYNC_TUNNEL_ENABLED",
    "CLOUD_SYNC_TUNNEL_HOST",
    "CLOUD_SYNC_TUNNEL_PORT",
)

#: 绝不能当隧道落点的地址(容器里指的是容器自己)。
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _read_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def _stub_container(monkeypatch, in_container: bool) -> None:
    """固定「当前进程是否在容器里」的判据。

    采集机上有**两种**运行环境, 对回环地址的解读相反:
    容器里 ``127.0.0.1`` 是容器自己(要重写); 宿主进程里它就是宿主自己(不能重写)。
    """
    monkeypatch.setattr(
        "backend.tasks.cloud_sync_integrity_tasks._running_in_container",
        lambda: in_container,
    )


def _compose_default(raw: str) -> str:
    """取 ``${VAR:-default}`` 里的 default 部分。

    取不到(写成了裸值)就原样返回 —— 那样也照样能判定它是不是回环地址。
    """
    text = str(raw).strip()
    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-(.*)\}", text)
    return match.group(1) if match else text


# ---------------------------------------------------------------------------
# ① 纯函数: 主机名规整
# ---------------------------------------------------------------------------


def test_loopback_host_is_rewritten_to_tunnel_host():
    """★ 回环地址必须被换成容器里真正可达的隧道落点。"""
    resolution = normalize_cloud_database_url(
        "postgresql://user:pass@127.0.0.1:15433/xihong_erp",
        tunnel_enabled=True,
    )

    assert resolution.rewritten is True
    assert resolution.reason == "rewritten_to_tunnel"
    assert resolution.original_host == "127.0.0.1"
    assert resolution.effective_host == "host.docker.internal"
    assert resolution.effective_port == 15433

    parsed = urlsplit(resolution.url)
    assert parsed.hostname == "host.docker.internal"
    assert parsed.port == 15433
    # 用户名 / 口令 / 库名原样保留
    assert parsed.username == "user"
    assert parsed.password == "pass"
    assert parsed.path == "/xihong_erp"
    assert parsed.scheme == "postgresql"


def test_localhost_is_rewritten_and_urlencoded_password_is_not_broken():
    """★ ``localhost`` 同样是回环; 且 URL 编码的口令绝不能被破坏。"""
    resolution = normalize_cloud_database_url(
        "postgresql+asyncpg://user:p%40ss@localhost:15433/db",
        tunnel_enabled=True,
    )

    assert resolution.rewritten is True
    parsed = urlsplit(resolution.url)
    assert parsed.hostname == "host.docker.internal"
    assert parsed.port == 15433
    # 驱动前缀原样保留
    assert parsed.scheme == "postgresql+asyncpg"
    # 口令仍是**编码态**的字面量, 没被解码、也没被拆坏
    assert parsed.password == "p%40ss"
    assert "p%40ss" in parsed.netloc
    assert parsed.netloc == "user:p%40ss@host.docker.internal:15433"
    assert parsed.path == "/db"


def test_already_rewritten_url_is_left_untouched():
    """★ 幂等: 已经是隧道落点就一个字都不动。"""
    url = "postgresql://user:pass@host.docker.internal:15433/db"
    resolution = normalize_cloud_database_url(url, tunnel_enabled=True)

    assert resolution.rewritten is False
    assert resolution.reason == "not_loopback_host"
    assert resolution.url == url


def test_real_host_is_left_untouched():
    """★ 非回环 host(真实 IP / 域名)原样保留。"""
    url = "postgresql://user:pass@10.0.0.5:5432/db"
    resolution = normalize_cloud_database_url(url, tunnel_enabled=True)

    assert resolution.rewritten is False
    assert resolution.reason == "not_loopback_host"
    assert resolution.url == url


def test_tunnel_disabled_means_no_rewrite():
    """★ 隧道显式关掉 ⇒ 不改, 并且**明确说没改**。"""
    url = "postgresql://user:pass@127.0.0.1:15433/xihong_erp"
    resolution = normalize_cloud_database_url(url, tunnel_enabled=False)

    assert resolution.rewritten is False
    assert resolution.reason == "tunnel_disabled"
    assert resolution.url == url
    assert resolution.original_host == "127.0.0.1"
    # 调用方必须能从摘要里看出「没有做重写」
    summary = resolution.to_summary_dict()
    assert summary["rewritten"] is False
    assert summary["reason"] == "tunnel_disabled"
    assert summary["effective_host"] == "127.0.0.1"


def test_ipv6_loopback_is_rewritten():
    """★ ``::1`` 也是回环地址。"""
    resolution = normalize_cloud_database_url(
        "postgresql://user:pass@[::1]:15433/db",
        tunnel_enabled=True,
    )

    assert resolution.rewritten is True
    assert resolution.original_host == "::1"
    assert urlsplit(resolution.url).hostname == "host.docker.internal"


def test_query_parameters_are_preserved():
    """★ 连接参数不能被规整过程吃掉。"""
    resolution = normalize_cloud_database_url(
        "postgresql://user:pass@127.0.0.1:15433/db?sslmode=require&connect_timeout=10",
        tunnel_enabled=True,
    )

    parsed = urlsplit(resolution.url)
    assert parsed.query == "sslmode=require&connect_timeout=10"
    assert parsed.path == "/db"


def test_custom_tunnel_host_and_port_are_honored():
    """★ 隧道落点可以由环境变量改。"""
    resolution = normalize_cloud_database_url(
        "postgresql://user:pass@127.0.0.1:15433/db",
        tunnel_enabled=True,
        tunnel_host="tunnel.internal",
        tunnel_port=25433,
    )

    assert resolution.rewritten is True
    parsed = urlsplit(resolution.url)
    assert parsed.hostname == "tunnel.internal"
    assert parsed.port == 25433


def test_unparsable_url_is_returned_untouched():
    """★ 畸形连接串不猜、不改, 交给上层报错。"""
    url = "postgresql://user:pass@127.0.0.1:notaport/db"
    resolution = normalize_cloud_database_url(url, tunnel_enabled=True)

    assert resolution.rewritten is False
    assert resolution.reason == "unparsable_url"
    assert resolution.url == url


# ---------------------------------------------------------------------------
# ② 环境变量接线
# ---------------------------------------------------------------------------


def test_tunnel_enabled_flag_is_only_disabled_explicitly():
    """★ 只有**显式**为假才算关掉; 未设置 => 开着。"""
    assert _tunnel_enabled_from_env(None) is True
    assert _tunnel_enabled_from_env("") is True
    assert _tunnel_enabled_from_env("true") is True
    assert _tunnel_enabled_from_env("1") is True
    assert _tunnel_enabled_from_env("false") is False
    assert _tunnel_enabled_from_env("FALSE") is False
    assert _tunnel_enabled_from_env("0") is False
    assert _tunnel_enabled_from_env("off") is False


def test_env_resolution_rewrites_loopback_url(monkeypatch):
    """★ 走真实环境变量接线: **在容器里**回环地址被重写。"""
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        "postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp",
    )
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_ENABLED", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_HOST", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_PORT", raising=False)
    _stub_container(monkeypatch, True)

    resolution = _resolve_cloud_database_url_from_env()

    assert resolution.rewritten is True
    assert resolution.effective_host == "host.docker.internal"
    assert resolution.effective_port == 15433


def test_env_resolution_does_not_rewrite_outside_container(monkeypatch):
    """★ **不在容器里**时回环地址原样保留 —— 别把宿主进程弄坏。

    采集机的云端同步 worker 跑在**宿主进程**
    (``scripts\\start_collection_formal.ps1``), 那里 ``127.0.0.1`` 就是宿主自己;
    ``host.docker.internal`` 这个名字**只在容器里有意义** ⇒ 宿主上重写反而连不上。
    """
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        "postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp",
    )
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_ENABLED", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_HOST", raising=False)
    monkeypatch.delenv("CLOUD_SYNC_TUNNEL_PORT", raising=False)
    _stub_container(monkeypatch, False)

    resolution = _resolve_cloud_database_url_from_env()

    assert resolution.rewritten is False
    assert resolution.reason == "not_in_container"
    assert resolution.url == ("postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp")


def test_running_in_container_returns_a_bool():
    """★ 容器判据本身必须是个确定的布尔, 不能抛异常。"""
    assert isinstance(_running_in_container(), bool)


def test_env_resolution_reports_when_tunnel_is_disabled(monkeypatch):
    """★ 隧道被显式关掉时, 结果里必须**看得见没做重写**。"""
    monkeypatch.setenv(
        "CLOUD_DATABASE_URL",
        "postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp",
    )
    monkeypatch.setenv("CLOUD_SYNC_TUNNEL_ENABLED", "false")
    _stub_container(monkeypatch, True)

    resolution = _resolve_cloud_database_url_from_env()

    assert resolution.rewritten is False
    assert resolution.reason == "tunnel_disabled"
    assert resolution.url == ("postgresql://erp_user:pass@127.0.0.1:15433/xihong_erp")


def test_resolution_summary_never_leaks_credentials():
    """★ 摘要进的是任务返回结果 / 日志, 绝不能带出口令。"""
    resolution = normalize_cloud_database_url(
        "postgresql://user:sup3rs3cr3t@127.0.0.1:15433/db",
        tunnel_enabled=True,
    )

    summary = resolution.to_summary_dict()
    assert "sup3rs3cr3t" not in str(summary)
    assert "user" not in str(summary)
    assert set(summary) == {
        "rewritten",
        "original_host",
        "effective_host",
        "effective_port",
        "reason",
    }


# ---------------------------------------------------------------------------
# ③ compose 守护: celery 必须拿到同一份云端配置
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service_name", ["celery-worker", "celery-beat"])
def test_celery_services_receive_cloud_database_url(service_name):
    """★ worker 与 beat 都必须能拿到 ``CLOUD_DATABASE_URL``。

    没有它, 云端巡检在采集机上永远是 ``skipped`` —— 2026-11-07 事故就是这么漏掉的。
    """
    services = _read_compose()["services"]

    assert service_name in services, f"{service_name} 必须存在于 compose"
    environment = services[service_name]["environment"]
    assert "CLOUD_DATABASE_URL" in environment, (
        f"{service_name} 缺 CLOUD_DATABASE_URL, 云端巡检会一直 skipped"
    )


@pytest.mark.parametrize("service_name", ["celery-worker", "celery-beat"])
def test_celery_tunnel_host_default_is_not_loopback(service_name):
    """★ 隧道落点默认**不得**是回环地址。

    容器里的 ``127.0.0.1`` 是容器自己 —— 把它写成默认值等于把「连不上」固化进配置。
    """
    services = _read_compose()["services"]
    environment = services[service_name]["environment"]

    raw_host = environment.get("CLOUD_SYNC_TUNNEL_HOST")
    assert raw_host, f"{service_name} 缺 CLOUD_SYNC_TUNNEL_HOST"
    default_host = _compose_default(raw_host)
    assert default_host.lower() not in LOOPBACK_HOSTS, (
        f"{service_name} 的 CLOUD_SYNC_TUNNEL_HOST 默认值不能是回环地址: {default_host}"
    )


def test_celery_worker_and_beat_cloud_settings_are_identical():
    """★ 两个 service 的云端配置必须**完全一致**。

    不一致 ⇒ worker 和 beat 看到的配置不同, 是极难排查的问题。
    """
    services = _read_compose()["services"]
    worker_env = services["celery-worker"]["environment"]
    beat_env = services["celery-beat"]["environment"]

    for key in CLOUD_SYNC_ENV_KEYS:
        assert key in worker_env, f"celery-worker 缺 {key}"
        assert key in beat_env, f"celery-beat 缺 {key}"
        assert worker_env[key] == beat_env[key], (
            f"{key} 在 celery-worker 与 celery-beat 里不一致: "
            f"{worker_env[key]!r} != {beat_env[key]!r}"
        )


def test_compose_cloud_database_url_default_is_empty():
    """★ ``CLOUD_DATABASE_URL`` 默认留空是有意的。

    compose 只负责把变量**传进去**; 主机名重写由代码负责
    (``normalize_cloud_database_url``)。默认给个非空值反而会掩盖配置缺失。
    """
    services = _read_compose()["services"]

    for service_name in ("celery-worker", "celery-beat"):
        environment = services[service_name]["environment"]
        assert _compose_default(environment["CLOUD_DATABASE_URL"]) == "", (
            f"{service_name} 的 CLOUD_DATABASE_URL 默认值应为空"
        )


def test_resolution_is_idempotent():
    """★ 规整结果再规整一次不会变形(第二遍必须是 no-op)。"""
    once = normalize_cloud_database_url(
        "postgresql://user:p%40ss@127.0.0.1:15433/db",
        tunnel_enabled=True,
    )
    twice = normalize_cloud_database_url(once.url, tunnel_enabled=True)

    assert twice.rewritten is False
    assert twice.url == once.url


def test_resolution_result_is_a_plain_value_object():
    """★ 返回的是可比较的值对象, 方便直接断言。"""
    resolution: CloudDatabaseUrlResolution = normalize_cloud_database_url(
        "postgresql://user:pass@127.0.0.1:15433/db",
        tunnel_enabled=True,
    )

    assert resolution.effective_host == "host.docker.internal"
    assert tuple(resolution)[:2] == (resolution.url, True)
