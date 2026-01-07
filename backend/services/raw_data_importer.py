#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B类数据入库服务（Raw Data Importer）

v4.6.0新增：
- 将数据写入新的B类数据表（fact_raw_data_{domain}_{granularity}）
- 支持JSONB格式存储（中文字段名作为键）
- 使用ON CONFLICT自动去重
- 批量插入优化

职责：
- 根据data_domain+granularity选择目标表
- 批量插入数据到对应的fact_raw_data表
- 处理ON CONFLICT去重
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, insert, select, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from datetime import datetime, date
import json
import asyncio
from modules.core.db import (
    CatalogFile,
)
from modules.core.logger import get_logger
from backend.services.executor_manager import get_executor_manager  # v4.19.0新增：使用统一执行器管理器

from backend.services.dynamic_column_manager import get_dynamic_column_manager
from backend.services.deduplication_fields_config import (  # ⭐ v4.15.0新增
    get_deduplication_strategy,
    get_upsert_update_fields
)
from backend.services.platform_table_manager import get_platform_table_manager  # ⭐ v4.17.0新增

logger = get_logger(__name__)


class RawDataImporter:
    """
    B类数据入库服务（v4.17.0重构：按平台分表）
    
    功能：
    - 根据platform+data_domain+granularity+sub_domain动态生成表名
    - 批量插入数据（使用ON CONFLICT自动去重）
    - 支持JSONB格式存储
    - 支持动态列管理（根据模板字段添加列）
    
    v4.18.2更新：支持异步会话
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    - 使用run_in_executor包装同步批量操作
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化原始数据导入器
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
        self.table_manager = get_platform_table_manager(db)
    
    def get_target_table_name(
        self,
        platform: str,
        data_domain: str,
        granularity: str,
        sub_domain: Optional[str] = None
    ) -> str:
        """
        获取目标表名（动态生成）
        
        ⭐ v4.17.0重构：从固定表映射改为动态表名生成
        表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
        
        Args:
            platform: 平台代码（shopee/tiktok/miaoshou）
            data_domain: 数据域
            granularity: 粒度
            sub_domain: 子类型（可选，services域必须提供：ai_assistant或agent）
        
        Returns:
            表名字符串
        """
        return self.table_manager.get_table_name(platform, data_domain, sub_domain, granularity)
    
    def extract_metric_date(self, row: Dict[str, Any], header_columns: List[str]) -> Optional[date]:
        """
        从数据行中提取metric_date
        
        尝试从以下字段提取：
        - 日期、日期字段、metric_date、order_date等
        - 如果找不到，返回None（将由调用方设置默认值）
        """
        # 常见日期字段名（中英文）
        date_field_candidates = [
            '日期', 'date', 'metric_date', 'order_date', '下单日期',
            '订单日期', 'data_date', '统计日期', '时间', 'time'
        ]
        
        for field in date_field_candidates:
            # 尝试原始字段名
            if field in row and row[field]:
                try:
                    date_value = row[field]
                    if isinstance(date_value, date):
                        return date_value
                    elif isinstance(date_value, datetime):
                        return date_value.date()
                    elif isinstance(date_value, str):
                        # 尝试解析日期字符串
                        from dateutil.parser import parse
                        parsed = parse(date_value)
                        return parsed.date()
                except Exception:
                    continue
            
            # 尝试header_columns中的字段（中文表头）
            for header_col in header_columns:
                if field.lower() in header_col.lower() or header_col.lower() in field.lower():
                    if header_col in row and row[header_col]:
                        try:
                            date_value = row[header_col]
                            if isinstance(date_value, date):
                                return date_value
                            elif isinstance(date_value, datetime):
                                return date_value.date()
                            elif isinstance(date_value, str):
                                from dateutil.parser import parse
                                parsed = parse(date_value)
                                return parsed.date()
                        except Exception:
                            continue
        
        return None
    
    def extract_period_dates(self, row: Dict[str, Any], header_columns: List[str]) -> tuple:
        """
        v4.18.0新增：从数据行中提取period_start_date、period_end_date、period_start_time、period_end_time
        
        支持的格式：
        - 单日期：2025-09-17 → (2025-09-17, 2025-09-17, None, None)
        - 日期范围：16/09/2025 - 20/09/2025 → (2025-09-16, 2025-09-20, None, None)
        - 日期时间范围：2025-08-25 17:01~2025-08-26 11:02 → (2025-08-25, 2025-08-26, datetime, datetime)
        - 反斜杠格式：19\\9\\25 → (2019-09-25, 2019-09-25, None, None)
        
        Returns:
            (start_date, end_date, start_time, end_time)
            - start_date/end_date: 总是返回（DATE类型），如果解析失败返回None
            - start_time/end_time: 如果数据包含时间则返回（TIMESTAMP类型），否则返回None
        """
        import re
        
        # 日期字段候选（包含日期期间）
        date_field_candidates = [
            '日期期间', 'date_period', 'period', '日期范围', 'date_range',
            '日期', 'date', 'metric_date', 'order_date', '下单日期',
            '订单日期', 'data_date', '统计日期', '时间', 'time'
        ]
        
        # 尝试从row中查找日期字段
        for field in date_field_candidates:
            # 精确匹配
            if field in row and row[field]:
                result = self._parse_date_range_value(row[field])
                if result and result[0]:
                    return result
            
            # 模糊匹配（字段名包含关键词）
            for key in row.keys():
                if field.lower() in key.lower() or key.lower() in field.lower():
                    if row[key]:
                        result = self._parse_date_range_value(row[key])
                        if result and result[0]:
                            return result
            
            # 尝试header_columns中的字段
            for header_col in header_columns:
                if field.lower() in header_col.lower() or header_col.lower() in field.lower():
                    if header_col in row and row[header_col]:
                        result = self._parse_date_range_value(row[header_col])
                        if result and result[0]:
                            return result
        
        return (None, None, None, None)
    
    def _parse_date_range_value(self, value: Any) -> tuple:
        """
        解析日期范围值
        
        返回：(start_date, end_date, start_time, end_time)
        """
        import re
        
        if value is None:
            return (None, None, None, None)
        
        # 如果是date/datetime对象
        if isinstance(value, date) and not isinstance(value, datetime):
            return (value, value, None, None)
        if isinstance(value, datetime):
            return (value.date(), value.date(), value, value)
        
        if not isinstance(value, str):
            return (None, None, None, None)
        
        s = str(value).strip()
        if not s:
            return (None, None, None, None)
        
        # 标准化：将反斜杠替换为斜杠
        s = s.replace('\\', '/')
        
        # 检测是否为日期范围（包含分隔符）
        range_separators = [' - ', '~', ' 至 ', ' to ', ' 到 ']
        for sep in range_separators:
            if sep in s:
                parts = s.split(sep, 1)
                if len(parts) == 2:
                    start_str, end_str = parts[0].strip(), parts[1].strip()
                    start_date, start_time = self._parse_single_date_value(start_str)
                    end_date, end_time = self._parse_single_date_value(end_str)
                    if start_date and end_date:
                        return (start_date, end_date, start_time, end_time)
        
        # 单日期格式
        parsed_date, parsed_time = self._parse_single_date_value(s)
        if parsed_date:
            return (parsed_date, parsed_date, parsed_time, parsed_time)
        
        return (None, None, None, None)
    
    def _parse_single_date_value(self, value: str) -> tuple:
        """
        解析单个日期值
        
        返回：(date_obj, datetime_obj_or_none)
        - date_obj: 日期对象
        - datetime_obj: 如果包含时间则返回datetime，否则返回None
        """
        import re
        
        if not value:
            return (None, None)
        
        s = str(value).strip()
        if not s:
            return (None, None)
        
        # 标准化：将反斜杠替换为斜杠
        s = s.replace('\\', '/')
        
        # 检测是否包含时间（HH:MM 或 HH:MM:SS）
        time_pattern = r'(\d{1,2}:\d{2}(?::\d{2})?)'
        time_match = re.search(time_pattern, s)
        has_time = time_match is not None
        
        # 提取日期部分（移除时间）
        date_str = s
        time_str = None
        if has_time:
            # 尝试提取日期部分
            # 格式1：2025-09-17 19:27:25 或 2025/09/17 19:27:25
            datetime_match = re.match(r'^(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})\s*[/\s]*(\d{1,2}:\d{2}(?::\d{2})?)', s)
            if datetime_match:
                date_str = datetime_match.group(1)
                time_str = datetime_match.group(2)
            else:
                # 格式2：19/9/25/19:27:25（反斜杠分隔日期和时间）
                parts = s.rsplit('/', 1)
                if len(parts) == 2 and ':' in parts[1]:
                    date_str = parts[0]
                    time_str = parts[1]
        
        # 解析日期
        parsed_date = self._parse_date_only(date_str)
        
        # 如果包含时间，解析完整的datetime
        parsed_datetime = None
        if parsed_date and has_time and time_str:
            try:
                from dateutil.parser import parse as dateutil_parse
                # 组合日期和时间
                datetime_str = f"{parsed_date.isoformat()} {time_str}"
                parsed_datetime = dateutil_parse(datetime_str)
            except Exception:
                pass
        
        return (parsed_date, parsed_datetime)
    
    def _parse_date_only(self, value: str) -> Optional[date]:
        """
        解析纯日期字符串（不含时间）
        
        支持格式：
        - 标准格式：2025-09-17, 17/09/2025, 09/17/2025
        - 短格式：19/9/25（自动推断年份）
        - Excel序列号
        """
        import re
        
        if not value:
            return None
        
        s = str(value).strip()
        if not s:
            return None
        
        # 标准化：将反斜杠替换为斜杠
        s = s.replace('\\', '/')
        
        # 尝试使用现有的smart_date_parser
        try:
            from modules.services.smart_date_parser import parse_date as smart_parse_date
            parsed = smart_parse_date(s, prefer_dayfirst=True)
            if parsed:
                return parsed
        except Exception:
            pass
        
        # 处理短格式日期（如 19/9/25）
        short_date_match = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{1,2})$', s)
        if short_date_match:
            a, b, c = short_date_match.groups()
            a, b, c = int(a), int(b), int(c)
            
            # 推断年份和日期格式
            current_year = date.today().year
            
            # 尝试 DD/MM/YY 格式
            try:
                year = c
                if year < 100:
                    year = 2000 + year if year < 50 else 1900 + year
                parsed = date(year, b, a)
                if parsed.year <= current_year + 1:  # 合理范围内
                    return parsed
            except ValueError:
                pass
            
            # 尝试 YY/MM/DD 格式
            try:
                year = a
                if year < 100:
                    year = 2000 + year if year < 50 else 1900 + year
                parsed = date(year, b, c)
                if parsed.year <= current_year + 1:
                    return parsed
            except ValueError:
                pass
        
        # 最后尝试使用dateutil
        try:
            from dateutil.parser import parse as dateutil_parse
            parsed = dateutil_parse(s, dayfirst=True)
            return parsed.date()
        except Exception:
            pass
        
        return None
    
    def batch_insert_raw_data(
        self,
        rows: List[Dict[str, Any]],
        data_hashes: List[str],
        data_domain: str,
        granularity: str,
        platform_code: str,
        shop_id: Optional[str] = None,
        file_id: Optional[int] = None,
        header_columns: Optional[List[str]] = None,  # ⭐ v4.16.0更新：归一化的header_columns（用于动态列管理）
        currency_codes: Optional[List[Optional[str]]] = None,  # ⭐ v4.15.0新增：货币代码列表
        sub_domain: Optional[str] = None,  # ⭐ v4.16.0新增：子类型（services域必须提供）
        original_header_columns: Optional[List[str]] = None,  # ⭐ v4.16.0新增：原始header_columns（包含货币代码，用于保存到数据库）
        template_id: Optional[int] = None  # ⭐ v4.17.0新增：模板ID（用于动态列管理）
    ) -> Dict[str, int]:  # ⭐ v4.15.0修改：返回详细统计信息
        """
        批量插入B类数据（v4.17.0重构：按平台分表）
        
        Args:
            rows: 数据行列表（原始数据，中文字段名作为键）
            data_hashes: 数据哈希列表（与rows对应）
            data_domain: 数据域
            granularity: 粒度
            platform_code: 平台代码（必填，用于生成表名）
            shop_id: 店铺ID（可选）
            file_id: 文件ID（可选）
            header_columns: 归一化的表头字段列表（用于动态列管理）
            currency_codes: 货币代码列表
            sub_domain: 子类型（可选，services域必须提供：ai_assistant或agent）
            original_header_columns: 原始表头字段列表（包含货币代码，用于保存到数据库）
            template_id: 模板ID（可选，用于动态列管理）
        
        Returns:
            详细统计信息字典
        """
        if not rows:
            return {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        try:
            # ⭐ v4.17.0重构：使用动态表名（基于平台+数据域+粒度+子类型）
            # 确保表存在（如果不存在则创建）
            table_name = self.table_manager.ensure_table_exists(
                platform=platform_code,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity
            )
            
            # ⭐ v4.17.0新增：根据模板同步表列（如果提供了header_columns）
            if header_columns:
                self.table_manager.sync_table_columns(
                    table_name=table_name,
                    header_columns=header_columns,
                    template_id=template_id
                )
            
            # 准备插入数据
            insert_data = []
            for i, (row, data_hash) in enumerate(zip(rows, data_hashes)):
                # ⭐ v4.18.0增强：提取period_start_date/end_date和period_start_time/end_time
                period_start_date, period_end_date, period_start_time, period_end_time = \
                    self.extract_period_dates(row, header_columns or [])
                
                # 如果无法提取日期，使用今天作为默认值
                if not period_start_date:
                    period_start_date = date.today()
                    period_end_date = date.today()
                    logger.warning(
                        f"[RawDataImporter] 无法提取period日期，使用默认值: {period_start_date}"
                    )
                
                # 向后兼容：metric_date使用period_start_date
                metric_date = period_start_date
                
                # ⭐ v4.15.0新增：获取货币代码
                currency_code = None
                if currency_codes and i < len(currency_codes):
                    currency_code = currency_codes[i]
                
                # 准备插入记录
                # ⭐ v4.16.0修复：header_columns字段保存原始列名（包含货币代码）用于追溯
                # 但动态列管理使用归一化的列名（避免创建重复列）
                header_columns_for_storage = original_header_columns if original_header_columns else header_columns
                
                insert_record = {
                    'platform_code': platform_code,
                    'shop_id': shop_id,
                    'data_domain': data_domain,
                    'granularity': granularity,
                    'metric_date': metric_date,
                    'period_start_date': period_start_date,  # ⭐ v4.18.0新增
                    'period_end_date': period_end_date,      # ⭐ v4.18.0新增
                    'period_start_time': period_start_time,  # ⭐ v4.18.0新增（可为None）
                    'period_end_time': period_end_time,      # ⭐ v4.18.0新增（可为None）
                    'file_id': file_id,
                    'raw_data': row,  # JSONB格式，中文字段名作为键（已归一化，不含货币代码）
                    'header_columns': header_columns_for_storage,  # ⭐ v4.16.0修复：保存原始字段名（含货币代码）用于追溯
                    'data_hash': data_hash,
                    'ingest_timestamp': datetime.utcnow(),
                    'currency_code': currency_code  # ⭐ v4.15.0新增：货币代码
                }
                
                # ⭐ v4.16.0新增：services域的表需要sub_domain字段
                if data_domain.lower() == 'services' and sub_domain:
                    insert_record['sub_domain'] = sub_domain.lower()
                
                insert_data.append(insert_record)
            
            # ⭐ v4.14.0新增：动态列管理（确保源数据表头字段作为列存在）
            # ⭐ v4.17.0重构：table_name已在前面从table_manager获取，这里直接使用
            # 注意：动态列管理已集成到table_manager.sync_table_columns中，这里保留作为备用
            if header_columns:
                try:
                    dynamic_column_manager = get_dynamic_column_manager(self.db)
                    # table_name已在前面从table_manager获取
                    
                    # 确保列存在（动态添加列）
                    added_columns = dynamic_column_manager.ensure_columns_exist(
                        table_name=table_name,
                        header_columns=header_columns
                    )
                    
                    if added_columns:
                        logger.info(
                            f"[RawDataImporter] [v4.14.0] 动态添加列: {len(added_columns)}个 "
                            f"（表={table_name}）"
                        )
                except Exception as e:
                    logger.error(
                        f"[RawDataImporter] [v4.14.0] 动态列管理失败: {e}",
                        exc_info=True
                    )
                    # 动态列管理失败不影响数据入库（继续使用raw_data JSONB）
            
            # ⭐ v4.14.0修复：不要在这里填充动态列
            # 原因：SQLAlchemy ORM模型不包含动态列，会导致"Unconsumed column names"错误
            # 解决方案：先使用ORM插入系统字段，然后使用原始SQL更新动态列
            # 动态列的填充将在后面的UPDATE语句中完成
            
            # ⭐ v4.15.0增强：插入前查询已存在的data_hash（用于区分INSERT和UPDATE）
            # 获取去重策略
            strategy = get_deduplication_strategy(data_domain)
            is_upsert = (strategy == 'UPSERT')
            
            # 查询已存在的data_hash（仅UPSERT策略需要）
            existing_hashes = set()
            if is_upsert:
                # ⭐ v4.17.0修复：确保在查询existing_hashes之前，前一个事务已提交
                # 显式刷新事务状态，确保能看到已提交的数据
                try:
                    self.db.commit()  # 如果当前有未提交的事务，先提交
                    logger.debug(
                        f"[RawDataImporter] [v4.17.0] 提交前一个事务，确保existing_hashes查询能看到已提交的数据"
                    )
                except Exception as e:
                    # 如果没有未提交的事务，忽略错误
                    logger.debug(
                        f"[RawDataImporter] [v4.17.0] 前一个事务已提交或无事务: {e}"
                    )
                
                # ⭐ v4.17.0修复：先检查索引类型，以便使用正确的查询条件
                new_index_name = f"uq_{table_name}_hash"
                is_expression_index_for_query = False
                try:
                    check_index_def_sql = text(
                        f"SELECT indexdef FROM pg_indexes "
                        f"WHERE indexname = '{new_index_name}' AND schemaname = 'b_class'"
                    )
                    index_def = self.db.execute(check_index_def_sql).scalar() or ""
                    if index_def:
                        # 检查索引定义中是否包含COALESCE或其他表达式
                        is_expression_index_for_query = 'COALESCE' in index_def.upper() or '(' in index_def
                except Exception as e:
                    logger.debug(f"[RawDataImporter] [v4.17.0] 检查索引类型失败（继续）: {e}")
                
                # ⭐ v4.17.0重构：使用原始SQL查询（表是动态的，没有ORM Model）
                where_clause = "data_domain = :data_domain AND granularity = :granularity AND platform_code = :platform_code"
                where_params = {
                    'data_domain': data_domain,
                    'granularity': granularity,
                    'platform_code': platform_code
                }
                
                # ⭐ v4.17.0修复：existing_hashes查询必须与索引表达式一致
                # 如果索引使用COALESCE(shop_id, '')，查询也必须使用COALESCE才能正确匹配
                if is_expression_index_for_query:
                    # 表达式索引：使用COALESCE匹配（与索引定义一致）
                    if shop_id:
                        where_clause += " AND COALESCE(shop_id, '') = COALESCE(:shop_id, '')"
                        where_params['shop_id'] = shop_id
                    else:
                        # shop_id为NULL时，COALESCE(shop_id, '') = ''
                        where_clause += " AND COALESCE(shop_id, '') = ''"
                else:
                    # 普通索引：使用直接匹配
                    if shop_id:
                        where_clause += " AND shop_id = :shop_id"
                        where_params['shop_id'] = shop_id
                    else:
                        where_clause += " AND shop_id IS NULL"
                
                # services域需要sub_domain条件
                if data_domain.lower() == 'services' and sub_domain:
                    where_clause += " AND sub_domain = :sub_domain"
                    where_params['sub_domain'] = sub_domain
                
                # ⭐ v4.17.1优化：使用LIMIT优化查询（如果只需要检查是否存在，不需要全部数据）
                # 但为了准确统计INSERT/UPDATE，我们需要查询所有匹配的data_hash
                query_sql = text(f'SELECT data_hash FROM b_class."{table_name}" WHERE {where_clause}')
                existing_records = self.db.execute(query_sql, where_params).fetchall()
                existing_hashes = {row[0] for row in existing_records}
                logger.info(
                    f"[RawDataImporter] [v4.17.1] UPSERT策略：查询到{len(existing_hashes)}个已存在的data_hash "
                    f"（表={table_name}, platform={platform_code}, shop_id={shop_id or 'NULL'}, "
                    f"表达式索引={is_expression_index_for_query}）"
                )
            
            # ⭐ 修复：插入前查询当前记录数（用于计算实际插入数）
            count_sql = text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
            before_count = self.db.execute(count_sql).scalar() or 0
            
            # ⭐ v4.17.0重构：表名已从table_manager获取，直接使用
            # 检查唯一索引名称（用于ON CONFLICT）
            new_index_name = f"uq_{table_name}_hash"
            
            # 检查新索引是否存在，并判断索引类型（表达式索引 vs 普通索引）
            index_exists = False
            is_expression_index = False
            try:
                check_index_sql = text(
                    f"SELECT COUNT(*) FROM pg_indexes "
                    f"WHERE indexname = '{new_index_name}'"
                )
                index_exists = self.db.execute(check_index_sql).scalar() > 0
                
                # ⭐ v4.14.0修复：如果索引存在，检查是否是表达式索引
                if index_exists:
                    check_index_def_sql = text(
                        f"SELECT indexdef FROM pg_indexes "
                        f"WHERE indexname = '{new_index_name}'"
                    )
                    index_def = self.db.execute(check_index_def_sql).scalar() or ""
                    # 检查索引定义中是否包含COALESCE或其他表达式
                    is_expression_index = 'COALESCE' in index_def.upper() or '(' in index_def
                    
                    if is_expression_index:
                        logger.info(
                            f"[RawDataImporter] [v4.14.0] 检测到表达式索引: {new_index_name}, "
                            f"定义: {index_def[:100]}..."
                        )
                    else:
                        logger.debug(
                            f"[RawDataImporter] [v4.14.0] 检测到普通索引: {new_index_name}"
                        )
            except Exception as e:
                logger.warning(f"[RawDataImporter] 检查索引失败: {e}")
                index_exists = False
                is_expression_index = False
            
            # 分离系统字段和动态列
            system_fields = {
                'platform_code', 'shop_id', 'data_domain', 'granularity',
                'metric_date', 'file_id', 'raw_data', 'header_columns',
                'data_hash', 'ingest_timestamp', 'currency_code',  # ⭐ v4.15.0新增
                'sub_domain', 'template_id',  # ⭐ v4.16.0新增：services域需要；v4.17.0新增：template_id
                'period_start_date', 'period_end_date',  # ⭐ v4.18.0新增：日期范围
                'period_start_time', 'period_end_time'   # ⭐ v4.18.0新增：时间范围（可选）
            }
            
            # ⭐ v4.17.0新增：添加template_id到插入数据
            for record in insert_data:
                if template_id is not None:
                    record['template_id'] = template_id
            
            # 准备插入数据（只包含系统字段）
            insert_data_prepared = []
            for record in insert_data:
                prepared_record = {k: v for k, v in record.items() if k in system_fields}
                insert_data_prepared.append(prepared_record)
            
            if is_upsert:
                logger.info(
                    f"[RawDataImporter] [v4.15.0] 数据域 {data_domain} 使用UPSERT策略（更新而非跳过）"
                )
            
            # ⭐ v4.17.0重构：统一使用原始SQL插入（表是动态的，没有ORM Model）
            # 检查索引类型（表达式索引 vs 普通索引）
            index_exists = False
            is_expression_index = False
            try:
                check_index_sql = text(
                    f"SELECT COUNT(*) FROM pg_indexes "
                    f"WHERE indexname = '{new_index_name}'"
                )
                index_exists = self.db.execute(check_index_sql).scalar() > 0
                
                if index_exists:
                    check_index_def_sql = text(
                        f"SELECT indexdef FROM pg_indexes "
                        f"WHERE indexname = '{new_index_name}'"
                    )
                    index_def = self.db.execute(check_index_def_sql).scalar() or ""
                    is_expression_index = 'COALESCE' in index_def.upper() or '(' in index_def
            except Exception as e:
                logger.warning(f"[RawDataImporter] 检查索引失败: {e}")
                index_exists = False
                is_expression_index = False
            
            # ⭐ v4.17.0重构：统一使用原始SQL插入
            if True:  # 总是使用原始SQL（因为表是动态的）
                # 表达式索引：使用原始SQL的ON CONFLICT，明确指定表达式
                logger.info(
                    f"[RawDataImporter] [v4.14.0] 使用原始SQL插入（表达式索引）: {new_index_name}"
                )
                
                # ⭐ v4.15.0新增：根据策略构建SQL
                # ⭐ v4.17.0重构：统一使用原始SQL，支持动态表名
                
                # 构建INSERT列和值（基础字段）
                # ⭐ v4.18.0增强：添加period_start_date, period_end_date, period_start_time, period_end_time
                base_columns = [
                    "platform_code", "shop_id", "data_domain", "granularity",
                    "metric_date", "period_start_date", "period_end_date",
                    "period_start_time", "period_end_time",
                    "file_id", "raw_data", "header_columns",
                    "data_hash", "ingest_timestamp", "currency_code"
                ]
                base_values = [
                    ":platform_code", ":shop_id", ":data_domain", ":granularity",
                    ":metric_date", ":period_start_date", ":period_end_date",
                    ":period_start_time", ":period_end_time",
                    ":file_id", ":raw_data", ":header_columns",
                    ":data_hash", ":ingest_timestamp", ":currency_code"
                ]
                
                # services域需要sub_domain字段
                if data_domain.lower() == 'services' and sub_domain:
                    base_columns.append("sub_domain")
                    base_values.append(":sub_domain")
                
                # template_id字段（可选）
                if template_id is not None:
                    base_columns.append("template_id")
                    base_values.append(":template_id")
                
                insert_columns = ", ".join(base_columns)
                insert_values = ", ".join(base_values)
                
                # ⭐ v4.17.0修复：构建ON CONFLICT子句
                # PostgreSQL的ON CONFLICT对于表达式索引，必须使用表达式本身，不能使用索引名称
                # ⚠️ 注意：PostgreSQL不支持ON CONFLICT ON INDEX语法，必须使用表达式
                if is_expression_index:
                    # 表达式索引：使用表达式本身（与索引定义一致）
                    if data_domain.lower() == 'services' and sub_domain:
                        conflict_clause = "(data_domain, sub_domain, granularity, data_hash)"
                    else:
                        # ⭐ 关键：表达式索引使用COALESCE表达式，与索引定义完全一致
                        conflict_clause = "(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)"
                else:
                    # 普通索引：使用列名列表
                    if data_domain.lower() == 'services' and sub_domain:
                        conflict_clause = "(data_domain, sub_domain, granularity, data_hash)"
                    else:
                        conflict_clause = "(platform_code, shop_id, data_domain, granularity, data_hash)"
                
                if is_upsert:
                    # UPSERT策略：ON CONFLICT ... DO UPDATE
                    update_fields = get_upsert_update_fields(data_domain)
                    update_clauses = []
                    for field in update_fields:
                        if field == 'raw_data':
                            # ⭐ v4.17.0修复：raw_data已经是JSON字符串，PostgreSQL会自动转换为JSONB
                            update_clauses.append(f'raw_data = EXCLUDED.raw_data')
                        elif field == 'header_columns':
                            # ⭐ v4.17.0修复：header_columns已经是JSON字符串，PostgreSQL会自动转换为JSONB
                            update_clauses.append(f'header_columns = EXCLUDED.header_columns')
                        else:
                            update_clauses.append(f'{field} = EXCLUDED.{field}')
                    update_clause = ', '.join(update_clauses) if update_clauses else 'ingest_timestamp = EXCLUDED.ingest_timestamp'
                    
                    insert_sql_template = text(f"""
                        INSERT INTO b_class."{table_name}" 
                        ({insert_columns})
                        VALUES ({insert_values})
                        ON CONFLICT {conflict_clause}
                        DO UPDATE SET {update_clause}
                    """)
                else:
                    # INSERT策略：ON CONFLICT DO NOTHING
                    insert_sql_template = text(f"""
                        INSERT INTO b_class."{table_name}" 
                        ({insert_columns})
                        VALUES ({insert_values})
                        ON CONFLICT {conflict_clause} DO NOTHING
                    """)
                
                # ⭐ v4.18.1性能优化：真正的批量插入（使用executemany）
                # 将BATCH_SIZE从100增加到500，提升批处理效率
                BATCH_SIZE = 500  # 每批500行（提升性能）
                processed_count = 0
                skipped_count = 0
                error_count = 0
                total_batches = (len(insert_data_prepared) + BATCH_SIZE - 1) // BATCH_SIZE
                
                logger.info(
                    f"[RawDataImporter] [v4.18.1] 开始批量插入（表={table_name}，策略={strategy}）: "
                    f"共{len(insert_data_prepared)}行，分{total_batches}批，每批{BATCH_SIZE}行"
                )
                
                # 预处理所有记录（转换JSON字段）
                prepared_records = []
                for record in insert_data_prepared:
                    record_copy = record.copy()  # 避免修改原始记录
                    
                    # 转换raw_data（dict -> JSON字符串）
                    if 'raw_data' in record_copy and isinstance(record_copy['raw_data'], dict):
                        record_copy['raw_data'] = json.dumps(record_copy['raw_data'], ensure_ascii=False)
                    elif 'raw_data' in record_copy and record_copy['raw_data'] is None:
                        record_copy['raw_data'] = None
                    
                    # 转换header_columns（list -> JSON字符串）
                    if 'header_columns' in record_copy and isinstance(record_copy['header_columns'], list):
                        record_copy['header_columns'] = json.dumps(record_copy['header_columns'], ensure_ascii=False)
                    elif 'header_columns' in record_copy and record_copy['header_columns'] is None:
                        record_copy['header_columns'] = None
                    
                    # ⭐ v4.17.0新增：确保sub_domain字段存在（services域）
                    if data_domain.lower() == 'services' and sub_domain and 'sub_domain' not in record_copy:
                        record_copy['sub_domain'] = sub_domain.lower()
                    
                    # ⭐ v4.17.0新增：确保template_id字段存在
                    if template_id is not None and 'template_id' not in record_copy:
                        record_copy['template_id'] = template_id
                    
                    prepared_records.append(record_copy)
                
                # ⭐ v4.18.1优化：使用executemany进行真正的批量插入
                # PostgreSQL + psycopg2 的 executemany 会自动优化为批量INSERT
                # 性能提升：从每行1次SQL调用改为每批1次SQL调用
                from sqlalchemy import Connection
                
                # 批量插入（每批一次executemany调用）
                for batch_idx in range(0, len(prepared_records), BATCH_SIZE):
                    batch_end = min(batch_idx + BATCH_SIZE, len(prepared_records))
                    batch_records = prepared_records[batch_idx:batch_end]
                    batch_num = (batch_idx // BATCH_SIZE) + 1
                    batch_processed = 0
                    batch_skipped = 0
                    batch_errors = 0
                    
                    try:
                        # ⭐ v4.18.1核心优化：使用原生connection的executemany
                        # 这比循环execute快5-10倍
                        connection = self.db.connection()
                        raw_conn = connection.connection
                        cursor = raw_conn.cursor()
                        
                        # 构建SQL（使用%s作为占位符，psycopg2格式）
                        columns_list = base_columns.copy()
                        if data_domain.lower() == 'services' and sub_domain:
                            if 'sub_domain' not in columns_list:
                                columns_list.append('sub_domain')
                        if template_id is not None:
                            if 'template_id' not in columns_list:
                                columns_list.append('template_id')
                        
                        columns_str = ', '.join(columns_list)
                        placeholders = ', '.join(['%s'] * len(columns_list))
                        
                        if is_upsert:
                            update_fields = get_upsert_update_fields(data_domain)
                            update_clauses = []
                            for field in update_fields:
                                update_clauses.append(f'{field} = EXCLUDED.{field}')
                            update_clause = ', '.join(update_clauses) if update_clauses else 'ingest_timestamp = EXCLUDED.ingest_timestamp'
                            
                            sql = f'''
                                INSERT INTO b_class."{table_name}" ({columns_str})
                                VALUES ({placeholders})
                                ON CONFLICT {conflict_clause}
                                DO UPDATE SET {update_clause}
                            '''
                        else:
                            sql = f'''
                                INSERT INTO b_class."{table_name}" ({columns_str})
                                VALUES ({placeholders})
                                ON CONFLICT {conflict_clause} DO NOTHING
                            '''
                        
                        # 准备数据元组列表（按columns_list顺序）
                        data_tuples = []
                        for record in batch_records:
                            row_tuple = tuple(record.get(col) for col in columns_list)
                            data_tuples.append(row_tuple)
                        
                        # 执行批量插入
                        from psycopg2.extras import execute_batch
                        execute_batch(cursor, sql, data_tuples, page_size=BATCH_SIZE)
                        batch_processed = len(batch_records)
                        
                        # 提交事务
                        raw_conn.commit()
                        processed_count += batch_processed
                        
                        # 记录进度（减少日志频率，每5批输出一次）
                        if batch_num % 5 == 0 or batch_num == total_batches:
                            logger.info(
                                f"[RawDataImporter] [v4.18.1] [进度] 批次 {batch_num}/{total_batches} 完成: "
                                f"已处理 {batch_end}/{len(insert_data_prepared)} 行 "
                                f"（成功={processed_count}, 错误={error_count}）"
                            )
                        
                    except Exception as e:
                        # 批量插入失败，回滚并尝试逐行插入（降级处理）
                        try:
                            raw_conn.rollback()
                        except:
                            pass
                        
                        error_str = str(e).lower()
                        
                        # 如果是唯一约束冲突，逐行处理以找出重复项
                        if 'unique' in error_str or 'duplicate' in error_str or 'violates unique constraint' in error_str:
                            logger.warning(
                                f"[RawDataImporter] [v4.18.1] 批次 {batch_num} 批量插入失败（唯一约束），降级为逐行插入"
                            )
                            # 逐行处理
                            for i, record_copy in enumerate(batch_records):
                                try:
                                    self.db.execute(insert_sql_template, record_copy)
                                    self.db.commit()
                                    batch_processed += 1
                                except Exception as row_error:
                                    self.db.rollback()
                                    row_error_str = str(row_error).lower()
                                    if 'unique' in row_error_str or 'duplicate' in row_error_str:
                                        batch_skipped += 1
                                    else:
                                        batch_errors += 1
                            processed_count += batch_processed
                            skipped_count += batch_skipped
                            error_count += batch_errors
                        else:
                            # 其他错误，记录并跳过整个批次
                            batch_errors = len(batch_records)
                            error_count += batch_errors
                            logger.error(
                                f"[RawDataImporter] [v4.18.1] 批次 {batch_num} 插入失败: {e}",
                                exc_info=True
                            )
                
                # ⭐ v4.18.1优化：批量插入已完成，所有批次都已提交
                # 不需要再次commit（每批都已提交）
                
                logger.info(
                    f"[RawDataImporter] [v4.15.0] 表达式索引插入完成（策略={strategy}）: "
                    f"准备插入={len(insert_data_prepared)}行, "
                    f"已处理={processed_count}行, "
                    f"跳过={skipped_count}行, "
                    f"错误={error_count}行 "
                    f"（实际插入/更新数稍后通过计数计算）"
                )
                
                # ⭐ 注意：表达式索引插入后，实际插入数会在后面通过比较前后记录数计算
                # 这里先跳过，在后面的代码中统一计算
                
                # 验证：确保所有行都被处理
                if processed_count + skipped_count + error_count != len(insert_data_prepared):
                    logger.warning(
                        f"[RawDataImporter] ⚠️ 警告：处理行数不匹配！"
                        f"准备插入={len(insert_data_prepared)}, "
                        f"已处理={processed_count}, "
                        f"跳过={skipped_count}, "
                        f"错误={error_count}, "
                        f"总计={processed_count + skipped_count + error_count}"
                    )
            
            # ⭐ v4.14.0新增：使用原始SQL更新动态列（如果存在）
            # 从原始rows数据中获取动态列的值
            if header_columns and rows:
                try:
                    dynamic_column_manager = get_dynamic_column_manager(self.db)
                    existing_columns = dynamic_column_manager.get_existing_columns(table_name)
                    
                    # 构建列名映射（原始列名 -> 规范化列名），只映射存在的列
                    column_mapping = {}
                    for original_col in header_columns:
                        normalized_col = dynamic_column_manager.normalize_column_name(original_col)
                        # 只映射那些确实存在于表中的列（排除系统字段）
                        if normalized_col in existing_columns and normalized_col not in system_fields:
                            column_mapping[original_col] = normalized_col
                    
                    if column_mapping:
                        # 构建UPDATE语句更新动态列
                        # 注意：需要根据唯一键更新，使用刚插入的数据
                        for i, row in enumerate(rows):
                            prepared_record = insert_data_prepared[i]
                            
                            # 构建WHERE条件（使用唯一键）
                            where_conditions = []
                            where_params = {}
                            
                            if data_domain.lower() == 'services' and sub_domain:
                                # services域：使用sub_domain的唯一约束
                                where_conditions.append('data_domain = :data_domain')
                                where_conditions.append('sub_domain = :sub_domain')
                                where_conditions.append('granularity = :granularity')
                                where_conditions.append('data_hash = :data_hash')
                                where_params['sub_domain'] = sub_domain.lower()
                            elif index_exists and is_expression_index:
                                where_conditions.append('platform_code = :platform_code')
                                where_conditions.append('COALESCE(shop_id, \'\') = COALESCE(:shop_id, \'\')')
                                where_conditions.append('data_domain = :data_domain')
                                where_conditions.append('granularity = :granularity')
                                where_conditions.append('data_hash = :data_hash')
                            else:
                                where_conditions.append('data_domain = :data_domain')
                                where_conditions.append('granularity = :granularity')
                                where_conditions.append('data_hash = :data_hash')
                            
                            where_params.update({
                                'platform_code': prepared_record['platform_code'],
                                'shop_id': prepared_record.get('shop_id'),
                                'data_domain': prepared_record['data_domain'],
                                'granularity': prepared_record['granularity'],
                                'data_hash': prepared_record['data_hash']
                            })
                            
                            # 构建SET子句（从原始row数据获取值）
                            set_clauses = []
                            for original_col, normalized_col in column_mapping.items():
                                if original_col in row:
                                    set_clauses.append(f'"{normalized_col}" = :{normalized_col}')
                                    where_params[normalized_col] = str(row[original_col]) if row[original_col] is not None else None
                            
                            if set_clauses:
                                update_sql = text(f"""
                                    UPDATE "{table_name}"
                                    SET {', '.join(set_clauses)}
                                    WHERE {' AND '.join(where_conditions)}
                                """)
                                self.db.execute(update_sql, where_params)
                        
                        logger.info(
                            f"[RawDataImporter] [v4.14.0] 更新动态列: {len(column_mapping)}个列 "
                            f"（表={table_name}）"
                        )
                except Exception as e:
                    logger.warning(
                        f"[RawDataImporter] [v4.14.0] 更新动态列失败: {e}，"
                        f"数据已通过raw_data JSONB存储",
                        exc_info=True
                    )
                    # 更新失败不影响数据入库（数据已在raw_data JSONB中）
            
            self.db.commit()
            
            # ⭐ 修复：插入后查询实际记录数
            after_count_sql = text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
            after_count = self.db.execute(after_count_sql).scalar() or 0
            
            # ⭐ 修复：计算实际插入数
            actual_inserted = after_count - before_count
            
            # ⭐ 添加行数验证：检测显著数据丢失
            expected_inserted = len(insert_data)
            if expected_inserted > 0:
                loss_rate = (expected_inserted - actual_inserted) / expected_inserted
                if loss_rate > 0.05:  # 超过5%的数据丢失
                    logger.warning(
                        f"[RawDataImporter] ⚠️ 警告：检测到显著数据丢失！"
                        f"准备插入={expected_inserted}行, "
                        f"实际插入={actual_inserted}行, "
                        f"丢失率={loss_rate:.2%} "
                        f"（可能原因：核心字段配置不正确导致所有行产生相同的hash）"
                    )
                elif actual_inserted == 1 and expected_inserted > 1:
                    logger.error(
                        f"[RawDataImporter] ❌ 严重错误：只插入了1行，但准备插入{expected_inserted}行！"
                        f"这可能是因为所有行的data_hash都相同，导致去重失败。"
                        f"请检查核心字段配置是否正确。"
                    )
            
            # ⭐ v4.15.0新增：计算详细统计信息（区分INSERT/UPDATE/SKIP）
            inserted_count = 0
            updated_count = 0
            skipped_count = 0
            
            if is_upsert:
                # ⭐ v4.17.0修复：UPSERT策略下，使用existing_hashes准确区分INSERT和UPDATE
                # existing_hashes在第284行已经查询（仅UPSERT策略）
                if existing_hashes:
                    # 有已存在的数据：区分新插入和更新
                    # 从insert_data_prepared中提取所有data_hash
                    new_hashes = {record['data_hash'] for record in insert_data_prepared}
                    
                    inserted_hashes = new_hashes - existing_hashes  # 新插入的hash
                    updated_hashes = new_hashes & existing_hashes  # 更新的hash
                    
                    # 统计新插入和更新的行数
                    inserted_count = sum(1 for r in insert_data_prepared if r['data_hash'] in inserted_hashes)
                    updated_count = sum(1 for r in insert_data_prepared if r['data_hash'] in updated_hashes)
                else:
                    # 没有已存在的数据：全部是新插入
                    inserted_count = len(insert_data_prepared)
                    updated_count = 0
                
                skipped_count = 0
                
                # ⭐ v4.17.0验证：actual_inserted应该等于inserted_count（允许小误差）
                # actual_inserted = after_count - before_count（实际数据库变化）
                # 由于并发、事务等因素，可能有小误差
                if abs(actual_inserted - inserted_count) > 5:  # 允许5行的误差
                    logger.warning(
                        f"[RawDataImporter] [v4.17.0] ⚠️ 统计不匹配（使用actual_inserted修正）: "
                        f"actual_inserted={actual_inserted}, inserted_count={inserted_count}, "
                        f"updated_count={updated_count}, expected_inserted={expected_inserted}"
                    )
                    # 使用actual_inserted作为最终值（更准确，因为它是实际数据库变化）
                    inserted_count = max(0, actual_inserted)
                    updated_count = max(0, expected_inserted - inserted_count)
                
                # ⭐ v4.17.0验证：确保统计总数正确
                if inserted_count + updated_count != expected_inserted:
                    logger.warning(
                        f"[RawDataImporter] [v4.17.0] ⚠️ 统计总数不匹配: "
                        f"插入={inserted_count}, 更新={updated_count}, 总计={inserted_count + updated_count}, "
                        f"期望={expected_inserted}"
                    )
                
                logger.info(
                    f"[RawDataImporter] [v4.17.0] UPSERT策略完成: "
                    f"表={table_name}, "
                    f"准备处理={expected_inserted}行, "
                    f"新插入={inserted_count}行, "
                    f"更新={updated_count}行, "
                    f"执行前={before_count}行, 执行后={after_count}行"
                )
            else:
                # INSERT策略：区分INSERT和SKIP
                inserted_count = actual_inserted
                updated_count = 0
                skipped_count = expected_inserted - actual_inserted
                
                logger.info(
                    f"[RawDataImporter] 批量插入完成: "
                    f"表={table_name}, "
                    f"准备插入={expected_inserted}行, "
                    f"实际插入={inserted_count}行, "
                    f"跳过={skipped_count}行"
                )
            
            # ⭐ v4.15.0修改：返回详细统计信息
            return {
                'inserted': inserted_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'total': expected_inserted
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[RawDataImporter] 批量插入失败: {e}", exc_info=True)
            raise
    
    async def async_batch_insert_raw_data(
        self,
        rows: List[Dict[str, Any]],
        data_hashes: List[str],
        data_domain: str,
        granularity: str,
        platform_code: str,
        shop_id: Optional[str] = None,
        file_id: Optional[int] = None,
        header_columns: Optional[List[str]] = None,
        currency_codes: Optional[List[Optional[str]]] = None,
        sub_domain: Optional[str] = None,
        original_header_columns: Optional[List[str]] = None,
        template_id: Optional[int] = None
    ) -> Dict[str, int]:
        """
        异步批量插入B类数据（v4.18.2新增）
        
        ⭐ 使用run_in_executor包装同步批量操作，避免阻塞事件循环
        
        注意：由于批量插入使用psycopg2原生连接，目前采用线程池包装方式。
        未来可以迁移到asyncpg原生批量插入以获得更好性能。
        
        Args: 与batch_insert_raw_data相同
        Returns: 与batch_insert_raw_data相同
        """
        if not rows:
            return {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        # ⭐ v4.18.2：对于异步模式，需要使用同步会话执行批量操作
        # 因为psycopg2.extras.execute_batch不支持异步
        from backend.models.database import SessionLocal
        
        def _sync_batch_insert():
            """同步批量插入（在线程池中执行）"""
            sync_db = SessionLocal()
            try:
                # 创建同步版本的importer
                sync_importer = RawDataImporter(sync_db)
                result = sync_importer.batch_insert_raw_data(
                    rows=rows,
                    data_hashes=data_hashes,
                    data_domain=data_domain,
                    granularity=granularity,
                    platform_code=platform_code,
                    shop_id=shop_id,
                    file_id=file_id,
                    header_columns=header_columns,
                    currency_codes=currency_codes,
                    sub_domain=sub_domain,
                    original_header_columns=original_header_columns,
                    template_id=template_id
                )
                sync_db.commit()
                return result
            except Exception as e:
                sync_db.rollback()
                raise
            finally:
                sync_db.close()
        
        # 在线程池中执行同步操作
        loop = asyncio.get_running_loop()
        # v4.19.0更新：使用统一执行器管理器（I/O密集型操作）
        executor_manager = get_executor_manager()
        result = await executor_manager.run_io_intensive(_sync_batch_insert)
        return result


def get_raw_data_importer(db: AsyncSession) -> RawDataImporter:
    """
    获取B类数据入库服务实例
    
    ⭐ v4.18.2：支持异步会话
    ⭐ v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return RawDataImporter(db)

