#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台表管理服务（Platform Table Manager）

v4.17.0新增：
- 根据文件元数据（platform + data_domain + sub_domain + granularity）动态创建表
- 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
- 表先于模板存在，模板只用于字段映射和动态列添加

职责：
- 表名生成（基于文件元数据）
- 表创建（基础结构）
- 表存在性检查
- 集成动态列管理（根据模板字段添加列）
"""

from typing import Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession  # [*] v4.18.2新增：异步支持
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError
import asyncio  # [*] v4.18.2新增：用于run_in_executor

from modules.core.logger import get_logger
from backend.services.dynamic_column_manager import get_dynamic_column_manager, SYSTEM_FIELDS

logger = get_logger(__name__)


class PlatformTableManager:
    """
    平台表管理服务
    
    职责：
    - 根据文件元数据创建表（如果不存在）
    - 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
    - 集成动态列管理（根据模板字段添加列）
    
    v4.18.2: 支持异步会话
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    - DDL操作通过run_in_executor在线程池中执行
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化平台表管理器
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
        self.dynamic_column_manager = get_dynamic_column_manager(db)
        # [*] v4.19.0更新：异步模式下不在构造函数中执行DDL，由调用者显式调用
    
    def _ensure_b_class_schema(self):
        """确保b_class schema存在"""
        try:
            self.db.execute(text("CREATE SCHEMA IF NOT EXISTS b_class"))
            self.db.commit()
            logger.debug("[PlatformTableManager] b_class schema已确保存在")
        except Exception as e:
            logger.warning(f"[PlatformTableManager] 确保b_class schema存在失败（可能已存在）: {e}")
            self.db.rollback()
    
    def get_table_name(
        self,
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
        granularity: str
    ) -> str:
        """
        生成表名：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
        
        规则：
        - sub_domain为空时，不包含sub_domain部分
        - 例如：fact_shopee_orders_daily（无sub_domain）
        - 例如：fact_shopee_services_ai_assistant_monthly（有sub_domain）
        
        Args:
            platform: 平台代码（shopee/tiktok/miaoshou）
            data_domain: 数据域（orders/products/services/analytics/inventory）
            sub_domain: 子类型（可选，services域有ai_assistant/agent）
            granularity: 粒度（daily/weekly/monthly/snapshot）
        
        Returns:
            表名
        """
        # [*] v4.17.0修复：验证platform不为空，避免表名错误（如fact__inventory_snapshot）
        platform = platform.lower().strip() if platform else "unknown"
        if not platform or platform == '':
            platform = "unknown"
            logger.warning(
                f"[PlatformTableManager] [WARN] platform为空，使用默认值: unknown "
                f"(data_domain={data_domain}, granularity={granularity})"
            )
        
        data_domain = data_domain.lower().strip() if data_domain else "unknown"
        granularity = granularity.lower().strip() if granularity else "daily"
        
        if sub_domain:
            sub_domain = sub_domain.lower().strip()
            return f"fact_{platform}_{data_domain}_{sub_domain}_{granularity}"
        else:
            return f"fact_{platform}_{data_domain}_{granularity}"
    
    def ensure_table_exists(
        self,
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
        granularity: str
    ) -> str:
        """
        确保表存在，如果不存在则创建（基础结构）
        
        调用时机：
        - 文件扫描注册时
        - 数据入库时（如果表不存在）
        
        Args:
            platform: 平台代码
            data_domain: 数据域
            sub_domain: 子类型（可选）
            granularity: 粒度
        
        Returns:
            表名
        """
        table_name = self.get_table_name(platform, data_domain, sub_domain, granularity)
        
        if not self._table_exists(table_name):
            logger.info(
                f"[PlatformTableManager] 创建新表: {table_name} "
                f"(platform={platform}, domain={data_domain}, "
                f"sub_domain={sub_domain or 'None'}, granularity={granularity})"
            )
            self._create_base_table(table_name, platform, data_domain, sub_domain, granularity)
        else:
            # [*] v4.18.1新增：表存在时，检查并补齐缺失的period列（兼容旧表）
            self._ensure_period_columns_exist(table_name)
            logger.debug(f"[PlatformTableManager] 表已存在: {table_name}")
        
        return table_name
    
    def sync_table_columns(
        self,
        table_name: str,
        header_columns: list,
        template_id: Optional[int] = None
    ) -> list:
        """
        同步表列（根据模板header_columns添加列）
        
        这是对DynamicColumnManager的封装，用于按平台分表场景
        
        Args:
            table_name: 表名
            header_columns: 表头字段列表（归一化后的，不含货币代码）
            template_id: 模板ID（可选，用于日志）
        
        Returns:
            新增的列列表
        """
        try:
            added_columns = self.dynamic_column_manager.ensure_columns_exist(
                table_name=table_name,
                header_columns=header_columns
            )
            
            if added_columns:
                logger.info(
                    f"[PlatformTableManager] 表 {table_name} "
                    f"新增 {len(added_columns)} 个动态列"
                    f"{f' (模板ID: {template_id})' if template_id else ''}"
                )
            
            return added_columns
        except Exception as e:
            logger.error(
                f"[PlatformTableManager] 同步表列失败 (表={table_name}): {e}",
                exc_info=True
            )
            # 失败不影响主流程（数据已通过raw_data JSONB存储）
            return []
    
    def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在（在b_class schema中）"""
        try:
            inspector = inspect(self.db.bind)
            return table_name in inspector.get_table_names(schema='b_class')
        except Exception as e:
            logger.error(f"[PlatformTableManager] 检查表存在性失败: {e}", exc_info=True)
            return False
    
    def _ensure_period_columns_exist(self, table_name: str):
        """
        v4.18.1修复：确保period相关的系统列存在
        
        对于在v4.18.0之前创建的表，需要补齐以下列：
        - period_start_date DATE NOT NULL (默认CURRENT_DATE)
        - period_end_date DATE NOT NULL (默认CURRENT_DATE)
        - period_start_time TIMESTAMP (可选)
        - period_end_time TIMESTAMP (可选)
        """
        try:
            # 检查列是否存在
            check_column_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'b_class' 
                AND table_name = :table_name
                AND column_name IN ('period_start_date', 'period_end_date', 'period_start_time', 'period_end_time')
            """)
            existing_columns = {row[0] for row in self.db.execute(check_column_sql, {'table_name': table_name}).fetchall()}
            
            # 需要添加的列
            columns_to_add = []
            if 'period_start_date' not in existing_columns:
                columns_to_add.append(('period_start_date', 'DATE', 'CURRENT_DATE'))
            if 'period_end_date' not in existing_columns:
                columns_to_add.append(('period_end_date', 'DATE', 'CURRENT_DATE'))
            if 'period_start_time' not in existing_columns:
                columns_to_add.append(('period_start_time', 'TIMESTAMP', None))
            if 'period_end_time' not in existing_columns:
                columns_to_add.append(('period_end_time', 'TIMESTAMP', None))
            
            if not columns_to_add:
                return  # 所有列已存在
            
            logger.info(
                f"[PlatformTableManager] [v4.18.1] 表 {table_name} 需要补齐 {len(columns_to_add)} 个period列: "
                f"{[c[0] for c in columns_to_add]}"
            )
            
            # 添加缺失的列
            for col_name, col_type, default_value in columns_to_add:
                try:
                    if default_value:
                        # DATE类型需要默认值（用于已有数据）
                        alter_sql = text(f'''
                            ALTER TABLE b_class."{table_name}" 
                            ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT {default_value}
                        ''')
                    else:
                        alter_sql = text(f'''
                            ALTER TABLE b_class."{table_name}" 
                            ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                        ''')
                    self.db.execute(alter_sql)
                    logger.info(f"[PlatformTableManager] [v4.18.1] 添加列 {col_name} 到表 {table_name}")
                except Exception as e:
                    logger.warning(f"[PlatformTableManager] [v4.18.1] 添加列 {col_name} 失败（可能已存在）: {e}")
            
            # 创建索引（如果不存在）
            try:
                index_sql = text(f'''
                    CREATE INDEX IF NOT EXISTS "ix_{table_name}_period_date" 
                    ON b_class."{table_name}" (period_start_date, period_end_date)
                ''')
                self.db.execute(index_sql)
            except Exception as e:
                logger.warning(f"[PlatformTableManager] [v4.18.1] 创建period索引失败（可能已存在）: {e}")
            
            self.db.commit()
            logger.info(f"[PlatformTableManager] [v4.18.1] 表 {table_name} period列补齐完成")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[PlatformTableManager] [v4.18.1] 补齐period列失败: {e}", exc_info=True)
    
    def _create_base_table(
        self,
        table_name: str,
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
        granularity: str
    ):
        """
        创建基础表结构（系统字段）
        
        表结构：
        - 系统字段：id, platform_code, shop_id, data_domain, granularity, sub_domain,
                    metric_date, file_id, template_id, raw_data, header_columns,
                    data_hash, ingest_timestamp, currency_code
        - 动态列：根据模板字段动态添加（通过sync_table_columns方法）
        """
        try:
            # 构建CREATE TABLE SQL
            # [*] 注意：services域的表需要sub_domain字段，其他域sub_domain可为NULL
            sub_domain_column = ""
            if data_domain.lower() == 'services':
                # services域必须提供sub_domain
                sub_domain_column = "sub_domain VARCHAR(64) NOT NULL,"
            else:
                # 其他域sub_domain可为NULL
                sub_domain_column = "sub_domain VARCHAR(64),"
            
            # v4.18.0: 添加period_start_date, period_end_date, period_start_time, period_end_time字段
            # 用于支持日期范围数据（如周度/月度数据）和精确时间查询
            create_table_sql = text(f"""
                CREATE TABLE IF NOT EXISTS b_class."{table_name}" (
                    id BIGSERIAL PRIMARY KEY,
                    platform_code VARCHAR(32) NOT NULL,
                    shop_id VARCHAR(256),
                    data_domain VARCHAR(64) NOT NULL DEFAULT '{data_domain}',
                    granularity VARCHAR(32) NOT NULL DEFAULT '{granularity}',
                    {sub_domain_column}
                    metric_date DATE NOT NULL,
                    period_start_date DATE NOT NULL,
                    period_end_date DATE NOT NULL,
                    period_start_time TIMESTAMP,
                    period_end_time TIMESTAMP,
                    file_id INTEGER REFERENCES catalog_files(id) ON DELETE SET NULL,
                    template_id INTEGER REFERENCES field_mapping_templates(id) ON DELETE SET NULL,
                    raw_data JSONB NOT NULL,
                    header_columns JSONB,
                    data_hash VARCHAR(64) NOT NULL,
                    ingest_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                    currency_code VARCHAR(3)
                )
            """)
            
            self.db.execute(create_table_sql)
            
            # 创建唯一索引（使用COALESCE处理NULL值）
            # [WARN] PostgreSQL的UNIQUE约束不支持表达式，需要使用唯一索引
            if data_domain.lower() == 'services':
                unique_index_sql = text(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table_name}_hash" 
                    ON b_class."{table_name}" (data_domain, sub_domain, granularity, data_hash)
                """)
            else:
                unique_index_sql = text(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table_name}_hash" 
                    ON b_class."{table_name}" (platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)
                """)
            
            self.db.execute(unique_index_sql)
            
            # 创建其他索引（在b_class schema中）
            indexes_sql = [
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_platform" ON b_class."{table_name}" (platform_code)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_shop" ON b_class."{table_name}" (shop_id)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_domain" ON b_class."{table_name}" (data_domain)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_granularity" ON b_class."{table_name}" (granularity)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_date" ON b_class."{table_name}" (metric_date)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_file" ON b_class."{table_name}" (file_id)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_hash" ON b_class."{table_name}" (data_hash)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_currency" ON b_class."{table_name}" (currency_code)'),
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_gin" ON b_class."{table_name}" USING GIN (raw_data)'),
                # v4.18.0: 日期范围索引（所有记录）
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_period_date" ON b_class."{table_name}" (period_start_date, period_end_date)'),
                # v4.18.0: 时间范围索引（部分索引，仅索引有时间信息的记录）
                text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_period_time" ON b_class."{table_name}" (period_start_time, period_end_time) WHERE period_start_time IS NOT NULL'),
            ]
            
            # services域的表需要sub_domain索引
            if data_domain.lower() == 'services' and sub_domain:
                indexes_sql.append(
                    text(f'CREATE INDEX IF NOT EXISTS "ix_{table_name}_sub_domain" ON b_class."{table_name}" (sub_domain)')
                )
            
            for index_sql in indexes_sql:
                try:
                    self.db.execute(index_sql)
                except Exception as e:
                    logger.warning(f"[PlatformTableManager] 创建索引失败（继续）: {e}")
            
            self.db.commit()
            
            # [*] v4.17.0修复：索引创建后，显式刷新统计信息，确保索引立即可用
            # 这对于表达式索引特别重要，确保ON CONFLICT能正确匹配
            try:
                refresh_stats_sql = text(f'ANALYZE b_class."{table_name}"')
                self.db.execute(refresh_stats_sql)
                self.db.commit()
                logger.debug(
                    f"[PlatformTableManager] [v4.17.0] 已刷新表统计信息: {table_name}"
                )
            except Exception as e:
                logger.warning(
                    f"[PlatformTableManager] [v4.17.0] 刷新统计信息失败（继续）: {e}"
                )
                # 刷新统计信息失败不影响主流程
            
            logger.info(
                f"[PlatformTableManager] 成功创建表: {table_name} "
                f"（包含基础字段和索引）"
            )
            
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"[PlatformTableManager] 创建表失败 (表={table_name}): {e}",
                exc_info=True
            )
            raise


def get_platform_table_manager(db: AsyncSession) -> PlatformTableManager:
    """
    获取平台表管理服务实例
    
    [*] v4.18.2：支持异步会话
    [*] v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return PlatformTableManager(db)


async def async_ensure_table_exists(
    db: AsyncSession,
    platform: str,
    data_domain: str,
    sub_domain: Optional[str],
    granularity: str,
    business_fields: Optional[Set[str]] = None
) -> str:
    """
    异步确保表存在（[*] v4.18.2新增，v4.19.0更新）
    
    [*] v4.19.0更新：统一为异步架构，使用run_in_executor将DDL操作包装为异步
    
    Args:
        db: 异步数据库会话（AsyncSession）
        platform: 平台代码
        data_domain: 数据域
        sub_domain: 子类型
        granularity: 粒度
        business_fields: 业务字段集合
    
    Returns:
        表名
    """
    # [*] v4.19.0更新：统一使用run_in_executor包装DDL操作
    from backend.models.database import SessionLocal
    
    def _sync_ensure_table():
        """同步执行DDL操作"""
        sync_db = SessionLocal()
        try:
            sync_manager = PlatformTableManager(sync_db)
            return sync_manager.ensure_table_exists(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity,
                business_fields=business_fields
            )
        finally:
            sync_db.close()
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_ensure_table)

