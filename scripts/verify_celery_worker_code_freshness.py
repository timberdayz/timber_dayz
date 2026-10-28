#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""校验 celery worker / beat 运行的代码是否与磁盘代码一致。

为什么需要这个脚本
------------------
容器是 bind-mount 挂载仓库代码的（``/app/backend`` -> 仓库 ``backend/``），
所以**改完代码磁盘上立刻就变了** —— 但 celery 是**常驻进程**,
Python 在**进程启动时**就把模块 import 进内存了, 之后再改磁盘上的文件,
运行中的 worker **不会**自动加载新代码。

真实事故(2026-10-28, 本地库实测)::

    第 1~3 批改造(模板契约 / 变体接管 / 状态语义)只存在于工作区, 没进过容器进程。
    磁盘上已有新代码, 但 celery worker 是 14 小时前启动的, 内存里跑的是旧模块。
    于是每 15 分钟 ``auto_ingest_pending_files`` 用**旧口径**重检,
    把 21 个真实文件的入库状态改回 ``template_update_required``,
    还把其中一个文件刚回填的模板契约整块抹掉。

判定方法
--------
比「容器内代码文件的最新 mtime」与「容器内进程的启动时间」:

* 代码比进程**新** => 进程跑的是旧代码 ⇒ **必须重启**
* 代码不比进程新 => 进程跑的是当前代码 => 正常

扫描范围是容器内 ``/app/backend`` 与 ``/app/modules`` 的**整棵 .py 代码树**
(排除测试目录), 而不是一份手工白名单。
手工白名单必然漂移 —— 2026-10-28 之后新增的服务文件若没登记进白名单,
就会再次出现「改了代码但进程没重启」而无人察觉。

退出码
------
* 0 = 全部新鲜(或容器未运行)
* 1 = 存在跑旧代码的进程
* 2 = 参数/环境问题

用法
----
::

    python scripts/verify_celery_worker_code_freshness.py
    python scripts/verify_celery_worker_code_freshness.py --container xihong_erp_celery_worker
    python scripts/verify_celery_worker_code_freshness.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

#: 默认检查的容器名(可用 --container 覆盖)
DEFAULT_CONTAINERS = (
    "xihong_erp_celery_worker",
    "xihong_erp_celery_beat",
)

#: 容器内参与比对的代码目录(相对容器工作目录 /app)
CODE_DIRS = ("/app/backend", "/app/modules")

#: 重点关注文件(相对 /app/backend)。它们承载「表头比对口径」,
#: 一旦变了, 旧进程给出的判定结论就不再可信。
#: 仅用于**报告重点**, 不参与新鲜度判定 —— 判定覆盖整棵代码树。
KEY_FILES = (
    "backend/services/data_sync_service.py",
    "backend/services/data_sync_template_status_service.py",
    "backend/services/template_contract_service.py",
    "backend/services/template_variant_takeover.py",
    "backend/services/template_variant_takeover_service.py",
    "backend/services/data_sync_status_semantics.py",
    "backend/services/cloud_sync_auto_recovery_service.py",
    "backend/tasks/scheduled_tasks.py",
    "backend/tasks/data_sync_tasks.py",
)

#: 判定时忽略的路径片段(测试代码不会被 celery worker 导入)
IGNORED_PATH_PARTS = ("/tests/", "/__pycache__/", "/.pytest_cache/")

#: 报告过期文件时最多列出的条数
MAX_REPORTED_STALE = 20


def safe_print(msg: str) -> None:
    """Windows 终端(GBK)下也不崩。"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("gbk", errors="ignore").decode("gbk"), flush=True)


@dataclass
class ContainerCheck:
    """单个容器的检查结果。"""

    name: str
    running: bool = False
    started_at: Optional[datetime] = None
    newest_code_at: Optional[datetime] = None
    stale_files: List[str] = field(default_factory=list)
    scanned_files: int = 0
    error: Optional[str] = None

    @property
    def is_stale(self) -> bool:
        """代码比进程新 => 进程跑的是旧代码。"""
        if not self.running:
            return False
        if self.started_at is None or self.newest_code_at is None:
            return False
        return self.newest_code_at > self.started_at


def _docker(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _parse_docker_time(raw: str) -> Optional[datetime]:
    """解析 docker 的时间输出(纳秒精度 ISO 串)。"""
    text = raw.strip()
    if not text:
        return None
    # docker 的 stat 格式形如: 2026-10-28 18:16:57.620949352 +0000
    head = text.split("+")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(head, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _is_ignored(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(part in normalized for part in IGNORED_PATH_PARTS)


def _scan_code_files(name: str) -> List[tuple]:
    """扫描容器内整棵代码树, 返回 [(mtime, 绝对路径), ...]。

    用 find -printf 一次性拿到全部 .py 的修改时间, 比逐文件 docker exec 快得多。
    """
    collected: List[tuple] = []
    for code_dir in CODE_DIRS:
        scan = _docker(
            [
                "exec",
                name,
                "find",
                code_dir,
                "-type",
                "f",
                "-name",
                "*.py",
                "-printf",
                "%T@ %p\n",
            ]
        )
        if scan.returncode != 0 and not scan.stdout:
            continue
        for line in (scan.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            head, _, path = line.partition(" ")
            try:
                mtime = datetime.fromtimestamp(float(head), tz=timezone.utc)
            except ValueError:
                continue
            if _is_ignored(path):
                continue
            collected.append((mtime, path))
    return collected


def check_container(name: str) -> ContainerCheck:
    """检查单个容器的代码新鲜度。"""
    result = ContainerCheck(name=name)

    running = _docker(["ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"])
    if running.returncode != 0:
        result.error = f"docker ps 失败: {(running.stderr or '').strip()}"
        return result
    if name not in (running.stdout or ""):
        # 容器没在跑 —— 不是「代码过期」, 而是「没在跑」
        return result

    result.running = True

    started = _docker(["inspect", name, "--format", "{{.State.StartedAt}}"])
    if started.returncode == 0:
        result.started_at = _parse_docker_time(started.stdout or "")
    else:
        result.error = f"docker inspect 失败: {(started.stderr or '').strip()}"

    files = _scan_code_files(name)
    result.scanned_files = len(files)

    newest: Optional[datetime] = None
    stale: List[str] = []
    for file_time, path in files:
        if newest is None or file_time > newest:
            newest = file_time
        if result.started_at is not None and file_time > result.started_at:
            stale.append(path)

    # 相对 /app 排序展示, 过期文件多的排前面
    stale.sort(key=lambda item: item)
    result.newest_code_at = newest
    result.stale_files = [path.replace("/app/", "", 1) for path in stale]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 celery 进程运行的代码是否与磁盘代码一致"
    )
    parser.add_argument(
        "--container",
        action="append",
        dest="containers",
        help="要检查的容器名(可重复指定)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果",
    )
    args = parser.parse_args()

    containers = args.containers or list(DEFAULT_CONTAINERS)
    checks = [check_container(name) for name in containers]
    stale = [c for c in checks if c.is_stale]

    if args.json:
        payload = {
            "checks": [
                {
                    "name": c.name,
                    "running": c.running,
                    "started_at": c.started_at.isoformat() if c.started_at else None,
                    "newest_code_at": (
                        c.newest_code_at.isoformat() if c.newest_code_at else None
                    ),
                    "stale": c.is_stale,
                    "stale_files": c.stale_files,
                    "scanned_files": c.scanned_files,
                    "error": c.error,
                }
                for c in checks
            ],
            "stale_containers": [c.name for c in stale],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1 if stale else 0

    safe_print("=" * 68)
    safe_print("celery 代码新鲜度检查")
    safe_print("=" * 68)

    for check in checks:
        if not check.running:
            safe_print(f"[SKIP] {check.name}: 容器未运行")
            if check.error:
                safe_print(f"       {check.error}")
            continue
        started = check.started_at.isoformat() if check.started_at else "未知"
        newest = check.newest_code_at.isoformat() if check.newest_code_at else "未知"
        if check.is_stale:
            safe_print(f"[STALE] {check.name}: 进程跑的是旧代码")
            safe_print(f"        进程启动: {started}")
            safe_print(f"        最新代码: {newest}")
            safe_print(f"        扫描文件: {check.scanned_files}")
            for name in check.stale_files[:MAX_REPORTED_STALE]:
                safe_print(f"        - {name}")
            if len(check.stale_files) > MAX_REPORTED_STALE:
                safe_print(f"        ... 另有 {len(check.stale_files) - MAX_REPORTED_STALE} 个过期文件")
        else:
            safe_print(f"[ OK ] {check.name}: 代码新鲜")
            safe_print(f"        进程启动: {started}")
            safe_print(f"        最新代码: {newest}")
            safe_print(f"        扫描文件: {check.scanned_files}")

    safe_print("=" * 68)
    if stale:
        safe_print(
            f"[FAIL] {len(stale)} 个容器跑的是旧代码。"
            "旧进程会用旧口径改写真实数据 —— 必须重启:"
        )
        for check in stale:
            safe_print(f"        docker restart {check.name}")
        return 1

    safe_print("[PASS] 所有运行中的 celery 容器代码都是最新的")
    return 0


if __name__ == "__main__":
    sys.exit(main())
