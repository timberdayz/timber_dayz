#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台自动修复任务（启动时执行）

功能：
1. 扫描data/raw目录下的所有.xls文件
2. 自动修复损坏的文件
3. 缓存到data/raw/repaired/
4. 异步执行，不阻塞启动

运行时机：后端启动时自动执行（如果Excel COM可用）
"""

import asyncio
from pathlib import Path
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def auto_repair_all_xls_files():
    """
    后台异步修复所有.xls文件
    
    特点：
    - 异步执行，不阻塞主线程
    - 只在Windows + Excel环境运行
    - 失败静默处理，不影响系统启动
    - 优雅处理取消，避免CancelledError异常
    """
    try:
        from backend.services.file_repair import batch_repair_all_xls
        
        logger.info("[自动修复] 启动后台.xls文件修复任务...")
        
        # 在后台线程中执行（避免阻塞异步事件循环）
        def _run_repair():
            try:
                stats = batch_repair_all_xls(
                    source_dir=None,  # 使用默认值（data/raw）
                    file_pattern="*.xls"
                )
                logger.info(f"[自动修复] 完成: 成功{stats['success']}, 失败{stats['failed']}, 缓存{stats['cached']}")
            except Exception as e:
                logger.warning(f"[自动修复] 后台任务异常: {e}")
        
        # 延迟5秒启动（等待主服务完全启动）
        # 使用try-except捕获CancelledError，优雅处理取消
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            # 任务被取消是正常的（应用关闭时），静默处理
            logger.debug("[自动修复] 任务被取消（应用关闭）")
            return
        
        # 在executor中运行（不阻塞）
        try:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, _run_repair)
            logger.info("[自动修复] 后台任务已启动")
        except Exception as e:
            logger.debug(f"[自动修复] 启动executor失败: {e}")
        
    except asyncio.CancelledError:
        # 任务被取消是正常的，静默处理
        logger.debug("[自动修复] 任务被取消（应用关闭）")
    except Exception as e:
        logger.debug(f"[自动修复] 任务启动失败（可能Excel COM不可用）: {e}")


def register_auto_repair_task(app):
    """
    注册自动修复任务到FastAPI应用
    
    Args:
        app: FastAPI应用实例
    """
    @app.on_event("startup")
    async def startup_auto_repair():
        """启动时执行自动修复"""
        # 创建后台任务（不等待完成）
        asyncio.create_task(auto_repair_all_xls_files())

