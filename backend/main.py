"""
FastAPI后端服务 - 西虹ERP系统API
现代化RESTful API设计,支持跨境电商数据管理

混合架构设计:
- 统一API入口
- 调用modules/业务模块
- 前后端完全分离
"""

import sys
import os
from pathlib import Path

# [*] 注意(2025-12-21):
# Windows 上 Playwright 需要 ProactorEventLoop(默认),因为需要 create_subprocess_exec
# SelectorEventLoop 不支持 subprocess,会导致 NotImplementedError
# 所以不要设置 WindowsSelectorEventLoopPolicy

# 添加项目根目录到Python路径(支持modules导入)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件(从项目根目录)
from dotenv import load_dotenv

load_dotenv(dotenv_path=project_root / ".env")


def _load_app_version() -> str:
    for env_name in ("APP_VERSION", "IMAGE_TAG", "RELEASE_VERSION"):
        candidate = os.getenv(env_name, "").strip()
        if candidate:
            return candidate

    version_file = project_root / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version

    return "dev"


from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from backend.middleware.performance_logging import PerformanceLoggingMiddleware
from backend.middleware.request_id import RequestIDMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import logging
import asyncio  # v4.3.3新增:支持后台任务
from typing import List, Optional

# 导入路由(全部启用 - v4.1.0优化后)
# Legacy cleanup notes for previously removed dashboard APIs.
from backend.routers import (
    permissions,  # v4.20.0: 权限树API
    permission,  # v4.20.0: 权限列表API
    collection,
    management,
    # accounts,  # v4.18.0: 已删除,使用account_management替代
    field_mapping,
    field_mapping_dictionary,  # v4.3.7: 字段映射辞典API
    auto_ingest,  # v4.5.0: 自动入库API(v4.12.0标记为废弃,使用data_sync替代)
    data_sync,  # v4.12.0: 数据同步API(新统一入口)
    data_sync_mapping_quality,  # v4.13.0: 字段映射质量评分API
    data_quarantine,  # v4.6.0: 数据隔离区API
    data_quality,  # C类数据核心字段优化计划: 数据质量监控API
    config_management,  # Phase 3: A类数据管理API(销售目标、战役目标、经营成本)
    dashboard_api_postgresql,  # PostgreSQL-first dashboard API
    data_pipeline,  # PostgreSQL dashboard pipeline observability API
    hr_management,  # Phase 3: HR管理API(员工管理、员工目标、考勤记录、绩效查询)
    test_api,
    inventory_domain,
    inventory_overview,
    # finance,  # v4.17.0: 已删除(财务域表已删除,API路由已移除)
    auth,
    users,
    roles,
    notifications,  # v4.19.0: 系统通知API
    performance,
    system,  # v4.3.5: 系统配置API
    system_logs,  # v4.20.0: 系统日志API
    security,  # v4.20.0: 安全设置API
    backup,  # v4.20.0: 数据备份与恢复API
    maintenance,  # v4.20.0: 系统维护API
    notification_config,  # v4.20.0: 通知配置API
    account_alignment,  # v4.3.6: 账号对齐API
    # procurement,  # v4.17.0: 已删除(财务域表已删除,API路由已移除)
    # [WARN] v4.12.0移除:旧数据浏览器API已移除
    # data_browser,  # v4.7.0: 数据库浏览器API
    sales_campaign,  # v4.11.0: 销售战役管理API
    target_management,  # v4.11.0: 目标管理API
    expense_management,  # v4.21.0: 费用管理API
    performance_management,  # v4.11.0: 绩效管理API
    raw_layer,  # v4.11.5: 原始数据层查看API
    raw_layer_export,  # v4.13.1: 丢失数据导出API
    data_flow,  # v4.11.5: 数据流转追踪API
    data_consistency,  # v4.11.5: 数据一致性验证API
    database_design_validator,  # [*] v4.12.0新增:数据库设计规范验证API
    mv,  # [*] v4.12.0修复:物化视图管理API(修复刷新功能)
    component_recorder,  # [*] Phase 8.1: UI化组件录制工具API
    rate_limit,  # [*] v4.19.2: 限流管理API
    data_migration,  # v5.0.0: 数据迁移API
    task_center,  # task center unified read APIs
)
from backend.routers import rate_limit_config  # [*] v4.19.4: 限流配置管理API(Phase 3)
from backend.routers import cloud_sync as cloud_sync_router
from backend.models.database import init_db, get_db
from backend.utils.config import get_settings
from modules.core.logger import get_logger
from backend.services.cloud_b_class_auto_sync_factory import (
    build_cloud_sync_runtime_from_env,
)
from backend.services.system_role_service import ensure_system_roles
from backend.utils.postgres_path import auto_configure_postgres_path
from modules.utils.sessions.legacy_shop_artifact_cleanup import (
    collect_legacy_shop_artifacts_for_active_shops,
)
from sqlalchemy.orm import Session

# 设置日志
logger = get_logger(__name__)

# 获取配置
settings = get_settings()
APP_VERSION = _load_app_version()

# 安全认证
security = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理(v4.1.0优化版 - 完整启动)"""
    import time
    from backend.models.database import engine, warm_up_pool
    from sqlalchemy import text

    # 启动性能监控
    startup_metrics = {
        "postgres_path": 0,
        "postgres_connect": 0,
        "table_init": 0,
        "pool_warmup": 0,
        "total": 0,
    }

    # 后台任务列表(用于关闭时正确取消)
    background_tasks = []
    app.state.cloud_sync_runtime = None

    startup_start = time.time()
    logger.info("[启动] 西虹ERP系统后端服务启动中...")

    # 环境标识
    env_mode = os.getenv("ENVIRONMENT", "development")
    logger.info(f"[环境] 运行环境: {env_mode}")
    if env_mode == "production":
        logger.info("[安全] 生产环境模式:安全检查已启用")
    else:
        logger.info("[开发] 开发环境模式:使用默认配置")

    try:
        # 1. 环境配置(<1秒)
        step_start = time.time()
        postgres_path_configured = auto_configure_postgres_path(emit_output=False)
        startup_metrics["postgres_path"] = time.time() - step_start
        if postgres_path_configured:
            logger.info(
                f"[OK] PostgreSQL客户端PATH配置完成 ({startup_metrics['postgres_path']:.2f}秒)"
            )
        else:
            logger.info(
                f"[SKIP] PostgreSQL客户端工具未找到，跳过PATH配置 ({startup_metrics['postgres_path']:.2f}秒)"
            )

        # 2. 数据库连接验证(<2秒)
        step_start = time.time()
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            startup_metrics["postgres_connect"] = time.time() - step_start
            logger.info(
                f"[OK] 数据库连接验证成功 ({startup_metrics['postgres_connect']:.2f}秒)"
            )
        except Exception as e:
            startup_metrics["postgres_connect"] = time.time() - step_start
            logger.error(f"[ERROR] 数据库连接失败: {e}")
            raise

        try:
            legacy_artifacts = collect_legacy_shop_artifacts_for_active_shops(
                project_root,
                settings.DATABASE_URL,
            )
            if legacy_artifacts:
                logger.warning(
                    "[WARNING] 检测到 %s 个店铺级会话历史残留；当前运行不会使用它们，但建议清理",
                    len(legacy_artifacts),
                )
                for artifact in legacy_artifacts[:10]:
                    logger.warning("[WARNING] legacy shop artifact: %s", artifact)
                if len(legacy_artifacts) > 10:
                    logger.warning(
                        "[WARNING] ... 其余 %s 个路径已省略",
                        len(legacy_artifacts) - 10,
                    )
        except Exception as legacy_artifact_error:
            logger.warning(
                "[WARNING] 遗留店铺会话残留检查失败: %s",
                legacy_artifact_error,
            )

        # 3. 数据库表验证(<3秒)
        # [SCHEMA MIGRATION] 生产环境:只验证,不创建;开发环境:可以使用 init_db()
        step_start = time.time()
        try:
            if settings.ENVIRONMENT == "production":
                # 生产环境:验证表结构完整性,不创建表
                from backend.models.database import verify_schema_completeness

                result = verify_schema_completeness()

                if not result["all_tables_exist"]:
                    missing_tables = result["missing_tables"][:10]
                    logger.error(
                        f"[ERROR] 生产环境表结构不完整！缺失表 ({len(result['missing_tables'])} 张): "
                        f"{', '.join(missing_tables)}"
                    )
                    if len(result["missing_tables"]) > 10:
                        logger.error(
                            f"[ERROR] ... 还有 {len(result['missing_tables']) - 10} 张表缺失"
                        )
                    logger.error("[ERROR] 请运行: alembic upgrade heads")
                    raise RuntimeError(
                        f"Schema incompleteness: {len(result['missing_tables'])} tables missing"
                    )

                if not result.get("all_critical_columns_exist", True):
                    missing_columns = result.get("missing_columns", [])[:10]
                    logger.error(
                        f"[ERROR] 生产环境关键列缺失({len(result.get('missing_columns', []))} 列): "
                        f"{', '.join(missing_columns)}"
                    )
                    if len(result.get("missing_columns", [])) > 10:
                        logger.error(
                            f"[ERROR] ... 还有 {len(result['missing_columns']) - 10} 个关键列缺失"
                        )
                    logger.error("[ERROR] 请运行: alembic upgrade heads")
                    raise RuntimeError(
                        f"Schema missing critical columns: {len(result.get('missing_columns', []))}"
                    )

                if result["migration_status"] not in ["up_to_date", "not_initialized"]:
                    logger.error(
                        f"[ERROR] Alembic 迁移状态异常: {result['migration_status']}"
                    )
                    logger.error(
                        f"[ERROR] 当前版本: {result.get('current_revision', 'N/A')}"
                    )
                    logger.error(
                        f"[ERROR] 最新版本: {result.get('head_revision', 'N/A')}"
                    )
                    logger.error("[ERROR] 请运行: alembic upgrade heads")
                    raise RuntimeError(
                        f"Migration status invalid: {result['migration_status']}"
                    )

                startup_metrics["table_init"] = time.time() - step_start
                logger.info(
                    f"[OK] 数据库表验证通过 ({result['actual_table_count']} 张表, "
                    f"{startup_metrics['table_init']:.2f}秒)"
                )
            else:
                # 开发环境:可以使用 init_db(),但记录警告
                init_db()
                startup_metrics["table_init"] = time.time() - step_start
                logger.info(
                    f"[OK] 数据库表初始化完成(开发模式) ({startup_metrics['table_init']:.2f}秒)"
                )
        except Exception as e:
            startup_metrics["table_init"] = time.time() - step_start
            if settings.ENVIRONMENT == "production":
                # 生产环境必须失败,不继续启动
                logger.error(f"[ERROR] 数据库验证失败: {e}")
                raise
            else:
                # 开发环境:仅警告
                logger.warning(f"[WARN] 数据库表初始化部分失败: {e}")

        try:
            from backend.models.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                created_role_codes = await ensure_system_roles(session)

            if created_role_codes:
                logger.info("[OK] 系统角色补齐完成: %s", ", ".join(created_role_codes))
            else:
                logger.info("[OK] 系统角色已完整，无需补齐")
        except Exception as role_seed_error:
            logger.error(f"[ERROR] 系统角色补齐失败: {role_seed_error}")
            raise

        # 4. 连接池预热(<2秒)
        step_start = time.time()
        try:
            dashboard_bootstrap_completed = False
            from backend.models.database import AsyncSessionLocal
            from backend.services.data_pipeline.dashboard_bootstrap import (
                bootstrap_dashboard_assets_if_needed,
            )

            async with AsyncSessionLocal() as session:
                dashboard_bootstrap_report = await bootstrap_dashboard_assets_if_needed(
                    session
                )
                await session.commit()
            startup_metrics["dashboard_bootstrap"] = time.time() - step_start
            if dashboard_bootstrap_report.get("bootstrapped"):
                logger.info(
                    "[OK] PostgreSQL Dashboard 资产已自动初始化 "
                    f"({startup_metrics['dashboard_bootstrap']:.2f}秒, run_id={dashboard_bootstrap_report.get('run_id')})"
                )
            else:
                logger.info(
                    "[OK] PostgreSQL Dashboard 资产已就绪 "
                    f"({startup_metrics['dashboard_bootstrap']:.2f}秒)"
                )

            dashboard_bootstrap_completed = True
            warm_pool_target = max(1, min(2, settings.DB_POOL_SIZE))
            warm_up_pool(pool_size=warm_pool_target)
            startup_metrics["pool_warmup"] = time.time() - step_start
            logger.info(f"[OK] 连接池预热完成 ({startup_metrics['pool_warmup']:.2f}秒)")
        except Exception as e:
            if not dashboard_bootstrap_completed:
                startup_metrics["dashboard_bootstrap"] = time.time() - step_start
                logger.error(f"[ERROR] PostgreSQL Dashboard 资产初始化失败: {e}")
                raise
            startup_metrics["pool_warmup"] = time.time() - step_start
            logger.warning(f"[WARN] 连接池预热失败: {e}")

        startup_metrics["total"] = time.time() - startup_start

        logger.info(
            f"""
╔══════════════════════════════════════════════════════════╗
║          西虹ERP系统启动完成 - 性能报告                  ║
╠══════════════════════════════════════════════════════════╣
║  PostgreSQL客户端PATH: {startup_metrics['postgres_path']:>6.2f}秒                    ║
║  数据库连接验证:     {startup_metrics['postgres_connect']:>6.2f}秒                      ║
║  数据库表初始化:     {startup_metrics['table_init']:>6.2f}秒                      ║
║  连接池预热:         {startup_metrics['pool_warmup']:>6.2f}秒                      ║
╠══════════════════════════════════════════════════════════╣
║  总启动时间:         {startup_metrics['total']:>6.2f}秒                      ║
║  已注册路由:         {len(app.routes):>6}个                       ║
╚══════════════════════════════════════════════════════════╝
        """
        )

        # [*] v4.3.3新增:启动后台自动修复任务(零手动干预)
        # v4.12.0修复:正确管理后台任务,避免关闭时的CancelledError
        try:
            from backend.tasks.auto_repair_files import auto_repair_all_xls_files

            repair_task = asyncio.create_task(auto_repair_all_xls_files())
            background_tasks.append(repair_task)
            logger.info("[OK] 后台自动修复任务已启动")
        except Exception as repair_err:
            logger.debug(f"[SKIP] 后台修复任务未启动: {repair_err}")

        # v4.6.3新增:初始化Redis缓存(可选,不影响主流程)
        try:
            cloud_sync_runtime = build_cloud_sync_runtime_from_env()
            app.state.cloud_sync_runtime = cloud_sync_runtime
            if cloud_sync_runtime is None:
                logger.info("[CloudSync] Cloud sync worker not enabled")
            else:
                started = await cloud_sync_runtime.start()
                if started:
                    logger.info("[CloudSync] Cloud sync worker started")
                else:
                    logger.warning(
                        "[CloudSync] Cloud sync worker not started because runtime is not configured"
                    )
        except Exception as cloud_sync_err:
            logger.error(
                f"[CloudSync] Failed to start cloud sync worker: {cloud_sync_err}"
            )
            raise

        try:
            from backend.utils.redis_client import init_redis

            redis_client = await init_redis(app)

            # [*] Phase 3: 初始化统一缓存服务
            if redis_client:
                from backend.services.cache_service import get_cache_service

                cache_service = get_cache_service(redis_client=redis_client)
                app.state.cache_service = cache_service
                logger.info("[OK] 统一缓存服务已启用")
                # [*] 4c8g 单机优化: 可选启动后缓存预热（不阻塞启动）
                if os.getenv(
                    "POSTGRESQL_DASHBOARD_CACHE_WARMUP_ENABLED", ""
                ).lower() in ("true", "1", "yes"):
                    delay_sec = int(
                        os.getenv(
                            "POSTGRESQL_DASHBOARD_CACHE_WARMUP_DELAY_SECONDS", "10"
                        )
                    )

                    async def _warmup_after_startup():
                        await asyncio.sleep(delay_sec)
                        try:
                            from backend.services.cache_warmup_service import (
                                run_dashboard_cache_warmup,
                            )

                            result = await run_dashboard_cache_warmup()
                            logger.info(f"[CacheWarmup] 启动预热结果: {result}")
                        except Exception as warmup_err:
                            logger.warning(
                                f"[CacheWarmup] 启动预热异常(不阻塞): {warmup_err}",
                                exc_info=True,
                            )

                    asyncio.create_task(_warmup_after_startup())
                    logger.info(
                        f"[CacheWarmup] 已调度 PostgreSQL Dashboard 启动后预热(延迟 {delay_sec}s)"
                    )
        except Exception as redis_err:
            logger.debug(f"[SKIP] Redis缓存未启用: {redis_err}")

        # v4.19.0新增:初始化执行器管理器
        try:
            from backend.services.executor_manager import get_executor_manager

            executor_manager = get_executor_manager()
            app.state.executor_manager = (
                executor_manager  # 可选:存储在app.state便于监控和调试
            )
            logger.info("[ExecutorManager] 执行器管理器已初始化")
        except Exception as executor_err:
            logger.warning(
                f"[ExecutorManager] 初始化失败(不影响主功能): {executor_err}"
            )

        # v4.19.0新增:启动资源监控服务(可选,P2功能)
        try:
            from backend.services.resource_monitor import get_resource_monitor

            resource_monitor = get_resource_monitor()
            await resource_monitor.start()
            app.state.resource_monitor = (
                resource_monitor  # 存储在app.state便于关闭时停止
            )
            logger.info("[ResourceMonitor] 资源监控服务已启动")
        except Exception as monitor_err:
            logger.warning(f"[ResourceMonitor] 启动失败(不影响主功能): {monitor_err}")

        # v4.19.0新增:启动通知WebSocket清理任务
        try:
            from backend.routers.notification_websocket import start_cleanup_task

            cleanup_task = await start_cleanup_task()
            if cleanup_task:
                background_tasks.append(cleanup_task)
                logger.info("[WS] 通知WebSocket清理任务已启动")
        except Exception as ws_err:
            logger.warning(f"[WS] WebSocket清理任务启动失败(不影响主功能): {ws_err}")

        # [*] v4.19.5 新增:检查限流器存储连接
        try:
            from backend.middleware.rate_limiter import check_redis_connection, limiter

            if limiter and limiter.enabled:
                storage_uri = getattr(limiter, "storage_uri", "memory://")
                if storage_uri.startswith("redis://"):
                    redis_ok = await check_redis_connection()
                    if redis_ok:
                        logger.info("[RateLimit] Redis 存储连接正常")
                    else:
                        logger.warning(
                            "[RateLimit] Redis 存储连接失败,限流器可能降级到内存模式"
                        )
                else:
                    logger.info(f"[RateLimit] 使用内存存储(storage_uri={storage_uri})")
        except Exception as rate_limit_err:
            logger.warning(
                f"[RateLimit] 存储连接检查失败(不影响主功能): {rate_limit_err}"
            )

        # v4.7.0新增:标记中断的采集任务并初始化调度器
        try:
            from backend.services.task_service import TaskService
            from backend.services.collection_scheduler import (
                CollectionScheduler,
                APSCHEDULER_AVAILABLE,
            )
            from backend.models.database import SessionLocal
            import asyncio

            # [*] v4.18.2修复:使用run_in_executor包装同步数据库操作
            def _sync_mark_interrupted_tasks():
                """同步标记中断任务(在线程池中执行)"""
                db = SessionLocal()
                try:
                    task_service = TaskService(db)
                    return task_service.mark_interrupted_tasks()
                finally:
                    db.close()

            # 标记服务重启前运行中的任务为中断
            loop = asyncio.get_running_loop()
            interrupted_count = await loop.run_in_executor(
                None, _sync_mark_interrupted_tasks
            )
            if interrupted_count > 0:
                logger.warning(f"[恢复] 标记 {interrupted_count} 个中断任务")

            # 按部署角色决定是否启动采集调度器（v4.19.x 本地与云端部署角色区分）
            enable_collection = os.getenv("ENABLE_COLLECTION", "true").lower() in (
                "true",
                "1",
            )
            deployment_role = os.getenv("DEPLOYMENT_ROLE", "").lower()
            if not enable_collection or deployment_role == "cloud":
                logger.info(
                    "[调度器] 未启用采集调度器 (ENABLE_COLLECTION=false 或 DEPLOYMENT_ROLE=cloud)"
                )
            # 初始化采集调度器
            elif APSCHEDULER_AVAILABLE:
                scheduler = CollectionScheduler.get_instance(
                    db_session_factory=SessionLocal
                )
                await scheduler.initialize()
                await scheduler.start()

                # 加载所有启用的定时配置
                loaded_count = await scheduler.load_all_schedules()
                logger.info(f"[调度器] 已加载 {loaded_count} 个定时采集配置")

                # 注册清理任务到调度器(每天凌晨3点执行)
                try:
                    from backend.services.cleanup_service import cleanup_service

                    # 添加每日清理任务
                    if scheduler._scheduler:
                        from apscheduler.triggers.cron import CronTrigger

                        scheduler._scheduler.add_job(
                            cleanup_service.run_full_cleanup,
                            trigger=CronTrigger(hour=3, minute=0),
                            id="daily_cleanup",
                            name="每日临时文件清理",
                            replace_existing=True,
                        )
                        logger.info("[调度器] 已注册每日清理任务(3:00 AM)")
                except Exception as cleanup_err:
                    logger.warning(f"[调度器] 清理任务注册失败: {cleanup_err}")

                # 保存到应用状态
                app.state.collection_scheduler = scheduler
            else:
                logger.warning("[调度器] APScheduler未安装,定时采集功能禁用")

        except Exception as scheduler_err:
            logger.warning(f"[调度器] 初始化失败(不影响主功能): {scheduler_err}")

    except Exception as e:
        logger.error(f"[ERROR] 系统启动失败: {e}")
        raise

        # Legacy dashboard scheduler notes retained for historical context only.

    yield

    # 关闭时执行
    logger.info("[关闭] 西虹ERP系统后端服务关闭")

    # v4.19.0新增:停止资源监控服务
    try:
        cloud_sync_runtime = getattr(app.state, "cloud_sync_runtime", None)
        if cloud_sync_runtime is not None:
            await cloud_sync_runtime.stop()
            logger.info("[CloudSync] Cloud sync worker stopped")
    except Exception as e:
        logger.warning(f"[Shutdown] Failed to stop cloud sync worker cleanly: {e}")

    try:
        if hasattr(app.state, "resource_monitor") and app.state.resource_monitor:
            await app.state.resource_monitor.stop()
            logger.info("[ResourceMonitor] 资源监控服务已停止")
    except Exception as e:
        logger.warning(f"[关闭] 停止资源监控服务时出现异常(可忽略): {e}")

    # v4.19.0新增:关闭执行器管理器
    try:
        from backend.services.executor_manager import get_executor_manager

        executor_manager = get_executor_manager()  # 或 app.state.executor_manager
        await executor_manager.shutdown(timeout=30)
        logger.info("[ExecutorManager] 执行器管理器已关闭")
    except Exception as e:
        logger.warning(f"[关闭] 关闭执行器管理器时出现异常(可忽略): {e}")

    # v4.7.0新增:关闭采集调度器
    try:
        if (
            hasattr(app.state, "collection_scheduler")
            and app.state.collection_scheduler
        ):
            await app.state.collection_scheduler.shutdown(wait=False)
            logger.info("[调度器] 采集调度器已关闭")
    except Exception as e:
        logger.debug(f"[关闭] 关闭调度器时出现异常(可忽略): {e}")

    # v4.12.0修复:正确取消后台任务,优雅处理CancelledError异常
    # 使用try-except包装整个关闭流程,避免CancelledError影响关闭
    try:
        for task in background_tasks:
            if not task.done():
                try:
                    task.cancel()
                    # 不等待任务完成,直接继续关闭流程
                    # 任务会在后台自动取消,CancelledError会被任务内部处理
                except Exception as e:
                    # 捕获所有异常,避免影响关闭流程
                    logger.debug(f"[关闭] 取消后台任务时出现异常(可忽略): {e}")
    except Exception as e:
        # 捕获关闭过程中的所有异常,确保关闭流程继续
        logger.debug(f"[关闭] 关闭过程中出现异常(可忽略): {e}")

    # [WARN] v4.6.0 DSS架构重构:物化视图和C类数据计算已迁移到Metabase


# 创建FastAPI应用
app = FastAPI(
    title="西虹ERP系统API",
    description="""
    智能跨境电商ERP系统后端API服务
    
    ## API响应格式标准
    
    所有API遵循统一的响应格式:
    
    **成功响应**:
    ```json
    {
        "success": true,
        "data": {...},
        "message": "操作成功",  // 可选
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    **错误响应**:
    ```json
    {
        "success": false,
        "error": {
            "code": 2001,
            "type": "BusinessError",
            "detail": "详细错误信息",
            "recovery_suggestion": "恢复建议"
        },
        "message": "用户友好的错误信息",
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    **分页响应**:
    ```json
    {
        "success": true,
        "data": [...],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 100,
            "total_pages": 5,
            "has_previous": false,
            "has_next": true
        },
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    详细文档:参见 `docs/API_CONTRACTS.md`
    """,
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# 添加中间件
# 请求ID中间件(必须在最前面,确保所有请求都有request_id)
app.add_middleware(RequestIDMiddleware)

# API性能监控中间件(基础监控 - 日志记录)
app.add_middleware(PerformanceLoggingMiddleware)

# [*] v6.0.0新增:CSRF 保护中间件(Phase 3: CSRF Token 保护)
# 注意:可以通过环境变量 CSRF_ENABLED 禁用(开发环境可能需要禁用)
csrf_enabled = os.getenv("CSRF_ENABLED", "false").lower() == "true"
if csrf_enabled:
    from backend.middleware.csrf import CSRFMiddleware

    app.add_middleware(CSRFMiddleware, enabled=True)
    logger.info("[Security] CSRF 保护已启用")
else:
    logger.info("[Security] CSRF 保护已禁用(设置 CSRF_ENABLED=true 启用)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# API速率限制(v4.6.3新增)
try:
    from backend.middleware.rate_limiter import limiter, rate_limit_handler
    from slowapi.errors import RateLimitExceeded

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    logger.info("[OK] API速率限制已启用")
except ImportError:
    logger.warning("[SKIP] slowapi未安装,速率限制未启用")


# 认证依赖
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """获取当前用户(简化版本)"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 这里应该验证token,简化版本直接返回
    return {
        "user_id": "1",
        "username": "admin",
        "permissions": [
            "dashboard",
            "collection",
            "management",
            "accounts",
            "field-mapping",
        ],
    }


# 健康检查端点(增强版 - v4.1.0,v4.4.1修复路径)
@app.get("/api/health", tags=["系统"])
@app.get("/health", tags=["系统"])  # 保留兼容性
async def health_check(db: Session = Depends(get_db)):
    """
    增强的健康检查端点

    检查项:
    - 数据库连接状态
    - 连接池状态
    - 已注册路由数量
    """
    from datetime import datetime
    from sqlalchemy import text
    from backend.models.database import engine

    health_status = {
        "status": "healthy",
        "service": "西虹ERP系统API",
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": {
            "status": "unknown",
            "type": "PostgreSQL" if "postgresql" in settings.DATABASE_URL else "SQLite",
        },
        "routes": {
            "total": len(app.routes),
            "endpoints": len([r for r in app.routes if hasattr(r, "path")]),
        },
        "pool": {"size": 0, "checked_out": 0, "overflow": 0},
        "executors": {  # [*] v4.19.0新增:执行器健康检查
            "status": "unknown",
            "cpu_executor": {},
            "io_executor": {},
        },
    }

    # 检查数据库连接
    try:
        db.execute(text("SELECT 1"))
        health_status["database"]["status"] = "connected"
    except Exception as e:
        health_status["database"]["status"] = "error"
        health_status["database"]["error"] = str(e)
        health_status["status"] = "unhealthy"

    # 检查连接池状态
    try:
        pool = engine.pool
        health_status["pool"]["size"] = pool.size()
        health_status["pool"]["checked_out"] = pool.checkedout()
        health_status["pool"]["overflow"] = pool.overflow()
    except Exception as e:
        health_status["pool"]["error"] = str(e)

    # [*] v4.19.0新增:检查执行器健康状态
    try:
        from backend.services.executor_manager import get_executor_manager

        executor_manager = get_executor_manager()
        executor_health = await executor_manager.check_health(timeout=2.0)

        health_status["executors"] = executor_health

        # 如果执行器不健康,标记整体状态为unhealthy
        if executor_health["overall_status"] != "healthy":
            health_status["status"] = "unhealthy"
            health_status["executors"]["status"] = executor_health["overall_status"]
        else:
            health_status["executors"]["status"] = "healthy"

    except Exception as e:
        health_status["executors"] = {
            "status": "error",
            "error": f"执行器健康检查失败: {str(e)}",
        }
        # [WARN] 注意:执行器健康检查失败不应该导致整体健康检查失败
        # 因为执行器是可选的(某些功能可能不使用执行器)
        # 但可以记录警告
        logger.warning(f"[HealthCheck] 执行器健康检查失败: {e}")

    return health_status


# 根路径
@app.get("/", tags=["系统"])
async def root():
    """根路径"""
    return {
        "message": "欢迎使用西虹ERP系统API",
        "version": "4.0.0",
        "docs": "/api/docs",
        "health": "/health",
    }


# 注册路由(全部启用 - v4.1.0优化版)

logger.info("Dashboard router source: PostgreSQL")
app.include_router(dashboard_api_postgresql.router, tags=["Dashboard"])

app.include_router(collection.router, prefix="/api/collection", tags=["数据采集"])

# Phase 8.1: UI化组件录制工具API
app.include_router(
    component_recorder.router, prefix="/api/collection", tags=["组件录制"]
)

# v4.6.0 数据采集WebSocket
try:
    from backend.routers import collection_websocket

    app.include_router(
        collection_websocket.router, prefix="/api/collection", tags=["采集WebSocket"]
    )

    from backend.routers import (
        main_accounts,
        platform_shop_discoveries,
        shop_account_aliases,
        shop_accounts,
    )

    app.include_router(main_accounts.router, prefix="/api", tags=["主账号管理"])
    app.include_router(shop_accounts.router, prefix="/api", tags=["店铺账号管理"])
    app.include_router(
        shop_account_aliases.router, prefix="/api", tags=["店铺别名管理"]
    )
    app.include_router(
        platform_shop_discoveries.router, prefix="/api", tags=["平台店铺ID发现"]
    )

    # Phase 9.4: 组件版本管理API
    from backend.routers import component_versions

    app.include_router(component_versions.router, prefix="/api", tags=["组件版本管理"])
except ImportError as e:
    logger.warning(f"Collection WebSocket router not loaded: {e}")

app.include_router(management.router, prefix="/api/management", tags=["数据管理"])

# v4.18.0: accounts.router 已删除，账号管理已全面切换到 main_accounts / shop_accounts / shop_account_aliases

app.include_router(field_mapping.router, prefix="/api/field-mapping", tags=["字段映射"])

# v4.3.7 字段映射辞典API(中文友好)
app.include_router(
    field_mapping_dictionary.router, prefix="/api/field-mapping", tags=["字段映射辞典"]
)

# [WARN] v4.6.0 DSS架构重构:已删除field_mapping_dictionary_mv_display(DSS架构不再需要物化视图显示标识)

# v4.12.0: 数据同步API(新统一入口)
app.include_router(data_sync.router, prefix="/api", tags=["数据同步"])

# v4.13.0: 字段映射质量评分API
app.include_router(data_sync_mapping_quality.router, prefix="/api", tags=["数据同步"])

app.include_router(data_pipeline.router, tags=["数据管道"])

# v4.19.0: 通知WebSocket路由
try:
    from backend.routers import notification_websocket

    app.include_router(
        notification_websocket.router, prefix="/api", tags=["通知WebSocket"]
    )
    # WebSocket 清理任务将在 lifespan startup 中启动
except ImportError as e:
    logger.warning(f"Notification WebSocket router not loaded: {e}")

# v4.19.0: 系统资源监控API
from backend.routers import system_monitoring

app.include_router(system_monitoring.router, prefix="/api", tags=["系统监控"])

# v4.5.0: 自动入库API(v4.12.0已废弃,统一使用data_sync)
# [WARN] 注意:只保留治理统计API,自动入库API已移除
# 治理统计API(governance/*)仍然需要,因为数据治理功能依赖这些API
from backend.routers import auto_ingest

app.include_router(
    auto_ingest.router,
    prefix="/api/field-mapping",
    tags=["数据治理统计"],  # [*] 只保留治理统计API,自动入库API已废弃
)

# v4.6.0 数据隔离区API(查看和重新处理隔离数据)
app.include_router(data_quarantine.router, prefix="/api", tags=["数据隔离区"])

app.include_router(data_quality.router, prefix="/api", tags=["数据质量监控"])

# ============================================================================
# Phase 3: A类数据管理API(销售目标、战役目标、经营成本)
# ============================================================================
app.include_router(config_management.router, tags=["A类数据管理", "配置管理"])

# ============================================================================
# Phase 3: HR管理API(员工管理、员工目标、考勤记录、绩效查询)
# ============================================================================
app.include_router(hr_management.router, tags=["HR管理"])

app.include_router(inventory_domain.router, tags=["库存管理"])

app.include_router(inventory_overview.router, tags=["库存总览"])

# 业务模块路由

# v4.17.0: 财务域API已删除(财务域表已删除,API路由已移除)
# app.include_router(
#     finance.router,
#     prefix="/api/finance",
#     tags=["财务管理"]
# )
from backend.routers import follow_investment, profit_basis

app.include_router(profit_basis.router, tags=["利润结算基准"])
app.include_router(follow_investment.router, tags=["跟投收益"])

# 系统管理路由
app.include_router(auth.router, prefix="/api", tags=["认证管理"])

app.include_router(users.router, prefix="/api", tags=["用户管理"])

app.include_router(roles.router, prefix="/api", tags=["角色管理"])

# v4.20.0: 权限管理路由
app.include_router(permissions.router, tags=["权限管理"])  # /api/permissions/tree

app.include_router(permission.router, tags=["权限管理"])  # /api/system/permissions

# v4.19.0: 通知管理路由
app.include_router(notifications.router, prefix="/api", tags=["通知管理"])

# 开发工具路由
app.include_router(test_api.router, prefix="/api/test", tags=["测试诊断"])

app.include_router(
    performance.router,
    prefix="/api",
    tags=["系统性能监控"],  # v4.18.0: 修改为/api/system/performance,避免与绩效管理冲突
)

# v4.10.0更新:库存管理API(原产品管理)

# v4.3.5 系统配置API(白名单平台/域/粒度)
app.include_router(
    system.router, tags=["系统配置"]  # v4.20.0: 前缀已更新为 /api/system
)

# v4.20.0 系统日志API
app.include_router(system_logs.router, tags=["系统日志"])  # 前缀: /api/system/logs

# v4.20.0 安全设置API
from backend.routers import security as security_router

app.include_router(
    security_router.router, tags=["安全设置"]  # 前缀: /api/system/security
)

# v4.20.0 数据备份与恢复API
app.include_router(backup.router, tags=["数据备份"])  # 前缀: /api/system/backup

# v4.20.0 系统维护API
app.include_router(
    maintenance.router, tags=["系统维护"]  # 前缀: /api/system/maintenance
)

# v4.20.0 通知配置API
app.include_router(
    notification_config.router, tags=["通知配置"]  # 前缀: /api/system/notification
)

# v4.3.6 账号对齐API(妙手订单账号级归并)
app.include_router(account_alignment.router, prefix="/api", tags=["账号对齐"])

# v4.17.0: 采购管理API已删除(财务域表已删除,API路由已移除)
# app.include_router(
#     procurement.router,
#     prefix="/api/procurement",
#     tags=["采购管理"]
# )

# [WARN] v4.12.0移除:旧数据浏览器API已移除
# v4.7.0 数据库浏览器API(查看已入库数据)
# app.include_router(
#     data_browser.router,
#     prefix="/api",
#     tags=["数据库浏览器"]
# )

# v4.8.0 物化视图管理API(刷新、状态查询)
# [WARN] v4.6.0后旧materialized_views路由已删除

# v4.11.0 销售战役管理API
app.include_router(sales_campaign.router, prefix="/api", tags=["销售战役管理"])

# v4.11.0 目标管理API
app.include_router(target_management.router, prefix="/api", tags=["目标管理"])

# v4.21.0 费用管理API
app.include_router(expense_management.router, prefix="/api", tags=["费用管理"])

# v4.11.0 绩效管理API
app.include_router(performance_management.router, prefix="/api", tags=["绩效管理"])

# [WARN] v4.6.0后旧store_analytics路由已删除

# v4.11.5 原始数据层查看API
app.include_router(raw_layer.router, tags=["原始数据层"])

app.include_router(raw_layer_export.router, tags=["原始数据层"])

# v4.11.5 数据流转追踪API
app.include_router(data_flow.router, tags=["数据流转追踪"])

# [WARN] v4.6.0后旧metrics路由已删除

# v4.11.5 数据一致性验证API
app.include_router(data_consistency.router, tags=["数据一致性验证"])

# [WARN] v4.6.0后旧main_views路由已删除

# [*] v4.12.0新增:数据库设计规范验证API
app.include_router(database_design_validator.router, tags=["数据库设计规范验证"])

# Legacy compatibility only: keep /api/mv available while DSS convergence completes.
app.include_router(mv.router, prefix="/api", tags=["遗留物化视图管理"])

# [*] v4.19.2新增:限流管理API
app.include_router(rate_limit.router, prefix="/api", tags=["限流管理"])

# [*] v4.19.4 新增:限流配置管理API(Phase 3)
app.include_router(rate_limit_config.router, tags=["限流配置管理"])

# v5.0.0 新增:数据迁移API
app.include_router(data_migration.router, prefix="/api", tags=["数据迁移"])

app.include_router(cloud_sync_router.router, tags=["云端同步管理"])

app.include_router(task_center.router, prefix="/api", tags=["任务中心"])

# 全局异常处理(v4.6.0统一响应格式)
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.utils.exceptions import APIException, error_response_v2
from modules.core.exceptions import ERPException


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理(统一响应格式)"""
    # 获取请求ID(从请求状态)
    request_id = getattr(request.state, "request_id", None)

    # 记录错误日志(包含请求ID和上下文信息)
    logger.error(
        f"[HTTP异常] {request.method} {request.url.path} - "
        f"状态码: {exc.status_code}, 错误: {exc.detail}, "
        f"请求ID: {request_id}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
            "error_detail": str(exc.detail),
        },
    )

    # 根据HTTP状态码映射到业务错误码
    status_to_code = {
        400: ErrorCode.PARAMETER_INVALID,
        401: ErrorCode.AUTH_REQUIRED,
        403: ErrorCode.PERMISSION_DENIED,
        404: ErrorCode.FILE_NOT_FOUND,
        500: ErrorCode.DATABASE_QUERY_ERROR,
    }

    error_code = status_to_code.get(exc.status_code, exc.status_code)
    error_type = get_error_type(error_code)

    return error_response(
        code=error_code,
        message=str(exc.detail) if exc.detail else "请求失败",
        error_type=error_type,
        detail=str(exc.detail) if exc.detail else None,
        status_code=exc.status_code,
        request_id=request_id,
    )


@app.exception_handler(ERPException)
async def erp_exception_handler(request: Request, exc: ERPException):
    """ERPException 体系异常处理(统一响应格式 + 语义化 HTTP 状态码)。"""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"[ERP异常] {request.method} {request.url.path} - "
        f"错误类型: {type(exc).__name__}, "
        f"错误消息: {str(exc)}, "
        f"请求ID: {request_id}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "query_params": str(request.query_params) if request.query_params else None,
            "client_host": request.client.host if request.client else None,
        },
    )

    return error_response_v2(exc, request_id=request_id)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理(兜底,避免未捕获异常泄漏)。"""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        f"[未处理异常] {request.method} {request.url.path} - "
        f"错误类型: {type(exc).__name__}, "
        f"错误消息: {str(exc)}, "
        f"请求ID: {request_id}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "query_params": str(request.query_params) if request.query_params else None,
            "client_host": request.client.host if request.client else None,
        },
    )

    return error_response(
        code=ErrorCode.DATABASE_QUERY_ERROR,
        message="内部服务器错误",
        error_type="SystemError",
        detail=str(exc) if settings.DEBUG else None,
        recovery_suggestion="请稍后重试,如问题持续存在请联系系统管理员并提供请求ID",
        status_code=500,
        request_id=request_id,
    )


if __name__ == "__main__":
    # [*] 注意(2025-12-21):
    # Windows 上 Playwright 需要 ProactorEventLoop(默认),因为需要 create_subprocess_exec
    # 不要设置 WindowsSelectorEventLoopPolicy,否则会导致 NotImplementedError
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
