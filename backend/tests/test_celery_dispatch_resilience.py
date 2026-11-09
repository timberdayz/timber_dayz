"""Celery 派发「不许把事件循环冻住」的契约测试。

事故现场(2026-11-09)
-------------------
``task.delay()`` 并不只是「把消息发到 broker」: Celery 在 ``send_task()`` 末尾
会回调 ``backend.on_task_call(producer, task_id)``, Redis 结果后端在这里
**同步订阅**该任务的 pubsub 通道 —— 于是**每次派发任务都要额外连一次 Redis**,
而且是**阻塞式**连接。

Redis 不可达时, kombu 的重试是**嵌套**的(外层 ``reconnect_on_error`` 套内层
``ensure()``, 各 20 次 × 1 秒), 实测单次 ``delay()`` 阻塞 **16~17 秒**才抛错。
放进 async 上下文, 这等于**整个事件循环被冻住** —— 表现就是「Redis 一抖,
整个 API 500」; 放进 pytest, 就是**整个测试会话静默挂死**(CPU 零增量)。

这里锁死三条契约:
1. 派发任务时**连接超时**有上限, 且**重试次数**有限(不得回退到 Celery 原生的
   20 次 / 100 次);
2. **不需要结果**的任务必须声明 ``ignore_result=True`` —— 从根上跳过那次
   多余的 pubsub 订阅;
3. 测试护栏把 Celery 钉成**内存 transport**, 测试永不连真实 Redis。

运行方式: ``pytest backend/tests/test_celery_dispatch_resilience.py``
"""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Celery 配置: 超时与重试必须有上限
# ---------------------------------------------------------------------------


def test_celery_publish_retry_policy_is_bounded():
    """派发任务的重试次数必须有上限。

    Celery 原生默认: ``task_publish_retry_policy = {max_retries: 3, ...}``,
    ``broker_connection_max_retries = 100``。后者对「派发一个可有可无的后台
    任务」是灾难 —— 它意味着「Redis 不在了就永远重试」。
    """
    from backend.celery_app import celery_app

    policy = celery_app.conf.task_publish_retry_policy or {}
    assert isinstance(policy, dict), policy
    assert policy.get("max_retries") is not None, "发布重试次数必须显式有上限"
    assert policy["max_retries"] <= 3, (
        f"发布重试次数过多(={policy['max_retries']}), "
        "Redis 不可达时会把调用方(或事件循环)阻塞十几秒"
    )


def test_celery_broker_connection_max_retries_is_bounded():
    """broker 建连重试次数必须有上限(Celery 原生默认 100)。"""
    from backend.celery_app import celery_app

    max_retries = celery_app.conf.broker_connection_max_retries
    assert max_retries is not None, "broker 建连重试次数必须显式有上限"
    assert max_retries <= 10, f"broker 建连重试次数过多(={max_retries})"


def test_celery_transport_options_declare_socket_connect_timeout():
    """broker / result backend 的传输层必须声明建连超时。

    没有 ``socket_connect_timeout`` 时, 建连会一直等到操作系统的 TCP 超时
    (Windows 默认可到 2 分钟), 期间调用方**完全无法响应**。
    """
    from backend.celery_app import celery_app

    for label, options in (
        ("broker_transport_options", celery_app.conf.broker_transport_options),
        (
            "result_backend_transport_options",
            celery_app.conf.result_backend_transport_options,
        ),
    ):
        assert isinstance(options, dict), f"{label} 必须显式配置"
        timeout = options.get("socket_connect_timeout")
        assert timeout is not None, f"{label} 缺少 socket_connect_timeout"
        assert 0 < float(timeout) <= 10, f"{label} 的 socket_connect_timeout 过大: {timeout}"


def test_celery_result_backend_retry_policy_is_bounded():
    """结果后端的重试次数必须有上限(Celery 原生默认 20 次 × 1 秒)。"""
    from backend.celery_app import celery_app

    options = celery_app.conf.result_backend_transport_options or {}
    policy = options.get("retry_policy") or {}
    assert policy.get("max_retries") is not None, "结果后端重试次数必须显式有上限"
    assert policy["max_retries"] <= 3, (
        f"结果后端重试次数过多(={policy['max_retries']})"
    )


# ---------------------------------------------------------------------------
# 2. 不需要结果的任务必须声明 ignore_result
# ---------------------------------------------------------------------------


def test_image_extraction_task_declares_ignore_result():
    """图片提取任务必须声明 ``ignore_result=True``。

    它的返回值**没有任何调用方读取**(调用方只关心「有没有派发出去」),
    所以声明「不关心结果」就能从根上跳过每次派发时那次多余的 Redis pubsub 订阅。

    历史事故: 少了这一行, 单次 ``delay()`` 阻塞 16~17 秒(嵌套重试),
    async 上下文里直接冻住整个事件循环。
    """
    from backend.tasks.image_extraction import extract_product_images_task

    assert extract_product_images_task.ignore_result is True, (
        "extract_product_images_task 必须声明 ignore_result=True: "
        "它的返回值无人读取, 而不声明会让每次派发都多连一次 Redis "
        "(Redis 不可达时阻塞 16~17 秒)"
    )


def test_no_dead_except_branch_after_broad_exception():
    """不许出现「先 ``except (ImportError, Exception)`` 再 ``except Exception``」。

    前者会吃掉所有异常, 使后者成为**死代码** —— 看起来有两套日志分支,
    实际只有一条生效。这是本批次在派发点实际发现的缺陷。
    """
    repo_root = Path(__file__).resolve().parents[2]
    targets = [
        repo_root / "backend" / "services" / "data_ingestion_service.py",
        repo_root
        / "backend"
        / "domains"
        / "data_platform"
        / "routers"
        / "field_mapping_ingest.py",
    ]

    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        handlers: list[tuple[str, list[str]]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                exc = handler.type
                if exc is None:
                    names = ["BaseException"]
                elif isinstance(exc, ast.Tuple):
                    names = [
                        e.id for e in exc.elts if isinstance(e, ast.Name)
                    ]
                elif isinstance(exc, ast.Name):
                    names = [exc.id]
                else:
                    names = ["<expr>"]
                handlers.append((getattr(handler, "lineno", 0), names))

        for idx, (lineno, names) in enumerate(handlers[:-1]):
            # Exception 出现在元组里 = 广捕获, 后面再跟任何 except 都是死代码
            if "Exception" in names and len(names) > 1:
                nxt_lineno, nxt_names = handlers[idx + 1]
                assert not any(
                    "Exception" in n for n in nxt_names
                ), (
                    f"{path.name}:{lineno} 的 `except ({', '.join(names)})` "
                    f"会吃掉所有异常, 使 line {nxt_lineno} 的 except 成为死代码"
                )


# ---------------------------------------------------------------------------
# 3. 测试护栏: Celery 必须是内存 transport
# ---------------------------------------------------------------------------


def test_conftest_pins_celery_to_memory_transport():
    """测试护栏必须把 Celery 钉成内存 transport。

    否则测试会回落到 ``redis://localhost:6379/0``(本机无人监听),
    于是走进上面那条「连不上 -> 无限重试」路径, 把整个测试会话拖死。
    """
    conftest = Path(__file__).resolve().parent / "conftest.py"
    source = conftest.read_text(encoding="utf-8-sig")

    assert 'os.environ["CELERY_BROKER_URL"] = "memory://"' in source, (
        "conftest 必须把 CELERY_BROKER_URL 钉成 memory://"
    )
    assert 'os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"' in source, (
        "conftest 必须把 CELERY_RESULT_BACKEND 钉成 cache+memory://"
    )


def test_test_env_guard_protects_celery_urls_from_dotenv_override():
    """``.env`` 不能把测试护栏的 Celery 内存配置覆盖回真实 Redis。

    仓库根 ``.env`` 里有真实的 Redis 地址; 若允许它覆盖, 护栏形同虚设。
    """
    from backend.utils.project_env import GUARDED_ENV_KEYS

    assert "CELERY_BROKER_URL" in GUARDED_ENV_KEYS, (
        "CELERY_BROKER_URL 必须在护栏保护名单里, 否则 .env 会覆盖掉测试护栏"
    )
    assert "CELERY_RESULT_BACKEND" in GUARDED_ENV_KEYS, (
        "CELERY_RESULT_BACKEND 必须在护栏保护名单里, 否则 .env 会覆盖掉测试护栏"
    )


# ---------------------------------------------------------------------------
# 4. 行为验证: 内存 broker 下派发必须立刻返回
# ---------------------------------------------------------------------------


def test_delay_returns_immediately_with_memory_broker():
    """内存 broker 下派发任务必须**立刻**返回(毫秒级)。

    这是「测试会话不会被拖死」的行为级保证 —— 不依赖任何超时参数,
    纯粹因为压根没连任何外部服务。
    """
    from backend.celery_app import celery_app

    @celery_app.task(name="mcode.test.dispatch_probe")
    def _probe() -> str:
        return "ok"

    started = time.perf_counter()
    _probe.delay()
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, (
        f"内存 broker 下派发仍耗时 {elapsed:.2f}s —— "
        "说明测试仍在连外部 Redis, 护栏失效"
    )


def test_memory_broker_does_not_open_any_socket(monkeypatch):
    """派发任务时不得建立任何 TCP 连接(护栏的硬保证)。"""
    import socket

    real_connect = socket.socket.connect
    attempts: list = []

    def _tracking_connect(self, address):
        attempts.append(address)
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", _tracking_connect)

    from backend.celery_app import celery_app

    @celery_app.task(name="mcode.test.no_socket_probe")
    def _probe() -> str:
        return "ok"

    _probe.delay()

    assert not attempts, (
        f"派发任务时建立了 TCP 连接: {attempts} —— "
        "测试护栏必须保证 Celery 走内存 transport"
    )
