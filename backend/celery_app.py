"""
Celery配置 - 西虹ERP系统异步任务队列

[*] v4.19.1 恢复 Celery 任务队列：
- 数据同步任务（支持任务持久化、恢复、重试）
- 定时任务（自动入库、低库存告警、应收账款逾期检查、数据库备份）

功能：
- 任务持久化：任务存储在 Redis 中，服务器重启后自动恢复
- 资源隔离：任务在独立的 Celery worker 进程中执行，不影响 API 服务
- 水平扩展：可以通过增加 worker 来扩展处理能力
- 任务优先级：支持任务优先级（需要 Redis >= 5.0）

启动说明：
- Linux/Mac: celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --concurrency=4
- Windows: celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4
"""

from celery import Celery
from celery.schedules import crontab
import os

# Celery应用配置
celery_app = Celery(
    "xihong_erp",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=[
        "backend.tasks.data_processing",
        "backend.tasks.scheduled_tasks",
        "backend.tasks.data_sync_tasks",  # [*] v4.19.1 恢复：数据同步任务模块
        "backend.tasks.image_extraction",  # [*] 图片提取任务模块
        # [WARN] v4.6.0 DSS架构重构：已删除mv_refresh（Metabase直接查询原始表，无需物化视图）
        # [WARN] v4.6.0 DSS架构重构：已删除c_class_calculation（C类数据由Metabase定时计算）
    ]
)

# Celery配置
celery_app.conf.update(
    # 时区设置
    timezone='Asia/Shanghai',
    enable_utc=True,
    
    # 任务序列化
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_expires=3600,  # 结果过期时间（1小时）
    
    # 性能配置
    worker_prefetch_multiplier=4,  # 预取任务数
    worker_max_tasks_per_child=1000,  # 每个worker最多处理1000个任务后重启（防止内存泄漏）
    
    # 并发配置
    worker_concurrency=4,  # 并发worker数量
    
    # 任务路由
    task_routes={
        'backend.tasks.data_processing.*': {'queue': 'data_processing'},
        'backend.tasks.scheduled_tasks.*': {'queue': 'scheduled'},
        'backend.tasks.data_sync_tasks.*': {'queue': 'data_sync'},  # [*] v4.19.1 恢复：数据同步队列
        'extract_product_images': {'queue': 'data_processing'},  # [*] 图片提取任务路由到 data_processing 队列
    },
    
    # [*] v4.19.1 新增：任务优先级（需要 Redis >= 5.0 支持）
    task_default_priority=5,  # 默认优先级（1-10，10最高）
    
    # [*] v4.19.1 新增：任务持久化
    task_acks_late=True,  # 任务完成后才确认（支持任务恢复）
    task_reject_on_worker_lost=True,  # Worker 崩溃时重新分配任务
    
    # [*] v4.19.1 新增：任务超时
    task_time_limit=1800,  # 30分钟硬超时（强制终止）
    task_soft_time_limit=1500,  # 25分钟软超时（发送 SoftTimeLimitExceeded 异常）
)

# 定时任务配置
celery_app.conf.beat_schedule = {
    # [WARN] v4.6.0 DSS架构重构：已删除物化视图刷新任务（Metabase直接查询原始表）
    # 'refresh-sales-views-every-5min': {
    #     'task': 'backend.tasks.scheduled_tasks.refresh_sales_materialized_views',
    #     'schedule': crontab(minute='*/5'),
    # },
    # 'refresh-inventory-finance-views-every-10min': {
    #     'task': 'backend.tasks.scheduled_tasks.refresh_inventory_finance_views',
    #     'schedule': crontab(minute='*/10'),
    # },
    
    # 每15分钟自动入库兜底扫描
    'auto-ingest-pending-files-every-15min': {
        'task': 'backend.tasks.scheduled_tasks.auto_ingest_pending_files',
        'schedule': crontab(minute='*/15'),
    },
    
    # 每6小时检查低库存
    'check-low-stock-every-6hours': {
        'task': 'backend.tasks.scheduled_tasks.check_low_stock_alert',
        'schedule': crontab(hour='*/6', minute=0),  # 每6小时
    },
    
    # 每日检查应收账款逾期（每天早上9点）
    'check-overdue-ar-daily': {
        'task': 'backend.tasks.scheduled_tasks.check_overdue_accounts_receivable',
        'schedule': crontab(hour=9, minute=0),  # 每天9:00
    },
    
    # 每日数据库备份（每天凌晨3点）
    'backup-database-daily': {
        'task': 'backend.tasks.scheduled_tasks.backup_database',
        'schedule': crontab(hour=3, minute=0),  # 每天3:00
    },
}

if __name__ == '__main__':
    celery_app.start()

