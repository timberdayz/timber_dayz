#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Alembic环境配置

用于数据库迁移的环境设置，支持：
- 自动检测模型变更
- 环境变量配置
- 多数据库支持
- 安全的迁移执行
"""

import logging
from logging.config import fileConfig
from pathlib import Path
import sys
import os


from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入模型和配置
try:
    # 使用新的统一后端模型
    from backend.models.database import Base
    from backend.utils.config import get_settings
    
    # 获取配置
    settings = get_settings()
    secrets_manager = None  # 使用新的配置系统

except ImportError as e:
    print(f"警告: 无法导入模型或配置: {e}")
    Base = None
    settings = None
    secrets_manager = None

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata if Base else None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url():
    """获取数据库URL，优先使用环境变量 DATABASE_URL；否则使用配置"""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    if settings:
        return settings.DATABASE_URL
    # 默认回退
    return "sqlite:///data/erp_system.db"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 覆盖配置中的数据库URL
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
