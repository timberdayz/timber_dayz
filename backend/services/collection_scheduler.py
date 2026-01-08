"""
采集调度服务 - Collection Scheduler Service

提供定时采集任务的调度功能
使用 APScheduler 实现 Cron 表达式调度
"""

import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Awaitable
from contextlib import contextmanager

from sqlalchemy.orm import Session
from sqlalchemy import select

from modules.core.db import CollectionConfig, CollectionTask
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 尝试导入 APScheduler
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.executors.asyncio import AsyncIOExecutor
    APSCHEDULER_AVAILABLE = True
except ImportError:
    logger.warning("APScheduler not installed, scheduled tasks disabled")
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None


class SchedulerError(Exception):
    """调度器错误"""
    pass


class CollectionScheduler:
    """
    采集调度器
    
    功能：
    1. 根据配置的 Cron 表达式创建定时任务
    2. 管理定时任务（暂停/恢复/删除）
    3. 应用启动时自动加载启用的配置
    4. 支持任务冲突检测
    """
    
    # 调度器实例（单例）
    _instance: Optional['CollectionScheduler'] = None
    _scheduler: Optional[AsyncIOScheduler] = None
    
    def __init__(
        self, 
        db_session_factory: Callable[[], Session],
        task_executor: Callable[[int], Awaitable[None]] = None
    ):
        """
        初始化调度器
        
        Args:
            db_session_factory: 数据库会话工厂函数
            task_executor: 任务执行回调函数
        """
        if not APSCHEDULER_AVAILABLE:
            raise SchedulerError("APScheduler is not installed. Run: pip install apscheduler")
        
        self.db_session_factory = db_session_factory
        self.task_executor = task_executor
        self._initialized = False
    
    @classmethod
    def get_instance(
        cls,
        db_session_factory: Callable[[], Session] = None,
        task_executor: Callable[[int], Awaitable[None]] = None
    ) -> 'CollectionScheduler':
        """
        获取调度器单例
        
        Args:
            db_session_factory: 数据库会话工厂（首次调用时必须提供）
            task_executor: 任务执行回调
            
        Returns:
            CollectionScheduler: 调度器实例
        """
        if cls._instance is None:
            if db_session_factory is None:
                raise SchedulerError("db_session_factory is required for first initialization")
            cls._instance = cls(db_session_factory, task_executor)
        
        return cls._instance
    
    @contextmanager
    def _get_db(self):
        """获取数据库会话的上下文管理器"""
        db = self.db_session_factory()
        try:
            yield db
        finally:
            db.close()
    
    async def initialize(self) -> None:
        """
        初始化调度器
        
        创建 APScheduler 实例并配置作业存储
        """
        if self._initialized:
            logger.warning("Scheduler already initialized")
            return
        
        if not APSCHEDULER_AVAILABLE:
            logger.error("Cannot initialize scheduler: APScheduler not available")
            return
        
        try:
            # 获取数据库URL用于作业存储
            database_url = os.getenv('DATABASE_URL', 'sqlite:///scheduler_jobs.db')
            
            # 配置作业存储（使用数据库持久化）
            jobstores = {
                'default': SQLAlchemyJobStore(url=database_url, tablename='apscheduler_jobs')
            }
            
            # 配置执行器
            executors = {
                'default': AsyncIOExecutor()
            }
            
            # 作业默认配置
            job_defaults = {
                'coalesce': True,  # 合并错过的任务
                'max_instances': 1,  # 同一任务最多运行1个实例
                'misfire_grace_time': 60 * 5,  # 5分钟内的延迟任务仍然执行
            }
            
            # 创建调度器
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='Asia/Shanghai'
            )
            
            self._initialized = True
            logger.info("Collection scheduler initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}")
            raise SchedulerError(f"Scheduler initialization failed: {e}")
    
    async def start(self) -> None:
        """启动调度器"""
        if not self._initialized:
            await self.initialize()
        
        if self._scheduler and not self._scheduler.running:
            self._scheduler.start()
            logger.info("Collection scheduler started")
    
    async def shutdown(self, wait: bool = True) -> None:
        """
        关闭调度器
        
        Args:
            wait: 是否等待正在运行的任务完成
        """
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Collection scheduler stopped")
    
    async def load_all_schedules(self) -> int:
        """
        加载所有启用的定时配置
        
        Returns:
            int: 加载的配置数量
        """
        if not self._scheduler:
            logger.warning("Scheduler not initialized")
            return 0
        
        loaded_count = 0
        
        # [*] v4.18.2修复：使用异步数据库操作
        from backend.models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            # 查询所有启用定时的配置
            result = await db.execute(
                select(CollectionConfig).where(
                    CollectionConfig.schedule_enabled == True,
                    CollectionConfig.schedule_cron.isnot(None),
                    CollectionConfig.is_active == True
                )
            )
            configs = result.scalars().all()
            
            for config in configs:
                try:
                    await self.add_schedule(config.id, config.schedule_cron)
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to load schedule for config {config.id}: {e}")
        
        logger.info(f"Loaded {loaded_count} scheduled configurations")
        return loaded_count
    
    async def add_schedule(self, config_id: int, cron_expression: str) -> str:
        """
        添加定时任务
        
        Args:
            config_id: 配置ID
            cron_expression: Cron 表达式 (例如: "0 8 * * *" 每天8点)
            
        Returns:
            str: 作业ID
        """
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        
        # 生成作业ID
        job_id = f"collection_config_{config_id}"
        
        # 检查是否已存在
        existing_job = self._scheduler.get_job(job_id)
        if existing_job:
            # 更新现有作业
            self._scheduler.reschedule_job(
                job_id,
                trigger=CronTrigger.from_crontab(cron_expression)
            )
            logger.info(f"Updated schedule for config {config_id}: {cron_expression}")
        else:
            # 创建新作业
            self._scheduler.add_job(
                self._execute_scheduled_task,
                trigger=CronTrigger.from_crontab(cron_expression),
                id=job_id,
                args=[config_id],
                name=f"Collection Config {config_id}",
                replace_existing=True
            )
            logger.info(f"Added schedule for config {config_id}: {cron_expression}")
        
        return job_id
    
    async def remove_schedule(self, config_id: int) -> bool:
        """
        删除定时任务
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否成功删除
        """
        if not self._scheduler:
            return False
        
        job_id = f"collection_config_{config_id}"
        
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Removed schedule for config {config_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove schedule for config {config_id}: {e}")
            return False
    
    async def pause_schedule(self, config_id: int) -> bool:
        """
        暂停定时任务
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否成功暂停
        """
        if not self._scheduler:
            return False
        
        job_id = f"collection_config_{config_id}"
        
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"Paused schedule for config {config_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to pause schedule for config {config_id}: {e}")
            return False
    
    async def resume_schedule(self, config_id: int) -> bool:
        """
        恢复定时任务
        
        Args:
            config_id: 配置ID
            
        Returns:
            bool: 是否成功恢复
        """
        if not self._scheduler:
            return False
        
        job_id = f"collection_config_{config_id}"
        
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"Resumed schedule for config {config_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to resume schedule for config {config_id}: {e}")
            return False
    
    def get_job_info(self, config_id: int) -> Optional[Dict[str, Any]]:
        """
        获取定时任务信息
        
        Args:
            config_id: 配置ID
            
        Returns:
            Optional[Dict]: 作业信息
        """
        if not self._scheduler:
            return None
        
        job_id = f"collection_config_{config_id}"
        job = self._scheduler.get_job(job_id)
        
        if not job:
            return None
        
        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'pending': job.pending,
            'trigger': str(job.trigger),
        }
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """
        获取所有定时任务
        
        Returns:
            List[Dict]: 所有作业信息
        """
        if not self._scheduler:
            return []
        
        jobs = self._scheduler.get_jobs()
        
        return [
            {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'pending': job.pending,
                'trigger': str(job.trigger),
            }
            for job in jobs
        ]
    
    async def _execute_scheduled_task(self, config_id: int) -> None:
        """
        执行定时任务（v4.7.0更新）
        
        Args:
            config_id: 配置ID
        """
        logger.info(f"Executing scheduled task for config {config_id}")
        
        # [*] v4.18.2修复：使用异步数据库操作
        from backend.models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            # 获取配置
            result = await db.execute(
                select(CollectionConfig).where(
                    CollectionConfig.id == config_id,
                    CollectionConfig.is_active == True
                )
            )
            config = result.scalar_one_or_none()
            
            if not config:
                logger.error(f"Config {config_id} not found or inactive")
                return
            
            # 检查是否已有正在运行的任务（同一配置）
            result = await db.execute(
                select(CollectionTask).where(
                    CollectionTask.config_id == config_id,
                    CollectionTask.status.in_(['running', 'queued', 'paused'])
                )
            )
            existing_task = result.scalar_one_or_none()
            
            if existing_task:
                logger.warning(f"Config {config_id} already has an active task: {existing_task.task_id}")
                return
            
            # 为每个账号创建任务
            account_ids = config.account_ids or []
            
            # v4.7.0: 如果account_ids为空，从数据库加载所有活跃账号
            if not account_ids:
                try:
                    from backend.services.account_loader_service import get_account_loader_service
                    from backend.models.database import SessionLocal
                    import asyncio
                    
                    # [*] v4.18.2修复：使用run_in_executor包装同步账号加载操作
                    def _sync_load_accounts():
                        """同步加载账号（在executor中执行）"""
                        temp_db = SessionLocal()
                        try:
                            account_loader = get_account_loader_service()
                            accounts = account_loader.load_all_accounts(temp_db, platform=config.platform)
                            return [acc['account_id'] for acc in accounts]
                        finally:
                            temp_db.close()
                    
                    loop = asyncio.get_running_loop()
                    account_ids = await loop.run_in_executor(None, _sync_load_accounts)
                    logger.info(f"从数据库加载了 {len(account_ids)} 个活跃账号（平台: {config.platform}）")
                except Exception as e:
                    logger.error(f"从数据库加载账号失败: {e}")
                    return
            
            # v4.7.0: 计算总域数
            total_domains_count = len(config.data_domains)
            if config.sub_domains:
                total_domains_count = len(config.data_domains) * len(config.sub_domains)
            
            for account_id in account_ids:
                # 检查账号冲突
                result = await db.execute(
                    select(CollectionTask).where(
                        CollectionTask.account == account_id,
                        CollectionTask.platform == config.platform,
                        CollectionTask.status.in_(['running', 'paused'])
                    )
                )
                conflict = result.scalar_one_or_none()
                
                if conflict:
                    logger.warning(f"Account {account_id} has conflict task, skipping")
                    continue
                
                # v4.7.0: 构建日期范围
                date_range = {}
                if config.date_range_type == 'custom' and config.custom_date_start and config.custom_date_end:
                    date_range = {
                        'start_date': config.custom_date_start.isoformat(),
                        'end_date': config.custom_date_end.isoformat()
                    }
                else:
                    # 使用date_range_type（today/yesterday/last_7_days等）
                    from datetime import date, timedelta
                    today = date.today()
                    if config.date_range_type == 'today':
                        date_range = {'start_date': today.isoformat(), 'end_date': today.isoformat()}
                    elif config.date_range_type == 'yesterday':
                        yesterday = today - timedelta(days=1)
                        date_range = {'start_date': yesterday.isoformat(), 'end_date': yesterday.isoformat()}
                    elif config.date_range_type == 'last_7_days':
                        start = today - timedelta(days=7)
                        date_range = {'start_date': start.isoformat(), 'end_date': today.isoformat()}
                    elif config.date_range_type == 'last_30_days':
                        start = today - timedelta(days=30)
                        date_range = {'start_date': start.isoformat(), 'end_date': today.isoformat()}
                
                # v4.7.0: 创建任务（新字段）
                task_uuid = str(uuid.uuid4())
                task = CollectionTask(
                    task_id=task_uuid,
                    config_id=config_id,
                    platform=config.platform,
                    account=account_id,
                    data_domains=config.data_domains,
                    sub_domains=config.sub_domains,  # v4.7.0: 数组
                    granularity=config.granularity,
                    date_range=date_range,  # v4.7.0: JSON对象
                    status='pending',  # v4.7.0: 先pending，后台任务启动时改为running
                    progress=0,
                    trigger_type='scheduled',
                    # v4.7.0: 任务粒度优化字段
                    total_domains=total_domains_count,
                    completed_domains=[],
                    failed_domains=[],
                    current_domain=None,
                    debug_mode=False,  # 定时任务默认不使用调试模式
                    created_at=datetime.utcnow()
                )
                
                db.add(task)
                await db.commit()
                await db.refresh(task)
                
                logger.info(f"Created scheduled task {task_uuid} for account {account_id} ({total_domains_count} domains)")
                
                # v4.7.0: 启动后台任务执行
                try:
                    import asyncio
                    # 导入后台执行函数
                    from backend.routers.collection import _execute_collection_task_background
                    
                    # 启动后台任务
                    asyncio.create_task(
                        _execute_collection_task_background(
                            task_id=task_uuid,
                            platform=config.platform,
                            account_id=account_id,
                            data_domains=config.data_domains,
                            sub_domains=config.sub_domains,
                            date_range=date_range,
                            granularity=config.granularity,
                            debug_mode=False,
                            db_session_maker=db.get_bind()
                        )
                    )
                    logger.info(f"Started background execution for task {task_uuid}")
                except Exception as e:
                    logger.error(f"Failed to start background task {task_uuid}: {e}")
    
    @staticmethod
    def validate_cron_expression(cron_expression: str) -> bool:
        """
        验证 Cron 表达式是否有效
        
        Args:
            cron_expression: Cron 表达式
            
        Returns:
            bool: 是否有效
        """
        if not APSCHEDULER_AVAILABLE:
            return False
        
        try:
            CronTrigger.from_crontab(cron_expression)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_cron_description(cron_expression: str) -> str:
        """
        获取 Cron 表达式的人类可读描述
        
        Args:
            cron_expression: Cron 表达式
            
        Returns:
            str: 描述
        """
        # 简单的描述生成
        parts = cron_expression.split()
        if len(parts) != 5:
            return "无效的Cron表达式"
        
        minute, hour, day, month, weekday = parts
        
        descriptions = []
        
        # 处理常见模式
        if minute == '0' and hour != '*':
            descriptions.append(f"每天 {hour}:00")
        elif minute == '0' and hour == '0':
            descriptions.append("每天午夜")
        elif minute == '*' and hour == '*':
            descriptions.append("每分钟")
        else:
            descriptions.append(f"{minute}分 {hour}时")
        
        if weekday != '*':
            weekday_names = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
            if weekday.isdigit():
                descriptions.append(weekday_names[int(weekday) % 7])
            else:
                descriptions.append(f"每周{weekday}")
        
        if day != '*':
            descriptions.append(f"每月{day}日")
        
        return ' '.join(descriptions)


# 常用 Cron 表达式预设
CRON_PRESETS = {
    # [*] v4.7.0标准预设（Phase 4.1.6）[*]
    'daily_realtime': '0 6,12,18,22 * * *',    # 日度实时（每天4次：6点/12点/18点/22点）
    'weekly_summary': '0 5 * * 1',              # 周度汇总（每周一 05:00）
    'monthly_summary': '0 5 1 * *',             # 月度汇总（每月1号 05:00）
    
    # 其他常用预设
    'every_day_8am': '0 8 * * *',              # 每天早上8点
    'every_day_9am': '0 9 * * *',              # 每天早上9点
    'every_day_midnight': '0 0 * * *',         # 每天午夜
    'every_monday_9am': '0 9 * * 1',           # 每周一早上9点
    'every_month_1st': '0 9 1 * *',            # 每月1日早上9点
    'every_hour': '0 * * * *',                 # 每小时整点
    'every_6_hours': '0 */6 * * *',            # 每6小时
    'every_12_hours': '0 */12 * * *',          # 每12小时
}

