#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台自动修复任务（可控开关 + 单实例锁）

为什么需要开关：
- .xls 修复依赖 Excel COM（Windows 桌面组件），耗时且不稳定
- 不应在 Web 服务启动阶段默认跑重任务

环境变量：
- AUTO_REPAIR_XLS_ON_STARTUP=true/false（默认 false）
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from modules.core.logger import get_logger

logger = get_logger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _acquire_lock(lock_path: Path, ttl_seconds: int = 2 * 60 * 60) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # stale lock cleanup (best-effort)
    try:
        if lock_path.exists():
            age = time.time() - lock_path.stat().st_mtime
            if age > ttl_seconds:
                lock_path.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
            f.write(f"ts={int(time.time())}\n")
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


async def auto_repair_all_xls_files() -> None:
    """
    异步触发 .xls 批量修复（在线程池中执行，不阻塞事件循环）。

    默认关闭：需要设置 AUTO_REPAIR_XLS_ON_STARTUP=true 才会执行。
    """
    if not _env_flag("AUTO_REPAIR_XLS_ON_STARTUP", default=False):
        logger.info("[AutoRepair] Disabled (set AUTO_REPAIR_XLS_ON_STARTUP=true to enable)")
        return

    from backend.services.file_repair import batch_repair_all_xls
    from modules.core.path_manager import get_data_raw_dir

    lock_path = get_data_raw_dir() / "repaired" / ".auto_repair.lock"
    if not _acquire_lock(lock_path):
        logger.info("[AutoRepair] Skip because another repair task is running")
        return

    logger.info("[AutoRepair] Starting background .xls repair task")

    def _run_repair() -> None:
        try:
            stats = batch_repair_all_xls(source_dir=None, file_pattern="*.xls")
            logger.info(
                f"[AutoRepair] Done: success={stats['success']}, failed={stats['failed']}, cached={stats['cached']}"
            )
        except Exception as e:
            logger.warning(f"[AutoRepair] Background task error: {e}")
        finally:
            _release_lock(lock_path)

    # delay a bit to avoid contending with startup (best-effort)
    try:
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        _release_lock(lock_path)
        return

    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _run_repair)
        logger.info("[AutoRepair] Background task submitted")
    except Exception as e:
        logger.debug(f"[AutoRepair] Failed to submit executor task: {e}")
        _release_lock(lock_path)


def register_auto_repair_task(app) -> None:
    """
    注册自动修复启动钩子（默认关闭，需 env 显式开启）。
    """

    @app.on_event("startup")
    async def startup_auto_repair() -> None:
        asyncio.create_task(auto_repair_all_xls_files())

