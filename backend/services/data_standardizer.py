#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据标准化服务

功能：
1. 日期字段标准化：将各种日期格式统一转换为标准格式（YYYY-MM-DD或datetime对象）
2. 数值字段标准化：处理千分位、货币符号等
3. 字符串字段标准化：去除前后空格、统一编码

核心价值：
- 确保不同格式的日期数据在入库后保持一致
- 避免日期格式混乱导致的数据查询和分析错误
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from datetime import date, datetime

from modules.services.smart_date_parser import parse_date, detect_dayfirst
from backend.services.field_mapping.type_detector import detect_date_range_format
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 日期字段列表（根据数据域不同）
# 注意：DateTime字段保留时间部分，Date字段丢弃时间部分
DATE_FIELDS_BY_DOMAIN = {
    "orders": ["order_time_utc", "order_date_local", "metric_date", "payment_time", "ship_time"],
    "products": ["metric_date", "launch_date"],
    "traffic": ["metric_date"],
    "analytics": ["metric_date"],
    "services": ["service_date", "metric_date"],
}

# DateTime字段列表（需要保留时间部分）
DATETIME_FIELDS_BY_DOMAIN = {
    "orders": ["order_time_utc", "payment_time", "ship_time"],  # 这些字段需要保留时间
    "products": [],  # 产品指标通常只需要日期
    "traffic": [],
    "analytics": [],
    "services": [],
}

# 数值字段列表（需要去除千分位等）
NUMERIC_FIELDS_BY_DOMAIN = {
    "orders": ["total_amount", "subtotal", "shipping_fee", "tax_amount", "discount_amount", "refund_amount"],
    "products": ["price", "stock", "sales_amount"],
    "traffic": ["page_views", "unique_visitors"],
    "analytics": ["conversion_rate", "click_rate"],
    "services": ["amount"],
}


def standardize_date_value(value: Any, prefer_dayfirst: Optional[bool] = None, keep_time: bool = False) -> Optional[Any]:
    """
    标准化日期/时间值
    
    支持格式：
    - 字符串格式：25/08/2025, 2025-08-25, 2025\08\25, 2025-08-25-16:30 等
    - Excel序列值：44818
    - datetime对象：根据keep_time决定是否保留时间
    - date对象：直接返回（如果keep_time=True，转换为datetime 00:00:00）
    
    ⭐ v4.7.0企业级ERP空值处理：
    - None、空字符串""、NaN、空列表/字典都视为空值
    - 空值统一返回None（符合数据库NULL语义）
    - 空值不会导致错误，优雅处理
    
    Args:
        value: 原始日期值
        prefer_dayfirst: 日期格式偏好（True=dd/mm/yyyy, False=mm/dd/yyyy）
        keep_time: 是否保留时间部分（True=保留，返回datetime；False=丢弃，返回date）
    
    Returns:
        标准化后的date或datetime对象，如果无法解析或为空值则返回None
    """
    # ⭐ v4.7.0企业级ERP空值处理：统一检测空值
    if value is None:
        return None
    
    # 处理空字符串
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in ('null', 'none', 'n/a', 'na', '-'):
            return None
    
    # 处理NaN（pandas的NaN值）
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return None
    except:
        pass
    
    # 处理pandas的NaT（Not a Time）
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except:
        pass
    
    # 如果已经是date对象
    if isinstance(value, date) and not isinstance(value, datetime):
        if keep_time:
            # 需要时间，转换为datetime（00:00:00）
            return datetime.combine(value, datetime.min.time())
        else:
            # 只需要日期
            return value
    
    # 如果已经是datetime对象
    if isinstance(value, datetime):
        if keep_time:
            # 保留时间部分
            return value
        else:
            # 丢弃时间部分
            return value.date()
    
    # 尝试解析（先尝试解析为datetime，然后根据keep_time决定返回值）
    s = str(value).strip()
    if not s:
        return None
    
    # 先尝试解析为datetime（保留时间信息）
    parsed_datetime = None
    try:
        # 尝试多种datetime格式
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d-%H:%M:%S",
            "%Y-%m-%d-%H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y-%H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ]:
            try:
                parsed_datetime = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
    except Exception:
        pass
    
    # 如果解析出datetime，根据keep_time决定返回值
    if parsed_datetime:
        if keep_time:
            return parsed_datetime
        else:
            return parsed_datetime.date()
    
    # 如果没有时间部分，使用parse_date解析为date
    parsed_date = parse_date(value, prefer_dayfirst=prefer_dayfirst)
    
    if parsed_date is None:
        logger.warning(f"无法解析日期值: {value} (类型: {type(value)})")
        return None
    
    # 如果需要时间，转换为datetime（00:00:00）
    if keep_time:
        return datetime.combine(parsed_date, datetime.min.time())
    
    return parsed_date


def standardize_numeric_value(value: Any) -> Optional[float]:
    """
    标准化数值值
    
    处理：
    - 去除千分位符号（如：1,234.56 -> 1234.56）
    - 去除货币符号（如：$100 -> 100）
    - 处理空值和无效值
    
    ⭐ v4.7.0企业级ERP空值处理：
    - None、空字符串、NaN都视为空值，统一返回None
    - 无法解析的值返回None（调用方应设置为0.0）
    - 支持更多货币符号和格式
    
    Args:
        value: 原始数值
    
    Returns:
        标准化后的float值，如果无法解析或为空值则返回None
    """
    if value is None:
        return None
    
    # 如果已经是数值类型
    if isinstance(value, (int, float)):
        # 检查NaN
        try:
            import math
            if isinstance(value, float) and math.isnan(value):
                return None
        except:
            pass
        return float(value)
    
    # 转换为字符串处理
    s = str(value).strip()
    if not s or s.lower() in ["nan", "none", "null", "n/a", "na", "-", ""]:
        return None
    
    # ⭐ v4.7.0增强：去除常见货币符号和千分位
    # 支持更多货币符号和格式
    s = s.replace(",", "")  # 去除千分位
    s = s.replace("$", "").replace("¥", "").replace("€", "").replace("£", "").replace("RMB", "").replace("CNY", "")
    s = s.replace("USD", "").replace("SGD", "").replace("MYR", "").replace("BRL", "")  # 常见货币代码
    s = s.strip()
    
    # 如果去除符号后为空，返回None
    if not s:
        return None
    
    # ⭐ v4.7.0修复：如果去除符号后不是纯数字，返回None
    # 避免字符串（如"g待发货證."）被转换为数值
    try:
        return float(s)
    except (ValueError, TypeError):
        # ⭐ v4.7.0修复：无法解析的值返回None（而不是抛出异常）
        # 调用方应该将None转换为0.0
        return None


def standardize_row(row: Dict[str, Any], domain: str, date_fields: Optional[List[str]] = None, 
                    prefer_dayfirst: Optional[bool] = None,
                    detected_types: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    标准化单行数据
    
    对指定字段进行标准化处理：
    - 日期字段：统一转换为date对象（丢弃时间）
    - 时间字段：统一转换为datetime对象（保留时间）
    - 数值字段：去除格式符号，转换为float
    - 字符串字段：去除前后空格
    
    Args:
        row: 数据行字典
        domain: 数据域（orders/products/traffic/analytics/services）
        date_fields: 自定义日期字段列表（如果为None，使用默认列表）
        prefer_dayfirst: 日期格式偏好（用于自动检测）
        detected_types: 字段类型检测结果字典 {"标准字段名": "datetime"或"date"}
    
    Returns:
        标准化后的数据行
    """
    standardized = row.copy()
    
    # 获取日期字段列表
    if date_fields is None:
        date_fields = DATE_FIELDS_BY_DOMAIN.get(domain, ["metric_date"])
    
    # 获取DateTime字段列表（需要保留时间）
    datetime_fields = DATETIME_FIELDS_BY_DOMAIN.get(domain, [])
    
    # ⭐ 新增：从detected_types中提取字段类型信息
    if detected_types:
        for standard_field, detected_type in detected_types.items():
            if detected_type == "datetime" and standard_field not in datetime_fields:
                datetime_fields.append(standard_field)
                if standard_field not in date_fields:
                    date_fields.append(standard_field)
    
    # 如果没有指定prefer_dayfirst，尝试从数据中检测
    if prefer_dayfirst is None and date_fields:
        # 抽样检测日期格式偏好
        date_samples = []
        for field in date_fields:
            if field in standardized and standardized[field]:
                date_samples.append(standardized[field])
                if len(date_samples) >= 3:  # 采样3个即可
                    break
        
        if date_samples:
            prefer_dayfirst = detect_dayfirst(date_samples)
            logger.debug(f"检测到日期格式偏好: dayfirst={prefer_dayfirst}")
    
    # 标准化日期/时间字段
    for field in date_fields:
        if field in standardized:
            original_value = standardized[field]
            
            # ⭐ v4.7.0企业级ERP空值处理：统一检测空值
            # None、空字符串、NaN都视为空值，统一返回None
            is_empty = False
            if original_value is None:
                is_empty = True
            elif isinstance(original_value, str) and not original_value.strip():
                is_empty = True
            elif isinstance(original_value, float):
                try:
                    import math
                    if math.isnan(original_value):
                        is_empty = True
                except:
                    pass
            
            if is_empty:
                # 空值统一设置为None（符合数据库NULL语义）
                standardized[field] = None
                logger.debug(f"日期字段 {field} 为空值，设置为None")
            else:
                # 判断是否需要保留时间部分
                keep_time = field in datetime_fields
                standardized_value = standardize_date_value(original_value, prefer_dayfirst=prefer_dayfirst, keep_time=keep_time)
                
                if standardized_value is not None:
                    standardized[field] = standardized_value
                else:
                    # ⭐ v4.7.0修复：无法解析的非空值才记录警告
                    # 如果是空值，已经在上面处理了，这里不需要警告
                    logger.warning(f"日期字段 {field} 无法解析: {original_value}，设置为None")
                    standardized[field] = None  # 无法解析的统一设置为None
    
    # 标准化数值字段
    numeric_fields = NUMERIC_FIELDS_BY_DOMAIN.get(domain, [])
    for field in numeric_fields:
        if field in standardized:
            original_value = standardized[field]
            
            # ⭐ v4.7.0企业级ERP空值处理：统一检测空值
            is_empty = False
            if original_value is None:
                is_empty = True
            elif isinstance(original_value, str) and not original_value.strip():
                is_empty = True
            elif isinstance(original_value, float):
                try:
                    import math
                    if math.isnan(original_value):
                        is_empty = True
                except:
                    pass
            
            if is_empty:
                # 空值统一设置为0.0（数值字段默认值）
                standardized[field] = 0.0
                logger.debug(f"数值字段 {field} 为空值，设置为0.0")
            else:
                standardized_value = standardize_numeric_value(original_value)
                
                if standardized_value is not None:
                    standardized[field] = standardized_value
                else:
                    # ⭐ v4.7.0修复：无法解析的非空值设置为0.0（而不是保留原值）
                    # 保留原值会导致类型错误（字符串被插入float字段）
                    logger.warning(f"数值字段 {field} 无法解析: {original_value}，设置为0.0")
                    standardized[field] = 0.0
    
    # 标准化字符串字段（去除前后空格）
    for key, value in standardized.items():
        if isinstance(value, str):
            standardized[key] = value.strip()
    
    return standardized


def standardize_rows(rows: List[Dict[str, Any]], domain: str, 
                    date_fields: Optional[List[str]] = None,
                    field_mappings: Optional[Dict[str, Dict]] = None) -> List[Dict[str, Any]]:
    """
    批量标准化多行数据
    
    Args:
        rows: 数据行列表
        domain: 数据域
        date_fields: 自定义日期字段列表
        field_mappings: 字段映射建议（可选，包含detected_type信息）
                       格式: {"原始字段": {"standard_field": "标准字段", "detected_type": "datetime"}}
    
    Returns:
        标准化后的数据行列表
    """
    if not rows:
        return rows
    
    # 检测日期格式偏好（从第一行采样）
    prefer_dayfirst = None
    if date_fields is None:
        date_fields = DATE_FIELDS_BY_DOMAIN.get(domain, ["metric_date"])
    
    # 获取DateTime字段列表（需要保留时间）
    datetime_fields = DATETIME_FIELDS_BY_DOMAIN.get(domain, [])
    
    # ⭐ 新增：从映射建议中提取detected_type信息
    # 如果映射建议中包含detected_type，使用它来确定字段类型
    detected_types = {}
    date_range_fields = {}  # 时间范围字段映射：{原始字段: {"start_time": "开始时间字段", "end_time": "结束时间字段"}}
    time_range_fields = []  # ⭐ 新增：time_range字段列表（用户手动选择的时间范围字段）
    
    if field_mappings:
        for orig_col, mapping_info in field_mappings.items():
            if isinstance(mapping_info, dict):
                standard_field = mapping_info.get("standard_field") or mapping_info.get("standard")
                detected_type = mapping_info.get("detected_type")
                is_date_range = mapping_info.get("is_date_range", False)
                
                if standard_field and detected_type:
                    detected_types[standard_field] = detected_type
                
                # ⭐ 新增：检测time_range字段（用户手动选择的时间范围字段）
                if standard_field == "time_range":
                    time_range_fields.append(orig_col)
                    logger.info(f"[Standardizer] 检测到time_range字段: {orig_col}，将在标准化时自动拆分")
                    continue  # 跳过后续的日期时间检测逻辑
                
                # ⭐ 原有的自动检测时间范围字段（保留兼容性）
                if is_date_range:
                    split_fields = mapping_info.get("split_fields", {})
                    date_range_fields[orig_col] = {
                        "start_time": split_fields.get("start_time", "start_time"),
                        "end_time": split_fields.get("end_time", "end_time")
                    }
                    logger.info(f"[Standardizer] 检测到时间范围字段: {orig_col} -> {split_fields}")
    
    # 扩展datetime_fields：包含映射建议中detected_type为"datetime"的字段
    for standard_field, detected_type in detected_types.items():
        if detected_type == "datetime" and standard_field not in datetime_fields:
            datetime_fields.append(standard_field)
            if standard_field not in date_fields:
                date_fields.append(standard_field)
    
    # ⭐ 新增：时间范围字段也需要添加到datetime_fields
    for orig_col, split_info in date_range_fields.items():
        if "start_time" not in datetime_fields:
            datetime_fields.append("start_time")
        if "end_time" not in datetime_fields:
            datetime_fields.append("end_time")
    
    # ⭐ 新增：time_range字段也需要添加到datetime_fields和date_fields
    if time_range_fields:
        if "start_time" not in datetime_fields:
            datetime_fields.append("start_time")
        if "end_time" not in datetime_fields:
            datetime_fields.append("end_time")
        # metric_date用于按日期聚合
        if "metric_date" not in date_fields:
            date_fields.append("metric_date")
    
    # ⭐ 新增：处理时间范围字段的拆分
    # 1. 处理time_range字段（用户手动选择）
    # 2. 处理自动检测的时间范围字段（兼容性）
    processed_rows = []
    for row in rows:
        processed_row = row.copy()
        
        # 处理time_range字段（用户手动选择）
        for orig_col in time_range_fields:
            if orig_col in processed_row:
                range_value = processed_row[orig_col]
                if range_value:
                    # 检测时间范围格式
                    range_result = detect_date_range_format(range_value)
                    if range_result:
                        start_str, end_str = range_result
                        # ⭐ 修复：时间范围解析时优先使用dayfirst=True（因为原始数据可能是dd/mm/yyyy格式）
                        start_time = standardize_date_value(start_str, prefer_dayfirst=True, keep_time=True)
                        end_time = standardize_date_value(end_str, prefer_dayfirst=True, keep_time=True)
                        
                        # 如果解析失败，再尝试使用prefer_dayfirst参数
                        if not start_time or not end_time:
                            start_time = standardize_date_value(start_str, prefer_dayfirst=prefer_dayfirst, keep_time=True)
                            end_time = standardize_date_value(end_str, prefer_dayfirst=prefer_dayfirst, keep_time=True)
                        
                        if start_time and end_time:
                            processed_row["start_time"] = start_time
                            processed_row["end_time"] = end_time
                            
                            # ⭐ 新增：设置metric_date（用于按日期聚合）
                            # 对于周/月数据，metric_date使用开始日期，便于按日期范围查询和聚合
                            if isinstance(start_time, datetime):
                                processed_row["metric_date"] = start_time.date()
                            elif isinstance(start_time, date):
                                processed_row["metric_date"] = start_time
                            else:
                                # 如果start_time是字符串，尝试解析为date
                                try:
                                    parsed_date = standardize_date_value(start_str, prefer_dayfirst, keep_time=False)
                                    if parsed_date:
                                        processed_row["metric_date"] = parsed_date if isinstance(parsed_date, date) else parsed_date.date()
                                except:
                                    pass
                            
                            # ⭐ 新增：自动检测粒度（granularity）
                            # 计算时间范围的天数
                            if isinstance(start_time, datetime):
                                start_date = start_time.date()
                            elif isinstance(start_time, date):
                                start_date = start_time
                            else:
                                start_date = None
                            
                            if isinstance(end_time, datetime):
                                end_date = end_time.date()
                            elif isinstance(end_time, date):
                                end_date = end_time
                            else:
                                end_date = None
                            
                            if start_date and end_date:
                                days_diff = (end_date - start_date).days + 1  # +1包含首尾两天
                                if days_diff == 1:
                                    processed_row["granularity"] = "daily"
                                elif days_diff <= 7:
                                    processed_row["granularity"] = "weekly"
                                elif days_diff <= 31:
                                    processed_row["granularity"] = "monthly"
                                else:
                                    processed_row["granularity"] = "custom"  # 超过1个月的自定义范围
                                
                                # 设置period_start（用于weekly/monthly数据的区间标识）
                                processed_row["period_start"] = start_date
                            
                            logger.debug(f"[Standardizer] time_range字段拆分: {orig_col}={range_value} -> start_time={start_time}, end_time={end_time}, metric_date={processed_row.get('metric_date')}, granularity={processed_row.get('granularity')}")
                        else:
                            logger.warning(f"[Standardizer] time_range字段解析失败: {orig_col}={range_value}")
                    
                    # 删除原始time_range字段（已拆分为start_time和end_time）
                    processed_row.pop(orig_col, None)
        
        # 处理自动检测的时间范围字段（兼容性）
        for orig_col, split_info in date_range_fields.items():
            if orig_col in processed_row:
                range_value = processed_row[orig_col]
                if range_value:
                    # 检测时间范围格式
                    range_result = detect_date_range_format(range_value)
                    if range_result:
                        start_str, end_str = range_result
                        # ⭐ 修复：时间范围解析时优先使用dayfirst=True
                        start_time = standardize_date_value(start_str, prefer_dayfirst=True, keep_time=True)
                        end_time = standardize_date_value(end_str, prefer_dayfirst=True, keep_time=True)
                        
                        # 如果解析失败，再尝试使用prefer_dayfirst参数
                        if not start_time or not end_time:
                            start_time = standardize_date_value(start_str, prefer_dayfirst=prefer_dayfirst, keep_time=True)
                            end_time = standardize_date_value(end_str, prefer_dayfirst=prefer_dayfirst, keep_time=True)
                        
                        if start_time and end_time:
                            processed_row[split_info["start_time"]] = start_time
                            processed_row[split_info["end_time"]] = end_time
                            logger.debug(f"[Standardizer] 时间范围拆分: {orig_col}={range_value} -> start_time={start_time}, end_time={end_time}")
                        else:
                            logger.warning(f"[Standardizer] 时间范围解析失败: {orig_col}={range_value}")
                    
                    # 删除原始时间范围字段（或保留在attributes中）
                    # 根据业务需求决定是否删除
                    # processed_row.pop(orig_col, None)
        
        processed_rows.append(processed_row)
    
    # 使用处理后的行
    rows = processed_rows
    
    # 从前几行采样日期值
    date_samples = []
    for row in rows[:10]:  # 采样前10行
        for field in date_fields:
            if field in row and row[field]:
                date_samples.append(row[field])
                if len(date_samples) >= 10:  # 采样10个即可
                    break
        if len(date_samples) >= 10:
            break
    
    if date_samples:
        prefer_dayfirst = detect_dayfirst(date_samples)
        logger.info(f"批量数据日期格式偏好检测: dayfirst={prefer_dayfirst} (采样{len(date_samples)}个值)")
    
    # 标准化每一行
    standardized_rows = []
    for row in rows:
        standardized_row = standardize_row(row, domain, date_fields, prefer_dayfirst, detected_types)
        standardized_rows.append(standardized_row)
    
    return standardized_rows

