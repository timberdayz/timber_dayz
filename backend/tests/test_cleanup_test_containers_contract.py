"""Contract test for the test-container cleanup script (``scripts/cleanup_test_containers.py``).

Background:
    Integration tests spin up throw-away PostgreSQL containers through
    ``testcontainers``.  When the pytest process is **killed** (SIGKILL, CI
    timeout, background-task reaping) Python's ``atexit`` hooks never run and
    the containers plus their anonymous volumes stay behind in Docker.

    The cleanup script is the fixed entry point for that path.  It must stay
    deliberately narrow: it may only touch containers carrying the
    ``org.testcontainers`` label and volumes carrying the
    ``com.docker.volume.anonymous`` label, and it must never use ``prune`` --
    ``docker volume prune`` would also delete the project's named volumes
    (``xihong_erp_redis_data_dev``, ``docker_grafana-data``, ...) which hold
    real data.

    These tests lock that boundary in so a future refactor cannot silently
    widen it into deleting business data.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "cleanup_test_containers.py"

TESTCONTAINERS_LABEL = "org.testcontainers"
ANONYMOUS_VOLUME_LABEL = "com.docker.volume.anonymous"


class _FakeProc:
    """Minimal stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _load_module():
    spec = importlib.util.spec_from_file_location("cleanup_test_containers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_exists_and_is_syntactically_valid():
    assert SCRIPT.exists(), "清理脚本必须存在于 scripts/ 下"
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr


def test_protected_container_prefixes_cover_compose_services():
    """仓库自己的 compose 服务前缀必须在保护名单里。"""
    module = _load_module()
    assert "xihong_erp_" in module.PROTECTED_CONTAINER_PREFIXES


def test_dry_run_is_the_default_and_applies_nothing(monkeypatch):
    """默认(不加 ``--apply``)必须是只报告 —— 不得发出任何删除命令。"""
    module = _load_module()
    calls: List[Sequence[str]] = []

    def fake_run_docker(args, timeout=60):
        calls.append(list(args))
        return _FakeProc("", 0)

    monkeypatch.setattr(module, "run_docker", fake_run_docker)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_containers.py"])

    assert module.main() == 0

    destructive = [
        call for call in calls if call[:1] == ["rm"] or call[:2] == ["volume", "rm"]
    ]
    assert destructive == [], "dry-run 不得发出任何删除命令: {0}".format(destructive)


def test_apply_only_deletes_stopped_testcontainers_and_anonymous_volumes(monkeypatch):
    """``--apply`` 只允许删: 已停止的 testcontainers 容器 + 匿名卷。

    运行中的容器(别的会话可能在用)、仓库自己的 compose 服务、命名卷
    (业务持久化数据)一个都不能碰。
    """
    module = _load_module()

    containers = [
        ("leftover-postgres", "exited"),
        ("running-postgres", "running"),
        ("xihong_erp_postgres", "running"),
    ]
    anonymous_volumes = [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ]

    calls: List[Sequence[str]] = []

    def fake_run_docker(args, timeout=60):
        args = list(args)
        calls.append(args)
        if args[:1] == ["ps"] and args[1:2] == ["-a"]:
            if "volume=" in " ".join(args):
                return _FakeProc("", 0)  # 没有容器引用该卷
            rows = "".join(
                "{0}\t{1}\n".format(name, state) for name, state in containers
            )
            return _FakeProc(rows, 0)
        if args[:2] == ["volume", "ls"]:
            return _FakeProc("\n".join(anonymous_volumes) + "\n", 0)
        return _FakeProc("", 0)

    monkeypatch.setattr(module, "run_docker", fake_run_docker)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_containers.py", "--apply"])

    assert module.main() == 0

    removed_containers = [call[3] for call in calls if call[:3] == ["rm", "-f", "-v"]]
    removed_volumes = [call[2] for call in calls if call[:2] == ["volume", "rm"]]

    assert removed_containers == ["leftover-postgres"]
    assert removed_volumes == anonymous_volumes
    assert "running-postgres" not in removed_containers
    assert "xihong_erp_postgres" not in removed_containers


def test_script_never_prunes(monkeypatch):
    """绝不允许 prune —— prune 会连带删掉命名卷(业务数据)。"""
    module = _load_module()
    calls: List[Sequence[str]] = []

    def fake_run_docker(args, timeout=60):
        calls.append(list(args))
        return _FakeProc("", 0)

    monkeypatch.setattr(module, "run_docker", fake_run_docker)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_containers.py", "--apply"])

    module.main()

    for call in calls:
        assert "prune" not in call, "清理脚本不得使用 prune: {0}".format(call)


def test_listing_queries_are_label_scoped(monkeypatch):
    """容器与卷的查询都必须带 label 过滤 —— 否则会扫到业务资源。"""
    module = _load_module()
    calls: List[Sequence[str]] = []

    def fake_run_docker(args, timeout=60):
        calls.append(list(args))
        return _FakeProc("", 0)

    monkeypatch.setattr(module, "run_docker", fake_run_docker)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_containers.py"])

    module.main()

    listing_calls = [
        call for call in calls if call[:1] == ["ps"] or call[:2] == ["volume", "ls"]
    ]
    assert listing_calls, "应当至少发起一次列举命令"
    for call in listing_calls:
        if call[:2] == ["volume", "ls"]:
            assert any(TESTCONTAINERS_LABEL in str(a) for a in call) or any(
                ANONYMOUS_VOLUME_LABEL in str(a) for a in call
            ), "列举卷必须带标签过滤: {0}".format(call)


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="本机没有 docker, 跳过真实 dry-run"
)
def test_real_docker_dry_run_lists_nothing_to_delete_after_cleanup():
    """真实环境 dry-run: 清理完成后不应再报出待清理项。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert "命中 0 个" in proc.stdout or "命中" in proc.stdout
