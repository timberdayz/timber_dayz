#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理测试期遗留的临时容器与匿名卷。

背景
----
集成测试用 ``testcontainers`` 起一次性 PostgreSQL 容器。若 pytest 进程被
**强杀**(SIGKILL / CI 超时 / 后台任务被回收), Python 的 ``atexit`` 钩子不会执行
⇒ 容器与它的匿名卷就留在 Docker 里。实测一次强杀会留下 2 个容器 + 30+ 个
悬空匿名卷, 而且会越积越多。

本脚本是这条路径的**固定收尾入口**, 幂等: 没残留时正常退出码 0。

安全边界(刻意收窄, 不做泛化清理)
----------------------------------
* 只动带 ``org.testcontainers`` 标签的容器 —— 仓库自己的 compose 服务
  (``xihong_erp_*``)一律不碰;
* **运行中**的容器一律跳过(可能是别的会话正在用);
* 只动带 ``com.docker.volume.anonymous`` 标签的卷 —— **命名卷**
  (``xihong_erp_redis_data_dev`` / ``docker_grafana-data`` 等业务持久化数据)
  永不触碰;
* 仍被任何容器引用的卷跳过(``docker volume rm`` 本来也会失败, 这里提前拦)。

用法
----
    python scripts/cleanup_test_containers.py            # 只报告, 不动手(默认)
    python scripts/cleanup_test_containers.py --apply    # 真正清理
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List, Optional, Tuple

TESTCONTAINER_LABEL = "org.testcontainers"
ANONYMOUS_VOLUME_LABEL = "com.docker.volume.anonymous"

#: 永远不碰的容器名前缀(仓库自己的 compose 服务)
PROTECTED_CONTAINER_PREFIXES = ("xihong_erp_",)


def run_docker(
    args: List[str], timeout: int = 60
) -> Optional[subprocess.CompletedProcess]:
    """执行 docker 命令; 失败返回 None(不抛, 便于汇总)。"""
    try:
        return subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        print("[SKIP] 未找到 docker 可执行文件, 跳过清理")
        return None
    except subprocess.TimeoutExpired:
        print("[ERROR] docker 命令超时: {0}".format(" ".join(args)))
        return None


def list_testcontainers() -> List[Tuple[str, str]]:
    """列出带 testcontainers 标签的容器: [(name, state)]。"""
    proc = run_docker(
        [
            "ps",
            "-a",
            "--filter",
            "label={0}".format(TESTCONTAINER_LABEL),
            "--format",
            "{{.Names}}\t{{.State}}",
        ]
    )
    if proc is None or proc.returncode != 0:
        return []
    rows: List[Tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        name = parts[0].strip()
        state = parts[1].strip() if len(parts) > 1 else ""
        if name:
            rows.append((name, state))
    return rows


def list_anonymous_volumes() -> List[str]:
    """列出带匿名卷标签的卷名。"""
    proc = run_docker(
        [
            "volume",
            "ls",
            "--filter",
            "label={0}".format(ANONYMOUS_VOLUME_LABEL),
            "--format",
            "{{.Name}}",
        ]
    )
    if proc is None or proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def volume_is_referenced(name: str) -> bool:
    """该卷是否仍被任何容器(含已停止的)引用。"""
    proc = run_docker(
        ["ps", "-a", "--filter", "volume={0}".format(name), "--format", "{{.ID}}"]
    )
    if proc is None:
        # 查不到就按"仍被引用"处理 —— 宁可不删, 也不误删
        return True
    return bool(proc.stdout.strip())


def remove_container(name: str) -> bool:
    """删除容器并连带删除它的匿名卷。"""
    proc = run_docker(["rm", "-f", "-v", name])
    return proc is not None and proc.returncode == 0


def remove_volume(name: str) -> bool:
    """删除卷。"""
    proc = run_docker(["volume", "rm", name])
    return proc is not None and proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清理测试期遗留的 testcontainers 容器与匿名卷(默认只报告)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行删除; 不加此参数只打印清单",
    )
    args = parser.parse_args()
    apply_changes = args.apply

    print("=" * 66)
    print(
        "清理模式: {0}".format(
            "执行删除 (--apply)" if apply_changes else "只报告 (dry-run)"
        )
    )
    print("=" * 66)

    containers = list_testcontainers()
    removable_containers = [
        (name, state)
        for name, state in containers
        if not name.startswith(PROTECTED_CONTAINER_PREFIXES)
    ]
    running = [(n, s) for n, s in removable_containers if s == "running"]
    stopped = [(n, s) for n, s in removable_containers if s != "running"]
    protected = [
        (n, s) for n, s in containers if n.startswith(PROTECTED_CONTAINER_PREFIXES)
    ]

    print("")
    print("[容器] testcontainers 标签命中 {0} 个".format(len(containers)))
    for name, state in protected:
        print("  [跳过-受保护] {0} ({1})".format(name, state))
    for name, state in running:
        print("  [跳过-运行中] {0} ({1}) —— 可能有别的会话正在用".format(name, state))
    for name, state in stopped:
        print("  [待清理] {0} ({1})".format(name, state))

    volumes = list_anonymous_volumes()
    referenced = [v for v in volumes if volume_is_referenced(v)]
    free = [v for v in volumes if v not in referenced]
    print("")
    print("[卷] 匿名卷标签命中 {0} 个".format(len(volumes)))
    for name in referenced:
        print("  [跳过-仍被引用] {0}".format(name))
    for name in free:
        print("  [待清理] {0}".format(name))
    print("  [说明] 命名卷(xihong_erp_* / docker_*)不在命中范围内, 永不触碰")

    if not apply_changes:
        print("")
        print("[提示] 以上为 dry-run; 确认无误后加 --apply 执行")
        print("总计: 容器 {0} 个 / 卷 {1} 个".format(len(stopped), len(free)))
        return 0

    removed_containers = 0
    failed_containers = 0
    for name, _state in stopped:
        if remove_container(name):
            removed_containers += 1
            print("[OK] 已删除容器 {0}".format(name))
        else:
            failed_containers += 1
            print("[FAIL] 删除容器失败 {0}".format(name))

    removed_volumes = 0
    failed_volumes = 0
    for name in free:
        if remove_volume(name):
            removed_volumes += 1
            print("[OK] 已删除卷 {0}".format(name))
        else:
            failed_volumes += 1
            print("[FAIL] 删除卷失败 {0}".format(name))

    print("")
    print(
        "清理完成: 容器 删除 {0} / 失败 {1}; 卷 删除 {2} / 失败 {3}".format(
            removed_containers, failed_containers, removed_volumes, failed_volumes
        )
    )
    return 0 if (failed_containers == 0 and failed_volumes == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
