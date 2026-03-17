"""
数据采集模块 API 路由 - 聚合入口

v4.21.0: 拆分为三个子模块以保持每文件 <= 15 个端点：
  - collection_config.py:   配置管理 + 账号 (6 endpoints)
  - collection_tasks.py:    任务管理 + 历史统计 (10 endpoints)
  - collection_schedule.py: 调度管理 + 健康检查 (6 endpoints)

本文件作为向后兼容的聚合入口，main.py 仍通过 collection.router 挂载。
"""

from fastapi import APIRouter

from backend.routers.collection_config import router as config_router
from backend.routers.collection_tasks import router as tasks_router
from backend.routers.collection_tasks import _execute_collection_task_background  # noqa: F401 backward compat
from backend.routers.collection_schedule import router as schedule_router

router = APIRouter(tags=["数据采集"])

router.include_router(config_router)
router.include_router(tasks_router)
router.include_router(schedule_router)
