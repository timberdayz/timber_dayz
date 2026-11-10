"""
Celery配置 - 西虹ERP系统异步任务队列

[*] v4.19.1 恢复 Celery 任务队列:
- 数据同步任务(支持任务持久化、恢复、重试)
- 定时任务(自动入库、低库存告警、应收账款逾期检查、数据库备份)

功能:
- 任务持久化:任务存储在 Redis 中,服务器重启后自动恢复
- 资源隔离:任务在独立的 Celery worker 进程中执行,不影响 API 服务
- 水平扩展:可以通过增加 worker 来扩展处理能力
- 任务优先级:支持任务优先级(需要 Redis >= 5.0)

启动说明:
- Linux/Mac: celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --concurrency=4
- Windows: celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4
"""

from celery import Celery
from celery.schedules import crontab
import os

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_celery_broker_url = os.getenv("CELERY_BROKER_URL", _redis_url)
_celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", _redis_url)

# ---------------------------------------------------------------------------
# [*] Redis 不可达时的「快速失败」配置(2026-11-09)
# ---------------------------------------------------------------------------
#
# 事故现场
# --------
# ``task.delay()`` 并不只是「把消息发到 broker」—— Celery 在 ``send_task()``
# 末尾会回调 ``backend.on_task_call(producer, task_id)``; Redis 结果后端在这里
# 会**订阅该任务的 pubsub 通道**。也就是说**每次派发任务都要连一次 Redis**,
# 而且是**同步阻塞**地连(``kombu`` 的 ``retry_over_time``)。
#
# Redis 不可达(宕机/网络分区/密码错)时, 这里的重试是**嵌套**的:
#   外层 ``ResultConsumer.reconnect_on_error`` -> 内层 ``ensure()`` 的
#   ``retry_over_time``(默认 max_retries=20, 间隔 1 秒) -> 每次失败又走一遍
#   redis-py 自身的 ``connect_check_health`` 重试。
# 实测(本机 Redis 不可达): 单次 ``delay()`` **阻塞 16~17 秒**才抛
# ``OperationalError``; 在 async 上下文里, 这等于**整个事件循环被冻住**,
# 所有并发请求一起挂起 —— 表现就是「Redis 一抖, 整个 API 500」。
#
# 为什么不能只靠「捕获异常」
# --------------------------
# 调用点(如 ``backend/services/data_ingestion_service.py`` 的图片提取派发)
# 确实写了 ``except`` 兜底, 但那是在**卡了十几秒之后**才轮得到它。
# 故障时最需要的是「立刻失败、立刻让位」, 而不是「慢慢失败」。
#
# 这里的取舍
# ----------
# * ``socket_connect_timeout``: 建连最多等 **1 秒**(2026-11-10 由 3 秒收紧)。
#   Redis 是**同机房**服务, 正常建连是毫秒级(实测 0.07 ms), 1 秒已经足够
#   容忍一次网络抖动; 再久就是「它已经不在了」。
# * ``retry_policy.max_retries``: 发布重试 **1 次**、结果后端 1 次。
#   原生默认值(20 次 × 1 秒)对「派发一个图片提取任务」这种**可有可无**的
#   后台任务是灾难性的 —— 宁可失败, 也不要占住事件循环十几秒。
# * ``broker_connection_max_retries``: broker 建连重试上限。Celery 默认
#   **100 次**, 这是「连不上就永远重试」的元凶之一。
#
# 注意: 这些**只影响「连不上」时的行为**。Redis 正常时, 派发任务的耗时与
# 之前完全一样(2026-11-10 生产实测中位数 **0.52 ms**), 不会因为限了重试而丢任务。
#
# [*] 2026-11-10 再收紧一次(生产实测后调整)
# ------------------------------------------------
# 生产实测(Redis **健康**,在 backend_api 容器内实测, 与生产代码同一条路径):
#   Redis PING 中位数 **0.07 ms** / broker 建连 **1.31 ms** /
#   完整派发 ``send_task(..., ignore_result=True)`` 中位数 **0.52 ms**
#   ⇒ **正常状态下派发根本不是瓶颈**, 台账里那个「4.1 秒」是
#   **Redis 不可达时的退化阻塞**, 和 16~17 秒同源, 不是日常耗时。
#
# 真正的剩余风险: 退化路径的**同步阻塞**发生在 API 的 asyncio 事件循环里
# ⇒ Redis 一抖, 全站请求一起挂起。两条对策:
#   1) 把退化路径的阻塞上限再压一半(本文件): 建连超时 3 -> **1 秒**、
#      发布重试 2 -> **1 次** ⇒ 阻塞从约 4.1 秒降到约 2 秒量级;
#   2) 把派发动作**移出事件循环**(``backend/utils/celery_dispatch.py``):
#      即便 Redis 不可达, 也只有这一个请求在等, **其它请求照常服务**。
#      2026-11-10 已把 async 上下文里的 7 个派发点全部接上。
#
# (「1 秒」与「1 次」的取舍依据见上面「这里的取舍」一段)
_REDIS_SOCKET_CONNECT_TIMEOUT = int(
    os.getenv("CELERY_REDIS_SOCKET_CONNECT_TIMEOUT", "1") or 1
)
_CELERY_PUBLISH_RETRY_POLICY = {
    "max_retries": int(os.getenv("CELERY_PUBLISH_MAX_RETRIES", "1") or 1),
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 2,
}
_CELERY_RESULT_RETRY_POLICY = {
    "max_retries": int(os.getenv("CELERY_RESULT_MAX_RETRIES", "1") or 1),
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 2,
}

# Celery应用配置
celery_app = Celery(
    "xihong_erp",
    broker=_celery_broker_url,
    backend=_celery_result_backend,
    include=[
        "backend.tasks.data_processing",
        "backend.tasks.scheduled_tasks",
        "backend.tasks.data_sync_tasks",  # [*] v4.19.1 恢复:数据同步任务模块
        "backend.tasks.refresh_queue_tasks",
        "backend.tasks.price_adjust_notify_tasks",  # 最低售价变更检测与飞书通知
        "backend.tasks.image_extraction",  # [*] 图片提取任务模块
        "backend.tasks.source_freshness_tasks",  # 源数据新鲜度巡检（断流告警）
        "backend.tasks.cloud_sync_integrity_tasks",  # 云端同步链路完整性巡检（陈旧/收敛率/候选池）
        # [WARN] v4.6.0 DSS架构重构:已删除mv_refresh(Metabase直接查询原始表,无需物化视图)
        # [WARN] v4.6.0 DSS架构重构:已删除c_class_calculation(C类数据由Metabase定时计算)
    ],
)

# Celery配置
celery_app.conf.update(
    # 时区设置
    timezone="Asia/Shanghai",
    enable_utc=True,
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=86400,  # 结果过期时间(24小时)，控制 Redis result 占用
    # 性能配置
    worker_prefetch_multiplier=4,  # 预取任务数
    worker_max_tasks_per_child=1000,  # 每个worker最多处理1000个任务后重启(防止内存泄漏)
    # 并发配置
    worker_concurrency=4,  # 并发worker数量
    # 任务路由
    task_routes={
        "backend.tasks.data_processing.*": {"queue": "data_processing"},
        "backend.tasks.scheduled_tasks.*": {"queue": "scheduled"},
        "backend.tasks.data_sync_tasks.*": {
            "queue": "data_sync"
        },  # [*] v4.19.1 恢复:数据同步队列
        "backend.tasks.price_adjust_notify_tasks.*": {"queue": "scheduled"},
        # 源数据新鲜度巡检：轻量只读巡检，放定时任务队列即可。
        # 断流时它会把结论写进 ops.pipeline_run_log（状态 partial_failed）。
        "backend.tasks.source_freshness_tasks.*": {"queue": "scheduled"},
        # 云端同步链路完整性巡检：同样是轻量只读巡检，放定时任务队列即可。
        # 它盯的是**云端**那一侧（连接哪就巡检哪个）——
        # 采集机侧用它回答「云端还有没有在收数据」。
        "backend.tasks.cloud_sync_integrity_tasks.*": {"queue": "scheduled"},
        "extract_product_images": {
            "queue": "data_processing"
        },  # [*] 图片提取任务路由到 data_processing 队列
        # 刷新队列独立成一条道（2026-11-11）：按业务域分道并发，最多 2 道同时跑。
        # 独立队列的好处：刷新任务单条最长 250 秒，不跟「定时任务」互相拖慢。
        "backend.tasks.refresh_queue_tasks.process_refresh_queue_task": {
            "queue": "refresh_queue"
        },
    },
    # [*] v4.19.1 新增:任务优先级(需要 Redis >= 5.0 支持)
    task_default_priority=5,  # 默认优先级(1-10,10最高)
    # [*] v4.19.1 新增:任务持久化
    task_acks_late=True,  # 任务完成后才确认(支持任务恢复)
    task_reject_on_worker_lost=True,  # Worker 崩溃时重新分配任务
    # [*] v4.19.1 新增:任务超时
    task_time_limit=1800,  # 30分钟硬超时(强制终止)
    task_soft_time_limit=1500,  # 25分钟软超时(发送 SoftTimeLimitExceeded 异常)
    # [*] Redis 不可达时**快速失败**(2026-11-09)—— 理由见本文件上方长注释。
    # 派发后台任务是「可有可无」的操作, 绝不该为了它把事件循环冻住十几秒。
    broker_connection_max_retries=2,
    broker_transport_options={
        "socket_connect_timeout": _REDIS_SOCKET_CONNECT_TIMEOUT,
        "retry_policy": dict(_CELERY_PUBLISH_RETRY_POLICY),
    },
    result_backend_transport_options={
        "socket_connect_timeout": _REDIS_SOCKET_CONNECT_TIMEOUT,
        "retry_policy": dict(_CELERY_RESULT_RETRY_POLICY),
    },
    task_publish_retry_policy=dict(_CELERY_PUBLISH_RETRY_POLICY),
    redis_socket_connect_timeout=_REDIS_SOCKET_CONNECT_TIMEOUT,
)

# 定时任务配置
celery_app.conf.beat_schedule = {
    # [WARN] v4.6.0 DSS架构重构:已删除物化视图刷新任务(Metabase直接查询原始表)
    # 'refresh-sales-views-every-5min': {
    #     'task': 'backend.tasks.scheduled_tasks.refresh_sales_materialized_views',
    #     'schedule': crontab(minute='*/5'),
    # },
    # 'refresh-inventory-finance-views-every-10min': {
    #     'task': 'backend.tasks.scheduled_tasks.refresh_inventory_finance_views',
    #     'schedule': crontab(minute='*/10'),
    # },
    # 每15分钟自动入库兜底扫描
    "auto-ingest-pending-files-every-15min": {
        "task": "backend.tasks.scheduled_tasks.auto_ingest_pending_files",
        "schedule": crontab(minute="*/15"),
    },
    "cleanup-stale-auto-ingest-every-5min": {
        "task": "backend.tasks.scheduled_tasks.cleanup_stale_auto_ingest_tasks",
        "schedule": crontab(minute="*/5"),
    },
    # 每分钟派 2 道刷新任务（2026-11-11）。
    #
    # 为什么是 2 条而不是 1 条：刷新按**业务域分道**（orders / analytics /
    # products / inventory / services），同一个域永远串行，不同域可以并行。
    # 派 2 条 = 最多有 2 道同时在跑，慢域不再堵住快域。
    #
    # 真正的并发上限在**库里**（``refresh_queue_service.REFRESH_QUEUE_MAX_CONCURRENT``），
    # 这里派多了也只是「领不到任务、空手而归」⇒ 派 2 条是安全上限，不会跑飞。
    #
    # 注意：这两个条目用的是**同一个任务**、只是名字不同（Celery Beat 要求条目名唯一），
    # 两条消息在同一个时刻进队列 ⇒ 两个 worker 槽位同时领活。
    "process-refresh-queue-every-minute": {
        "task": "backend.tasks.refresh_queue_tasks.process_refresh_queue_task",
        "schedule": crontab(minute="*"),
    },
    "process-refresh-queue-lane-2-every-minute": {
        "task": "backend.tasks.refresh_queue_tasks.process_refresh_queue_task",
        "schedule": crontab(minute="*"),
    },
    "cloud-sync-auto-recovery-every-minute": {
        "task": "backend.tasks.scheduled_tasks.cloud_sync_auto_recovery",
        "schedule": crontab(minute="*"),
    },
    # 每6小时检查低库存
    "dashboard-refresh-safety-net-every-5min": {
        "task": "backend.tasks.refresh_queue_tasks.dashboard_refresh_safety_net",
        "schedule": crontab(minute="*/5"),
    },
    "check-low-stock-every-6hours": {
        "task": "backend.tasks.scheduled_tasks.check_low_stock_alert",
        "schedule": crontab(hour="*/6", minute=0),  # 每6小时
    },
    # 每日检查应收账款逾期(每天早上9点)
    "check-overdue-ar-daily": {
        "task": "backend.tasks.scheduled_tasks.check_overdue_accounts_receivable",
        "schedule": crontab(hour=9, minute=0),  # 每天9:00
    },
    # 每日数据库备份(每天凌晨3点)
    "backup-database-daily": {
        "task": "backend.tasks.scheduled_tasks.backup_database",
        "schedule": crontab(hour=3, minute=0),  # 每天3:00
    },
    # 最低售价变更检测与飞书通知（每天10:00）
    # 为什么是每天一次而不是跟库龄采集同步触发：最低售价的输入有七类
    # （库龄档位 / 采购成本 / 平台费率 / SPU 两率 / 参考售价 / 档位规则 / 人工覆盖），
    # 只有库龄是周节奏，其余是事件驱动。每天全量比对一次 = 任何输入变化最迟当天被抓住。
    # 时间定在 10:00，是给 09:00 的库存采集留出缓冲（采集当天库龄才会真的前进）。
    "price-adjust-notify-daily": {
        "task": "backend.tasks.price_adjust_notify_tasks.detect_and_notify_price_adjustments",
        "schedule": crontab(hour=10, minute=0),
    },
    # 源数据新鲜度巡检（每小时一次，整点后 13 分跑，避开整点高峰）。
    #
    # 为什么必须有它：刷新链路全绿 ≠ 业务数据是新的。
    # 2026-10-19 之后商品/服务两条链断了几个月，刷新照跑不误、监控一片绿，
    # 因为我们只监控了「视图有没有重建成功」，没监控「数据有没有进来」。
    # 这个任务盯的是 b_class.fact_* 的最新业务日期，
    # 一旦某条链超过该粒度允许的滞后天数，巡检 run 就是 partial_failed，
    # 在数据平台运行列表里直接能看到是哪条链断了。
    "source-freshness-check-hourly": {
        "task": "backend.tasks.source_freshness_tasks.check_source_data_freshness",
        "schedule": crontab(minute=13),
    },
    # 云端同步链路完整性巡检（每小时一次，整点后 37 分跑，与源数据巡检错开）。
    #
    # 为什么必须有它：源数据巡检盯的是**采集链**（我采到的数据有多旧），
    # 回答不了「云端还有没有在收数据」。
    # 2026-11-07 事故里采集机一切正常，是云端停在 11-06 再也没动过，
    # 而且账本还记着 completed —— 三个信号同时存在，却一个都没人看见。
    # 这个任务盯云端那一侧的三件事：数据新鲜度、身份收敛率、候选池平台覆盖。
    "cloud-sync-integrity-check-hourly": {
        "task": "backend.tasks.cloud_sync_integrity_tasks.check_cloud_sync_integrity",
        "schedule": crontab(minute=37),
    },
}

if __name__ == "__main__":
    celery_app.start()
