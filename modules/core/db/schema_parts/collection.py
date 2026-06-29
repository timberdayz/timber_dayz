from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base, JSON_COMPAT


class CollectionConfigTemplate(Base):
    """主账号 + 粒度级模板。"""

    __tablename__ = "collection_config_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=True)
    platform = Column(String(50), nullable=False)
    main_account_id = Column(
        String(100),
        ForeignKey("core.main_accounts.main_account_id", ondelete="CASCADE"),
        nullable=False,
        comment="归属主账号ID",
    )
    granularity = Column(String(20), default="daily", nullable=False)
    default_date_range_type = Column(String(32), default="yesterday", nullable=False)
    default_execution_mode = Column(String(20), default="headless", nullable=False)
    default_schedule_enabled = Column(Boolean, default=False, nullable=False)
    default_schedule_cron = Column(String(50), nullable=True)
    default_retry_count = Column(Integer, default=3, nullable=False)
    default_shop_scopes = Column(JSON_COMPAT, nullable=False, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    batches = relationship("CollectionConfig", back_populates="template")

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "main_account_id",
            "granularity",
            name="uq_cc_templates_platform_main_granularity",
        ),
        Index("ix_collection_config_templates_platform", "platform"),
        Index("ix_collection_config_templates_main_account_id", "main_account_id"),
        Index("ix_collection_config_templates_granularity", "granularity"),
        {"schema": "core"},
    )

class CollectionConfig(Base):
    """
    数据采集配置表
    
    存储采集任务的配置模板,支持:
    - 多账号批量采集
    - 多数据域选择
    - 定时调度
    - 日期范围配置
    
    v4.7.0 更新:
    - sub_domain -> sub_domains (改为数组,支持多选)
    - account_ids=[] 表示使用该平台所有活跃账号
    """
    __tablename__ = "collection_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(
        Integer,
        ForeignKey("core.collection_config_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(100), nullable=False)  # 配置名称
    platform = Column(String(50), nullable=False)  # 平台:shopee/tiktok/miaoshou
    main_account_id = Column(
        String(100),
        ForeignKey("core.main_accounts.main_account_id", ondelete="CASCADE"),
        nullable=False,
        comment="归属主账号ID",
    )
    account_ids = Column(JSON, nullable=False)  # 账号ID列表 ["acc1", "acc2"] 或 [](表示所有活跃账号)
    data_domains = Column(JSON, nullable=False)  # 数据域列表 ["orders", "products"]
    sub_domains = Column(JSON, nullable=True)  # 子域数组 ["agent", "ai_assistant"](v4.7.0改为数组)
    granularity = Column(String(20), default="daily", nullable=False)  # 粒度:daily/weekly/monthly
    date_range_type = Column(String(20), default="yesterday", nullable=False)  # today/yesterday/last_7_days/custom
    custom_date_start = Column(Date, nullable=True)  # 自定义开始日期
    custom_date_end = Column(Date, nullable=True)  # 自定义结束日期
    execution_mode = Column(String(20), default="headless", nullable=False)  # 默认执行模式: headless/headed
    schedule_enabled = Column(Boolean, default=False, nullable=False)  # 是否启用定时
    schedule_cron = Column(String(50), nullable=True)  # Cron表达式
    retry_count = Column(Integer, default=3, nullable=False)  # 重试次数
    batch_key = Column(String(32), nullable=True)
    batch_status = Column(String(20), default="draft", nullable=False)
    batch_note = Column(Text, nullable=True)
    batch_shop_overrides = Column(JSON_COMPAT, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)  # 是否启用
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), nullable=True)  # 创建者
    
    # 关系
    template = relationship("CollectionConfigTemplate", back_populates="batches")
    shop_scopes = relationship(
        "CollectionConfigShopScope",
        back_populates="config",
        cascade="all, delete-orphan",
    )
    tasks = relationship("CollectionTask", back_populates="config")
    runs = relationship("CollectionConfigRun", back_populates="config", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint(
            "name",
            "platform",
            "main_account_id",
            name="uq_collection_configs_name_platform_main_account",
        ),
        Index("ix_collection_configs_platform", "platform"),
        Index("ix_collection_configs_main_account_id", "main_account_id"),
        Index("ix_collection_configs_platform_main_account_id", "platform", "main_account_id"),
        Index("ix_collection_configs_template_id", "template_id"),
        Index("ix_collection_configs_batch_key", "batch_key"),
        Index("ix_collection_configs_active", "is_active"),
        {"schema": "core"},
    )

class CollectionConfigShopScope(Base):
    """
    店铺维度采集配置明细表

    一条记录表示某个采集配置在某个店铺上的实际采集范围。
    """

    __tablename__ = "collection_config_shop_scopes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(
        Integer,
        ForeignKey("core.collection_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shop_account_id = Column(
        String(100),
        ForeignKey("core.shop_accounts.shop_account_id", ondelete="CASCADE"),
        nullable=False,
    )
    data_domains = Column(JSON_COMPAT, nullable=False)
    sub_domains = Column(JSON_COMPAT, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    config = relationship("CollectionConfig", back_populates="shop_scopes")

    __table_args__ = (
        UniqueConstraint(
            "config_id",
            "shop_account_id",
            name="uq_collection_config_shop_scopes_config_shop",
        ),
        Index("ix_collection_config_shop_scopes_config_id", "config_id"),
        Index("ix_collection_config_shop_scopes_shop_account_id", "shop_account_id"),
        Index("ix_collection_config_shop_scopes_enabled", "enabled"),
        {"schema": "core"},
    )

class CollectionConfigRun(Base):
    """
    采集配置运行实例。

    用于表达某个 CollectionConfig 在某次触发中进入队列并被执行一次。
    """

    __tablename__ = "collection_config_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(100), nullable=False)
    config_id = Column(
        Integer,
        ForeignKey("core.collection_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform = Column(String(50), nullable=False)
    main_account_id = Column(String(100), nullable=False)
    trigger_type = Column(String(20), nullable=False, default="scheduled")
    status = Column(String(32), nullable=False, default="queued")
    priority = Column(Integer, nullable=False, default=5)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    config = relationship("CollectionConfig", back_populates="runs")
    tasks = relationship("CollectionTask", back_populates="config_run")

    __table_args__ = (
        UniqueConstraint("run_id", name="uq_collection_config_runs_run_id"),
        Index("ix_collection_config_runs_status", "status"),
        Index("ix_collection_config_runs_created_at", "created_at"),
        Index("ix_collection_config_runs_config_id", "config_id"),
        Index("ix_collection_config_runs_main_account_id", "main_account_id"),
        {"schema": "core"},
    )

class CollectionTask(Base):
    """
    数据采集任务表
    
    记录每次采集任务的执行状态和结果,支持:
    - 任务进度跟踪
    - 错误信息记录
    - 验证码暂停
    - 任务恢复和重试
    
    v4.7.0 更新(任务粒度优化):
    - 一个任务 = 一个账号 + 所有配置的数据域
    - 浏览器复用,一次登录采集所有域
    - 支持部分成功机制(单域失败不影响其他域)
    - 新增进度跟踪字段(total_domains, completed_domains, failed_domains, current_domain)
    - 新增 debug_mode 调试模式支持
    - 状态新增 partial_success(部分成功)
    """
    __tablename__ = "collection_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)  # UUID任务标识
    platform = Column(String(50), nullable=False)
    account = Column(String(100), nullable=False)  # 账号ID
    status = Column(String(32), default="pending", nullable=False)  # pending/queued/running/verification_required/verification_submitted/completed/partial_success/failed/cancelled/interrupted
    
    # 关联配置(可选,快速采集时为空)
    config_id = Column(Integer, ForeignKey("core.collection_configs.id", ondelete="SET NULL"), nullable=True)
    config_run_id = Column(
        Integer,
        ForeignKey("core.collection_config_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # 进度跟踪
    progress = Column(Integer, default=0, nullable=False)  # 0-100
    current_step = Column(String(200), nullable=True)  # 当前执行步骤
    files_collected = Column(Integer, default=0, nullable=False)  # 采集文件数
    
    # 任务配置(冗余存储,便于查询)
    trigger_type = Column(String(20), default="manual", nullable=False)  # manual/scheduled/retry
    data_domains = Column(JSON, nullable=True)  # ["orders", "products"]
    sub_domains = Column(JSON, nullable=True)  # ["agent", "ai_assistant"](v4.7.0改为数组)
    granularity = Column(String(20), nullable=True)
    date_range = Column(JSON, nullable=True)  # {"start": "2025-01-01", "end": "2025-01-31"}
    
    # v4.7.0 任务粒度优化字段
    total_domains = Column(Integer, default=0, nullable=False)  # 总数据域数量(含子域)
    completed_domains = Column(JSON, nullable=True)  # 已完成的数据域列表 ["orders", "products:agent"]
    failed_domains = Column(JSON, nullable=True)  # 失败的数据域及原因 [{"domain": "orders", "error": "..."}]
    current_domain = Column(String(100), nullable=True)  # 当前正在采集的数据域(含子域,如 "services:agent")
    
    # 错误信息
    error_message = Column(Text, nullable=True)
    error_screenshot_path = Column(String(500), nullable=True)
    
    # 执行统计
    duration_seconds = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)  # 任务实际开始执行时间(v4.7+ 步骤可观测)
    completed_at = Column(DateTime(timezone=True), nullable=True)  # 任务结束时间(终态时写入)
    retry_count = Column(Integer, default=0, nullable=False)
    parent_task_id = Column(Integer, ForeignKey("core.collection_tasks.id", ondelete="SET NULL"), nullable=True)
    
    # 验证码状态
    verification_type = Column(String(50), nullable=True)  # sms_code/email_code/slider/image/2fa
    verification_screenshot = Column(String(500), nullable=True)
    
    # v4.7.0 调试模式
    debug_mode = Column(Boolean, default=False, nullable=False)  # 调试模式(生产环境临时有头模式)
    
    # 乐观锁版本号
    version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    config = relationship("CollectionConfig", back_populates="tasks")
    config_run = relationship("CollectionConfigRun", back_populates="tasks")
    logs = relationship("CollectionTaskLog", back_populates="task", cascade="all, delete-orphan")
    parent_task = relationship("CollectionTask", remote_side=[id], backref="retry_tasks")
    
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_collection_tasks_task_id"),
        Index("ix_collection_tasks_platform", "platform"),
        Index("ix_collection_tasks_status", "status"),
        Index("ix_collection_tasks_config", "config_id"),
        Index("ix_collection_tasks_config_run", "config_run_id"),
        Index("ix_collection_tasks_created", "created_at"),
        {"schema": "core"},
    )

class CollectionTaskLog(Base):
    """
    采集任务日志表
    
    记录任务执行过程中的详细日志,便于排查问题。
    步骤可观测(v4.7+): details 约定结构为
    { step_id, component?, data_domain?, success?, duration_ms?, error? }，
    供前端步骤时间线解析。step_id 如 login/export_orders/file_process。
    """
    __tablename__ = "collection_task_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("core.collection_tasks.id", ondelete="CASCADE"), nullable=False)
    level = Column(String(10), nullable=False)  # info/warning/error
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)  # 步骤可观测: step_id/component/data_domain/success/duration_ms/error
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    
    # 关系
    task = relationship("CollectionTask", back_populates="logs")
    
    __table_args__ = (
        Index("ix_collection_task_logs_task", "task_id"),
        Index("ix_collection_task_logs_level", "level"),
        Index("ix_collection_task_logs_time", "timestamp"),
        {"schema": "core"},
    )

class CollectionSyncPoint(Base):
    """
    增量采集同步点表 (Phase 9.2 - 已取消,保留表结构)
    
    注意:增量采集功能已取消(不适用于UI模拟场景),但保留表结构以维护迁移历史
    """
    __tablename__ = "collection_sync_points"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 唯一标识(平台+账号+数据域)
    platform = Column(String(50), nullable=False, comment="平台代码")
    account_id = Column(String(100), nullable=False, comment="账号ID")
    data_domain = Column(String(50), nullable=False, comment="数据域: orders/products/inventory/traffic/services")
    
    # 同步点信息
    last_sync_at = Column(DateTime(timezone=True), nullable=False, comment="最后同步时间(UTC)")
    last_sync_value = Column(String(200), nullable=True, comment="最后同步值(如最大的updated_at时间戳)")
    
    # 统计信息
    total_synced_count = Column(Integer, default=0, comment="累计同步记录数")
    last_batch_count = Column(Integer, default=0, comment="最近一次同步记录数")
    
    # 元数据
    sync_mode = Column(String(20), default="incremental", comment="同步模式: full/incremental")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        # 唯一约束:一个账号+数据域只有一个同步点
        UniqueConstraint("platform", "account_id", "data_domain", name="uq_sync_point"),
        # 索引
        Index("ix_sync_points_platform_account", "platform", "account_id"),
        Index("ix_sync_points_last_sync", "last_sync_at"),
        {"schema": "core"},
    )

class TaskCenterTask(Base):
    """Generic durable task control-plane record for long-running jobs."""

    __tablename__ = "task_center_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)
    task_family = Column(String(32), nullable=False)
    task_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    trigger_source = Column(String(32), nullable=True)
    priority = Column(Integer, nullable=False, default=5)
    runner_kind = Column(String(32), nullable=True)
    external_runner_id = Column(String(128), nullable=True)
    parent_task_id = Column(Integer, ForeignKey("task_center_tasks.id", ondelete="SET NULL"), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    claimed_by = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    platform_code = Column(String(32), nullable=True)
    account_id = Column(String(100), nullable=True)
    source_file_id = Column(Integer, nullable=True)
    source_table_name = Column(String(255), nullable=True)
    current_step = Column(String(255), nullable=True)
    current_item = Column(String(500), nullable=True)
    total_items = Column(Integer, nullable=False, default=0)
    processed_items = Column(Integer, nullable=False, default=0)
    success_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    skipped_items = Column(Integer, nullable=False, default=0)
    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    error_rows = Column(Integer, nullable=False, default=0)
    quarantined_rows = Column(Integer, nullable=False, default=0)
    progress_percent = Column(Float, nullable=False, default=0.0)
    error_summary = Column(Text, nullable=True)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    parent_task = relationship("TaskCenterTask", remote_side=[id], backref="child_tasks")
    logs = relationship("TaskCenterLog", back_populates="task", cascade="all, delete-orphan")
    links = relationship("TaskCenterLink", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("task_id", name="uq_task_center_tasks_task_id"),
        Index("ix_task_center_tasks_family_status", "task_family", "status"),
        Index("ix_task_center_tasks_created", "created_at"),
        Index("ix_task_center_tasks_runner", "runner_kind", "external_runner_id"),
        Index("ix_task_center_tasks_source_file", "source_file_id"),
        Index("ix_task_center_tasks_source_table", "source_table_name"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'paused', 'retry_waiting', 'partial_success', 'completed', 'failed', 'cancelled', 'interrupted')",
            name="chk_task_center_tasks_status",
        ),
    )

class TaskCenterLog(Base):
    """Append-only operational log rows for a generic task."""

    __tablename__ = "task_center_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_pk = Column(Integer, ForeignKey("task_center_tasks.id", ondelete="CASCADE"), nullable=False)
    level = Column(String(16), nullable=False, default="info")
    event_type = Column(String(32), nullable=False, default="progress")
    message = Column(Text, nullable=False)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("TaskCenterTask", back_populates="logs")

    __table_args__ = (
        Index("ix_task_center_logs_task", "task_pk"),
        Index("ix_task_center_logs_created", "created_at"),
        Index("ix_task_center_logs_level", "level"),
    )

class TaskCenterLink(Base):
    """Indexed task-to-subject links for reverse lookup."""

    __tablename__ = "task_center_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_pk = Column(Integer, ForeignKey("task_center_tasks.id", ondelete="CASCADE"), nullable=False)
    subject_type = Column(String(32), nullable=False)
    subject_id = Column(String(128), nullable=True)
    subject_key = Column(String(255), nullable=True)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("TaskCenterTask", back_populates="links")

    __table_args__ = (
        Index("ix_task_center_links_task_subject", "task_pk", "subject_type"),
        Index("ix_task_center_links_subject_id", "subject_type", "subject_id"),
        Index("ix_task_center_links_subject_key", "subject_type", "subject_key"),
    )

class EmployeeTask(Base):
    """Employee-facing collaboration task for daily business work."""

    __tablename__ = "employee_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)
    task_type = Column(String(64), nullable=False)
    task_category = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    priority = Column(String(16), nullable=False, default="medium")
    owner_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_module = Column(String(64), nullable=False)
    source_record_type = Column(String(64), nullable=True)
    source_record_id = Column(String(128), nullable=True)
    completion_schema = Column(JSON_COMPAT, nullable=True)
    completion_payload = Column(JSON_COMPAT, nullable=True)
    result_status = Column(String(32), nullable=True)
    result_comment = Column(Text, nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("DimUser", foreign_keys=[owner_user_id], backref="owned_employee_tasks")
    creator = relationship("DimUser", foreign_keys=[created_by], backref="created_employee_tasks")
    logs = relationship("EmployeeTaskLog", back_populates="task", cascade="all, delete-orphan")
    participants = relationship("EmployeeTaskParticipant", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("task_id", name="uq_employee_tasks_task_id"),
        Index("ix_employee_tasks_owner_status", "owner_user_id", "status"),
        Index("ix_employee_tasks_due_at", "due_at"),
        Index("ix_employee_tasks_source", "source_module", "source_record_type", "source_record_id"),
        Index("ix_employee_tasks_created_at", "created_at"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'pending_confirmation', 'completed', 'rejected', 'closed')",
            name="chk_employee_tasks_status",
        ),
        {"schema": "core"},
    )

class EmployeeTaskLog(Base):
    """Timeline row for employee collaboration tasks."""

    __tablename__ = "employee_task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_pk = Column(Integer, ForeignKey("core.employee_tasks.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)
    action = Column(String(32), nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(JSON_COMPAT, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("EmployeeTask", back_populates="logs")
    actor = relationship("DimUser", backref="employee_task_logs")

    __table_args__ = (
        Index("ix_employee_task_logs_task_created", "task_pk", "created_at"),
        {"schema": "core"},
    )

class EmployeeTaskParticipant(Base):
    """Additional participants on employee tasks beyond the primary owner."""

    __tablename__ = "employee_task_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_pk = Column(Integer, ForeignKey("core.employee_tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    participant_role = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task = relationship("EmployeeTask", back_populates="participants")
    user = relationship("DimUser", backref="employee_task_participations")

    __table_args__ = (
        UniqueConstraint("task_pk", "user_id", "participant_role", name="uq_employee_task_participants"),
        Index("ix_employee_task_participants_user_role", "user_id", "participant_role"),
        CheckConstraint(
            "participant_role IN ('cc', 'collaborator')",
            name="chk_employee_task_participant_role",
        ),
        {"schema": "core"},
    )

class ApprovalTemplate(Base):
    """Reusable approval workflow definition."""

    __tablename__ = "approval_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_code = Column(String(100), nullable=False)
    template_name = Column(String(255), nullable=False)
    business_type = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    target_route = Column(String(255), nullable=True)
    form_schema = Column(JSON_COMPAT, nullable=True)
    approval_mode = Column(String(32), nullable=False, default="single")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("template_code", name="uq_approval_templates_template_code"),
        Index("ix_approval_templates_business_type", "business_type"),
        Index("ix_approval_templates_enabled", "enabled"),
    )

class ApprovalInstance(Base):
    """One concrete approval request."""

    __tablename__ = "approval_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_id = Column(String(100), nullable=False)
    template_code = Column(String(100), nullable=False)
    applicant_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    business_key = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="draft")
    current_step = Column(Integer, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    applicant = relationship("DimUser", foreign_keys=[applicant_user_id], backref="approval_instances")

    __table_args__ = (
        UniqueConstraint("approval_id", name="uq_approval_instances_approval_id"),
        Index("ix_approval_instances_applicant_status", "applicant_user_id", "status"),
        Index("ix_approval_instances_template_code", "template_code"),
    )

class ApprovalStep(Base):
    """Sequential approval step for an approval instance."""

    __tablename__ = "approval_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_pk = Column(Integer, ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    approver_type = Column(String(32), nullable=False)
    approver_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    acted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    approval = relationship("ApprovalInstance", backref="steps")
    approver = relationship("DimUser", foreign_keys=[approver_user_id], backref="approval_steps")

    __table_args__ = (
        Index("ix_approval_steps_approval_order", "approval_pk", "step_order"),
        Index("ix_approval_steps_approver_status", "approver_user_id", "status"),
    )

class ApprovalActionLog(Base):
    """Audit log for approval actions."""

    __tablename__ = "approval_action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_pk = Column(Integer, ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False)
    step_pk = Column(Integer, ForeignKey("approval_steps.id", ondelete="SET NULL"), nullable=True)
    actor_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=False)
    action_type = Column(String(32), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    approval = relationship("ApprovalInstance", backref="action_logs")
    step = relationship("ApprovalStep", foreign_keys=[step_pk], backref="action_logs")
    actor = relationship("DimUser", foreign_keys=[actor_user_id], backref="approval_action_logs")

    __table_args__ = (
        Index("ix_approval_action_logs_approval_created", "approval_pk", "created_at"),
        Index("ix_approval_action_logs_actor_created", "actor_user_id", "created_at"),
    )

class TrainingProgram(Base):
    """Formal ERP training program definition."""

    __tablename__ = "training_programs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    program_id = Column(String(64), nullable=True)
    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)
    target_role = Column(String(255), nullable=False)
    external_platform = Column(String(64), nullable=False, default="飞书")
    completion_rule = Column(Text, nullable=False)
    learning_url = Column(String(1024), nullable=True)
    exam_url = Column(String(1024), nullable=True)
    materials_url = Column(String(1024), nullable=True)
    external_course_id = Column(String(128), nullable=True)
    external_exam_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="待上线")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assignments = relationship("TrainingAssignment", back_populates="program", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("program_id", name="uq_training_programs_program_id"),
        Index("ix_training_programs_category", "category"),
        Index("ix_training_programs_status", "status"),
        {"schema": "core"},
    )

class TrainingFeishuConfig(Base):
    """Feishu integration config for training management."""

    __tablename__ = "training_feishu_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_code = Column(String(32), nullable=False, default="feishu")
    app_id = Column(String(128), nullable=False)
    app_secret_encrypted = Column(Text, nullable=True)
    tenant_key = Column(String(128), nullable=True)
    base_url = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, nullable=False, default=False)
    updated_by_user_id = Column(BigInteger, ForeignKey("core.dim_users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider_code", name="uq_training_feishu_configs_provider_code"),
        {"schema": "core"},
    )

class TrainingAssignment(Base):
    """Employee-level training assignment record."""

    __tablename__ = "training_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_id = Column(String(64), nullable=True)
    program_pk = Column(Integer, ForeignKey("core.training_programs.id", ondelete="CASCADE"), nullable=False)
    employee_name = Column(String(128), nullable=False)
    employee_code = Column(String(64), nullable=False)
    department = Column(String(128), nullable=False)
    role_name = Column(String(128), nullable=False)
    learning_status = Column(String(32), nullable=False, default="待学习")
    current_status = Column(String(32), nullable=False, default="待学习")
    due_date = Column(String(32), nullable=False)
    supervisor_name = Column(String(128), nullable=False)
    task_id = Column(String(100), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    program = relationship("TrainingProgram", back_populates="assignments")
    result = relationship("TrainingResult", back_populates="assignment", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_training_assignments_assignment_id"),
        Index("ix_training_assignments_employee_code", "employee_code"),
        Index("ix_training_assignments_current_status", "current_status"),
        Index("ix_training_assignments_program_pk", "program_pk"),
        Index("ix_training_assignments_task_id", "task_id"),
        {"schema": "core"},
    )

class TrainingResult(Base):
    """Training result and score attached to an assignment."""

    __tablename__ = "training_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_pk = Column(Integer, ForeignKey("core.training_assignments.id", ondelete="CASCADE"), nullable=False)
    exam_score = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assignment = relationship("TrainingAssignment", back_populates="result")

    __table_args__ = (
        UniqueConstraint("assignment_pk", name="uq_training_results_assignment_pk"),
        Index("ix_training_results_assignment_pk", "assignment_pk"),
        {"schema": "core"},
    )

class CloudBClassSyncCheckpoint(Base):
    """Per-table checkpoint for local-to-cloud B-class sync."""

    __tablename__ = "cloud_b_class_sync_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_schema = Column(String(64), nullable=False, default="b_class")
    table_name = Column(String(255), nullable=False)
    last_ingest_timestamp = Column(DateTime(timezone=True), nullable=True)
    last_source_id = Column(BigInteger, nullable=True)
    last_status = Column(String(32), nullable=False, default="pending")
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("table_schema", "table_name", name="uq_cloud_b_class_sync_checkpoint"),
        Index("ix_cloud_b_class_sync_checkpoint_table", "table_schema", "table_name"),
    )

class CloudBClassSyncRun(Base):
    """Run-level execution summary for local-to-cloud B-class sync."""

    __tablename__ = "cloud_b_class_sync_runs"

    run_id = Column(String(100), primary_key=True)
    status = Column(String(32), nullable=False, default="pending")
    total_tables = Column(Integer, nullable=False, default=0)
    succeeded_tables = Column(Integer, nullable=False, default=0)
    failed_tables = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_cloud_b_class_sync_runs_status", "status"),
        Index("ix_cloud_b_class_sync_runs_started_at", "started_at"),
    )

class CloudBClassSyncTask(Base):
    """Durable control-plane task for automatic B-class cloud sync."""

    __tablename__ = "cloud_b_class_sync_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), nullable=False, unique=True)
    dedupe_key = Column(String(255), nullable=False)
    source_table_name = Column(String(255), nullable=False)
    platform_code = Column(String(32), nullable=True)
    data_domain = Column(String(64), nullable=True)
    sub_domain = Column(String(64), nullable=True)
    granularity = Column(String(32), nullable=True)
    trigger_source = Column(String(32), nullable=False, default="auto_ingest")
    source_file_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    claimed_by = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_started_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    error_code = Column(String(64), nullable=True)
    projection_preset = Column(String(128), nullable=True)
    projection_status = Column(String(32), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_cloud_b_class_sync_tasks_status", "status"),
        Index("ix_cloud_b_class_sync_tasks_source_table", "source_table_name"),
        Index("ix_cloud_b_class_sync_tasks_dedupe_key", "dedupe_key"),
    )

class CloudSyncReceiveLog(Base):
    """Cloud-side append-only ledger for received B-class sync writes."""

    __tablename__ = "cloud_sync_receive_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    receive_id = Column(String(100), nullable=False)
    source_environment = Column(String(64), nullable=True)
    checkpoint_scope = Column(String(64), nullable=False, default="b_class")
    source_table_name = Column(String(255), nullable=False)
    source_file_id = Column(Integer, nullable=True)
    platform_code = Column(String(32), nullable=True)
    data_domain = Column(String(64), nullable=True)
    granularity = Column(String(32), nullable=True)
    business_date_min = Column(Date, nullable=True)
    business_date_max = Column(Date, nullable=True)
    source_latest_ingest_timestamp = Column(DateTime(timezone=True), nullable=True)
    written_rows = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("receive_id", name="uq_cloud_sync_receive_log_receive_id"),
        Index("ix_cloud_sync_receive_log_created", "created_at"),
        Index("ix_cloud_sync_receive_log_table_created", "source_table_name", "created_at"),
        Index("ix_cloud_sync_receive_log_file", "source_file_id"),
        {"schema": "ops"},
    )

class RefreshQueueTask(Base):
    """Durable global queue row for serial post-ingest refresh work."""

    __tablename__ = "refresh_queue_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(100), nullable=False)
    trigger_type = Column(String(32), nullable=False, default="data_ingested")
    pipeline_name = Column(String(100), nullable=False)
    dedupe_key = Column(String(255), nullable=False)
    targets_json = Column(JSON_COMPAT, nullable=False, default=list)
    context_json = Column(JSON_COMPAT, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_refresh_queue_tasks_job_id"),
        Index("ix_refresh_queue_tasks_status", "status"),
        Index("ix_refresh_queue_tasks_dedupe_key", "dedupe_key"),
        Index("ix_refresh_queue_tasks_created_at", "created_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="chk_refresh_queue_tasks_status",
        ),
        {"schema": "core"},
    )

class ComponentVersion(Base):
    """
    组件版本管理表 (Phase 9.4)
    
    用于管理组件版本、A/B测试和自动切换稳定版本
    
    使用场景:
    - 组件升级时保留旧版本
    - A/B测试新版本组件
    - 自动统计成功率
    - 快速回滚到稳定版本
    """
    __tablename__ = "component_versions"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 组件标识
    component_name = Column(String(100), nullable=False, comment="组件名称(不含版本号): shopee/login")
    version = Column(String(20), nullable=False, comment="版本号: 1.0.0, 1.1.0")
    file_path = Column(String(200), nullable=False, comment="组件文件路径(相对路径)")
    
    # 状态标识
    is_stable = Column(Boolean, default=False, comment="是否为稳定版本")
    is_active = Column(Boolean, default=True, comment="是否启用(禁用的版本不会被加载)")
    is_testing = Column(Boolean, default=False, comment="是否在A/B测试中")
    
    # 统计信息
    usage_count = Column(Integer, default=0, comment="使用次数")
    success_count = Column(Integer, default=0, comment="成功次数")
    failure_count = Column(Integer, default=0, comment="失败次数")
    success_rate = Column(Float, default=0.0, comment="成功率(自动计算)")
    
    # A/B测试配置
    test_ratio = Column(Float, default=0.0, comment="测试流量比例(0.0-1.0)")
    test_start_at = Column(DateTime(timezone=True), nullable=True, comment="测试开始时间")
    test_end_at = Column(DateTime(timezone=True), nullable=True, comment="测试结束时间")
    
    # 元数据
    description = Column(Text, nullable=True, comment="版本说明")
    created_by = Column(String(100), nullable=True, comment="创建人")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        # 唯一约束:组件名+版本号唯一
        UniqueConstraint("component_name", "version", name="uq_component_version"),
        # 索引
        Index("ix_component_versions_name", "component_name"),
        Index("ix_component_versions_stable", "is_stable"),
        Index("ix_component_versions_success_rate", "success_rate"),
        {"schema": "core"},
    )

class ComponentTestHistory(Base):
    """
    组件测试历史记录表 (Phase 8.2 - 2025-12-17)
    
    用于存储组件测试的详细历史记录,包括每步执行情况
    
    使用场景:
    - 查看组件历史测试结果
    - 分析组件稳定性趋势
    - 定位失败原因和时间点
    - 支持测试结果对比
    """
    __tablename__ = "component_test_history"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String(36), unique=True, nullable=False, comment="测试唯一ID (UUID)")
    
    # 组件标识
    component_name = Column(String(100), nullable=False, comment="组件名称: shopee/login")
    component_version = Column(String(20), nullable=True, comment="组件版本号(如未指定则为临时组件)")
    version_id = Column(Integer, nullable=True, comment="关联的版本ID(外键)")
    
    # 测试配置
    platform = Column(String(50), nullable=False, comment="平台代码")
    account_id = Column(String(100), nullable=False, comment="测试账号ID")
    headless = Column(Boolean, default=False, comment="是否无头模式")
    
    # 测试结果
    status = Column(String(20), nullable=False, comment="测试状态: passed/failed/cancelled")
    duration_ms = Column(Integer, nullable=False, comment="总耗时(毫秒)")
    steps_total = Column(Integer, nullable=False, comment="总步骤数")
    steps_passed = Column(Integer, nullable=False, comment="成功步骤数")
    steps_failed = Column(Integer, nullable=False, comment="失败步骤数")
    success_rate = Column(Float, nullable=False, comment="成功率(0.0-1.0)")
    
    # 详细结果(JSON存储)
    step_results = Column(JSONB, nullable=False, comment="每步执行详情(action/status/duration/error)")
    error_message = Column(Text, nullable=True, comment="失败原因(如有)")
    
    # 环境信息
    browser_info = Column(JSONB, nullable=True, comment="浏览器信息(User-Agent等)")
    
    # 审计字段
    tested_by = Column(String(100), nullable=True, comment="测试人")
    tested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="测试时间")
    
    __table_args__ = (
        # 外键约束(可选)
        ForeignKeyConstraint(
            ["version_id"],
            ["core.component_versions.id"],
            name="fk_test_history_version",
            ondelete="SET NULL"
        ),
        # 索引
        Index("ix_test_history_component", "component_name"),
        Index("ix_test_history_status", "status"),
        Index("ix_test_history_tested_at", "tested_at"),
        Index("ix_test_history_version", "version_id"),
        {"schema": "core"},
    )
