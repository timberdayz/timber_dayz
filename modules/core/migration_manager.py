#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库迁移管理器

提供数据库版本管理和迁移功能：
- Alembic集成
- 自动迁移检查
- 安全的升级/降级
- 迁移状态监控
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.runtime.environment import EnvironmentContext
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from .logger import get_logger
from .secrets_manager import get_secrets_manager
from .exceptions import ERPException

logger = get_logger(__name__)


class MigrationError(ERPException):
    """迁移错误"""
    pass


class MigrationManager:
    """数据库迁移管理器"""
    
    def __init__(self, alembic_ini_path: str = "alembic.ini"):
        """
        初始化迁移管理器
        
        Args:
            alembic_ini_path: Alembic配置文件路径
        """
        self.project_root = Path.cwd()
        self.alembic_ini_path = self.project_root / alembic_ini_path
        self.secrets_manager = get_secrets_manager()
        
        if not self.alembic_ini_path.exists():
            raise MigrationError(f"Alembic配置文件不存在: {self.alembic_ini_path}")
        
        self.alembic_cfg = Config(str(self.alembic_ini_path))
        
        # 设置数据库URL
        db_url = self._get_database_url()
        self.alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        
    def _get_database_url(self) -> str:
        """获取数据库URL。优先使用环境变量 DATABASE_URL；否则回退到统一的SQLite路径"""
        url = os.getenv("DATABASE_URL")
        if url:
            return url
        db_path = self.secrets_manager.get_unified_database_path()
        return f"sqlite:///{db_path}"

    def get_current_revision(self) -> Optional[str]:
        """
        获取当前数据库版本
        
        Returns:
            Optional[str]: 当前版本ID，如果数据库未初始化则返回None
        """
        try:
            engine = create_engine(self._get_database_url())
            
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                current_rev = context.get_current_revision()
                
            return current_rev
            
        except Exception as e:
            logger.warning(f"获取当前版本失败: {e}")
            return None
    
    def get_head_revision(self) -> Optional[str]:
        """
        获取最新版本
        
        Returns:
            Optional[str]: 最新版本ID
        """
        try:
            script = ScriptDirectory.from_config(self.alembic_cfg)
            head_rev = script.get_current_head()
            return head_rev
            
        except Exception as e:
            logger.error(f"获取最新版本失败: {e}")
            return None
    
    def get_migration_status(self) -> Dict[str, any]:
        """
        获取迁移状态
        
        Returns:
            Dict[str, any]: 迁移状态信息
        """
        current_rev = self.get_current_revision()
        head_rev = self.get_head_revision()
        
        status = {
            'current_revision': current_rev,
            'head_revision': head_rev,
            'is_up_to_date': current_rev == head_rev,
            'needs_migration': current_rev != head_rev,
            'database_exists': current_rev is not None
        }
        
        # 获取待执行的迁移
        if current_rev and head_rev and current_rev != head_rev:
            try:
                script = ScriptDirectory.from_config(self.alembic_cfg)
                pending_migrations = []
                
                for revision in script.walk_revisions(head_rev, current_rev):
                    if revision.revision != current_rev:
                        pending_migrations.append({
                            'revision': revision.revision,
                            'message': revision.doc,
                            'down_revision': revision.down_revision
                        })
                
                status['pending_migrations'] = pending_migrations
                status['pending_count'] = len(pending_migrations)
                
            except Exception as e:
                logger.warning(f"获取待执行迁移失败: {e}")
                status['pending_migrations'] = []
                status['pending_count'] = 0
        else:
            status['pending_migrations'] = []
            status['pending_count'] = 0
        
        return status
    
    def check_migration_needed(self) -> bool:
        """
        检查是否需要迁移
        
        Returns:
            bool: 是否需要迁移
        """
        status = self.get_migration_status()
        return status['needs_migration']
    
    def upgrade_database(self, revision: str = "head") -> bool:
        """
        升级数据库
        
        Args:
            revision: 目标版本，默认为最新版本
            
        Returns:
            bool: 升级是否成功
        """
        try:
            logger.info(f"开始升级数据库到版本: {revision}")
            
            # 确保数据目录存在
            db_path = self.secrets_manager.get_unified_database_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 执行升级
            command.upgrade(self.alembic_cfg, revision)
            
            logger.info("数据库升级完成")
            return True
            
        except Exception as e:
            logger.error(f"数据库升级失败: {e}")
            raise MigrationError(f"数据库升级失败: {e}")
    
    def downgrade_database(self, revision: str) -> bool:
        """
        降级数据库
        
        Args:
            revision: 目标版本
            
        Returns:
            bool: 降级是否成功
        """
        try:
            logger.info(f"开始降级数据库到版本: {revision}")
            
            command.downgrade(self.alembic_cfg, revision)
            
            logger.info("数据库降级完成")
            return True
            
        except Exception as e:
            logger.error(f"数据库降级失败: {e}")
            raise MigrationError(f"数据库降级失败: {e}")
    
    def create_migration(self, message: str, autogenerate: bool = True) -> str:
        """
        创建新的迁移文件
        
        Args:
            message: 迁移描述
            autogenerate: 是否自动生成迁移内容
            
        Returns:
            str: 新迁移的版本ID
        """
        try:
            logger.info(f"创建新迁移: {message}")
            
            # 创建迁移
            revision = command.revision(
                self.alembic_cfg,
                message=message,
                autogenerate=autogenerate
            )
            
            logger.info(f"迁移创建完成: {revision.revision}")
            return revision.revision
            
        except Exception as e:
            logger.error(f"创建迁移失败: {e}")
            raise MigrationError(f"创建迁移失败: {e}")
    
    def get_migration_history(self) -> List[Dict[str, any]]:
        """
        获取迁移历史
        
        Returns:
            List[Dict[str, any]]: 迁移历史列表
        """
        try:
            script = ScriptDirectory.from_config(self.alembic_cfg)
            history = []
            
            for revision in script.walk_revisions():
                history.append({
                    'revision': revision.revision,
                    'down_revision': revision.down_revision,
                    'message': revision.doc,
                    'branch_labels': revision.branch_labels,
                    'depends_on': revision.depends_on
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取迁移历史失败: {e}")
            return []
    
    def validate_database_schema(self) -> bool:
        """
        验证数据库结构
        
        Returns:
            bool: 验证是否通过
        """
        try:
            engine = create_engine(self._get_database_url())
            
            with engine.connect() as connection:
                # 检查关键表是否存在
                result = connection.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ))
                tables = [row[0] for row in result]
                
                # 检查Alembic版本表
                if 'alembic_version' not in tables:
                    logger.warning("数据库未初始化或缺少版本信息")
                    return False
                
                logger.info(f"数据库包含 {len(tables)} 个表")
                return True
                
        except Exception as e:
            logger.error(f"数据库结构验证失败: {e}")
            return False
    
    def auto_migrate_if_needed(self) -> bool:
        """
        如果需要则自动迁移
        
        Returns:
            bool: 是否执行了迁移
        """
        status = self.get_migration_status()
        
        if not status['database_exists']:
            logger.info("数据库未初始化，执行初始化迁移")
            self.upgrade_database()
            return True
        elif status['needs_migration']:
            logger.info(f"发现 {status['pending_count']} 个待执行迁移")
            self.upgrade_database()
            return True
        else:
            logger.debug("数据库已是最新版本")
            return False


# 全局迁移管理器实例
_migration_manager = None


def get_migration_manager() -> MigrationManager:
    """获取全局迁移管理器实例"""
    global _migration_manager
    if _migration_manager is None:
        _migration_manager = MigrationManager()
    return _migration_manager


def auto_migrate() -> bool:
    """自动迁移的便捷函数"""
    manager = get_migration_manager()
    return manager.auto_migrate_if_needed()


def check_migration_status() -> Dict[str, any]:
    """检查迁移状态的便捷函数"""
    manager = get_migration_manager()
    return manager.get_migration_status()
