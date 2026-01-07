#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态列管理服务（Dynamic Column Manager）

v4.14.0新增：
- 根据源文件表头动态添加列到PostgreSQL表
- 支持中文列名（TEXT类型）
- 处理列名冲突和列数限制
- 确保Metabase可以查询所有列

职责：
- 动态添加列到fact_raw_data_*表
- 查询表现有列
- 处理列名冲突（PostgreSQL列名限制）
- 处理列数限制（PostgreSQL列数限制1600列）
"""

from typing import List, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession  # ⭐ v4.18.2新增：异步支持
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError
import asyncio  # ⭐ v4.18.2新增：用于run_in_executor

from modules.core.logger import get_logger

logger = get_logger(__name__)

# PostgreSQL列名限制
MAX_COLUMN_NAME_LENGTH = 63  # PostgreSQL标识符最大长度
MAX_COLUMNS_PER_TABLE = 1600  # PostgreSQL建议的最大列数

# 系统保留字段（不能作为动态列）
SYSTEM_FIELDS = {
    'id', 'platform_code', 'shop_id', 'data_domain', 'granularity',
    'metric_date', 'file_id', 'raw_data', 'header_columns', 'data_hash',
    'ingest_timestamp', 'created_at', 'updated_at'
}


class DynamicColumnManager:
    """
    动态列管理服务
    
    功能：
    - 根据header_columns动态添加列到PostgreSQL表
    - 查询表现有列
    - 处理列名冲突和列数限制
    
    v4.18.2: 支持异步会话
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化动态列管理器
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
    
    def normalize_column_name(self, column_name: str) -> str:
        """
        规范化列名（符合PostgreSQL要求 + 移除货币代码）
        
        ⭐ v4.16.0增强：统一列名管理（最佳实践）
        - 先移除货币代码（防御性处理，避免创建包含货币代码的列）
        - 再进行PostgreSQL列名规范化（符合数据库标识符规则）
        
        这样可以确保：
        - 即使传入包含货币代码的列名（如 "销售 (SGD)"），也会创建归一化的列（"销售"）
        - 避免历史遗留问题（修复前创建的列不会重复创建）
        - 统一管理，性能高效（一次处理，后续复用）
        
        Args:
            column_name: 原始列名（可能包含中文、特殊字符、货币代码）
        
        Returns:
            规范化后的列名（符合PostgreSQL标识符规则，不包含货币代码）
        
        示例:
            normalize_column_name("销售 (SGD)") -> "销售"
            normalize_column_name("销售额_BRL") -> "销售额"
            normalize_column_name("销售R$") -> "销售"
        """
        # 如果列名已经是系统字段，直接返回
        if column_name in SYSTEM_FIELDS:
            return column_name
        
        # ⭐ v4.16.0新增：先移除货币代码（防御性处理）
        # 即使传入的列名已经归一化，这里也会再次处理，确保不会创建包含货币代码的列
        try:
            from backend.services.currency_extractor import get_currency_extractor
            currency_extractor = get_currency_extractor()
            # 移除货币代码（如 "销售 (SGD)" -> "销售"）
            column_name = currency_extractor.normalize_field_name(column_name)
        except Exception as e:
            # 如果货币提取器失败，记录警告但继续处理（不影响主流程）
            logger.warning(
                f"[DynamicColumn] 货币代码移除失败（继续处理）: {e}",
                exc_info=True
            )
        
        # PostgreSQL列名规范化（符合数据库标识符规则）
        # 替换特殊字符为下划线
        normalized = column_name.replace(' ', '_').replace('-', '_').replace('.', '_')
        normalized = ''.join(c if c.isalnum() or c == '_' else '_' for c in normalized)
        
        # 移除连续的下划线
        while '__' in normalized:
            normalized = normalized.replace('__', '_')
        
        # 移除开头和结尾的下划线
        normalized = normalized.strip('_')
        
        # 如果为空，使用默认名称
        if not normalized:
            normalized = 'col_' + str(hash(column_name) % 10000)
        
        # 截断到最大长度
        if len(normalized) > MAX_COLUMN_NAME_LENGTH:
            # 保留前50个字符 + 哈希值后8位
            hash_suffix = str(abs(hash(column_name)) % 100000000)[:8]
            normalized = normalized[:50] + '_' + hash_suffix
        
        # 确保不以数字开头（PostgreSQL要求）
        if normalized and normalized[0].isdigit():
            normalized = 'col_' + normalized
        
        return normalized
    
    def get_existing_columns(self, table_name: str) -> Set[str]:
        """
        查询表现有列
        
        Args:
            table_name: 表名（如 'fact_raw_data_orders_daily'）
        
        Returns:
            现有列名集合
        """
        try:
            # 使用SQLAlchemy的inspect功能查询表结构
            inspector = inspect(self.db.bind)
            columns = inspector.get_columns(table_name)
            column_names = {col['name'] for col in columns}
            
            logger.debug(f"[DynamicColumn] 表 {table_name} 现有列数: {len(column_names)}")
            return column_names
            
        except Exception as e:
            logger.error(f"[DynamicColumn] 查询表 {table_name} 列失败: {e}", exc_info=True)
            return set()
    
    def ensure_columns_exist(
        self,
        table_name: str,
        header_columns: List[str],
        max_new_columns: Optional[int] = None
    ) -> List[str]:
        """
        确保表中有指定的列（如果不存在则添加）
        
        Args:
            table_name: 表名（如 'fact_raw_data_orders_daily'）
            header_columns: 需要添加的列名列表（原始表头字段）
            max_new_columns: 最大新增列数（默认None，不限制）
        
        Returns:
            成功添加的列名列表（规范化后的列名）
        """
        if not header_columns:
            return []
        
        try:
            # 获取现有列
            existing_columns = self.get_existing_columns(table_name)
            
            # 规范化列名并去重
            normalized_columns = {}
            for col in header_columns:
                # 跳过系统字段
                if col in SYSTEM_FIELDS:
                    continue
                
                normalized = self.normalize_column_name(col)
                # 如果规范化后的列名已存在，跳过
                if normalized in existing_columns:
                    continue
                
                # 如果原始列名已映射，跳过（避免重复映射）
                if col in normalized_columns:
                    continue
                
                normalized_columns[col] = normalized
            
            # 检查列数限制
            total_columns = len(existing_columns) + len(normalized_columns)
            if total_columns > MAX_COLUMNS_PER_TABLE:
                # 限制新增列数
                if max_new_columns is None:
                    max_new_columns = MAX_COLUMNS_PER_TABLE - len(existing_columns)
                
                if max_new_columns <= 0:
                    logger.warning(
                        f"[DynamicColumn] 表 {table_name} 已达到最大列数限制 "
                        f"({MAX_COLUMNS_PER_TABLE})，无法添加新列"
                    )
                    return []
                
                # 只添加前max_new_columns个列
                normalized_columns = dict(list(normalized_columns.items())[:max_new_columns])
                logger.warning(
                    f"[DynamicColumn] 表 {table_name} 列数接近限制，"
                    f"只添加前 {max_new_columns} 个新列"
                )
            
            # 批量添加列
            added_columns = []
            for original_col, normalized_col in normalized_columns.items():
                try:
                    # 使用ALTER TABLE添加列（TEXT类型，支持中文数据）
                    alter_sql = text(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN IF NOT EXISTS "{normalized_col}" TEXT'
                    )
                    self.db.execute(alter_sql)
                    added_columns.append(normalized_col)
                    
                    logger.debug(
                        f"[DynamicColumn] 添加列: {table_name}.{normalized_col} "
                        f"(原始列名: {original_col})"
                    )
                    
                except ProgrammingError as e:
                    # 如果列已存在（并发情况），跳过
                    if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                        logger.debug(
                            f"[DynamicColumn] 列 {normalized_col} 已存在（并发添加），跳过"
                        )
                        continue
                    else:
                        logger.error(
                            f"[DynamicColumn] 添加列 {normalized_col} 失败: {e}",
                            exc_info=True
                        )
                        raise
            
            # 提交更改
            self.db.commit()
            
            if added_columns:
                logger.info(
                    f"[DynamicColumn] 表 {table_name} 成功添加 {len(added_columns)} 个新列"
                )
            
            return added_columns
            
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"[DynamicColumn] 确保列存在失败 (表={table_name}): {e}",
                exc_info=True
            )
            raise


def get_dynamic_column_manager(db: AsyncSession) -> DynamicColumnManager:
    """
    获取动态列管理服务实例
    
    ⭐ v4.18.2：支持异步会话
    ⭐ v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return DynamicColumnManager(db)


async def async_ensure_columns_exist(
    db: AsyncSession,
    table_name: str,
    header_columns: List[str],
    schema: str = 'b_class'
) -> List[str]:
    """
    异步确保列存在（⭐ v4.18.2新增，v4.19.0更新）
    
    ⭐ v4.19.0更新：统一为异步架构，使用run_in_executor将DDL操作包装为异步
    
    Args:
        db: 异步数据库会话（AsyncSession）
        table_name: 表名
        header_columns: 表头列名列表
        schema: 数据库schema
    
    Returns:
        新添加的列名列表
    """
    # ⭐ v4.19.0更新：统一使用run_in_executor包装DDL操作
    from backend.models.database import SessionLocal
    
    def _sync_ensure_columns():
        """同步执行DDL操作"""
        sync_db = SessionLocal()
        try:
            sync_manager = DynamicColumnManager(sync_db)
            return sync_manager.ensure_columns_exist(
                table_name=table_name,
                header_columns=header_columns,
                schema=schema
            )
        finally:
            sync_db.close()
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_ensure_columns)

