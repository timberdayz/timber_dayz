#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段类型自动检测器

功能：
- 自动检测原始数据值是否包含时间信息
- 根据检测结果智能建议字段类型（date或datetime）
- 无需用户手动选择，系统自动识别
"""

import re
from typing import Any, List, Optional, Dict
from datetime import datetime, date

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 时间格式模式
TIME_PATTERNS = [
    r'\d{1,2}:\d{2}(:\d{2})?',  # HH:MM 或 HH:MM:SS
    r'\d{1,2}[时点]\d{1,2}分',  # 中文时间格式
    r'\d{1,2}[:\s]\d{2}[:\s]\d{2}',  # 各种分隔符
]

# 日期时间组合格式
DATETIME_PATTERNS = [
    r'\d{4}[-/]\d{1,2}[-/]\d{1,2}[-_\s]\d{1,2}:\d{2}',  # 2025-08-25-16:30
    r'\d{1,2}[-/]\d{1,2}[-/]\d{4}[-_\s]\d{1,2}:\d{2}',  # 25/08/2025-16:30
    r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}',  # 2025-08-25 16:30
]


def detect_datetime_in_value(value: Any) -> bool:
    """
    检测单个值是否包含时间信息
    
    Args:
        value: 原始数据值
    
    Returns:
        True表示包含时间信息，False表示只有日期
    """
    if value is None:
        return False
    
    s = str(value).strip()
    if not s:
        return False
    
    # 如果已经是datetime对象，肯定包含时间
    if isinstance(value, datetime):
        return True
    
    # 如果已经是date对象，肯定不包含时间（除非是datetime.date()）
    if isinstance(value, date) and not isinstance(value, datetime):
        return False
    
    # 检测是否包含时间模式
    for pattern in TIME_PATTERNS:
        if re.search(pattern, s):
            return True
    
    # 检测是否包含日期时间组合格式
    for pattern in DATETIME_PATTERNS:
        if re.search(pattern, s):
            return True
    
    return False


def detect_date_range_format(value: Any) -> Optional[tuple]:
    """
    检测是否为时间范围格式，返回(start_time_str, end_time_str)
    
    支持的格式：
    - 2025-08-25 17:01~2025-08-26 11:02
    - 2025-08-25~2025-08-26
    - 25/08/2025 - 26/08/2025
    - 2025-08-25 17:01 至 2025-08-26 11:02
    - 2025-08-18-15:01~2025-08-25-15:01 (Shopee服务数据域周数据格式)
    
    Args:
        value: 原始数据值
    
    Returns:
        (start_time_str, end_time_str) 如果检测到时间范围，否则返回None
    """
    if value is None:
        return None
    
    s = str(value).strip()
    if not s:
        return None
    
    # 时间范围分隔符：~、-、至、to、～
    separators = [r'~', r'—', r'—', r'至', r'to', r'To', r'TO', r'-', r'到']
    
    # [*] 修复：支持日期时间格式（包含时间）
    # 格式1：2025-08-18-15:01~2025-08-25-15:01 (日期和时间用-分隔)
    datetime_pattern_with_dash = r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}[-]\d{1,2}:\d{2}(?::\d{2})?)'
    # 格式2：2025-08-25 17:01 (日期和时间用空格分隔)
    datetime_pattern_with_space = r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)'
    # 格式3：2025-08-25-16:30 (日期和时间用-分隔，但日期部分也可能用-分隔)
    datetime_pattern_combined = r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[-]\d{1,2}:\d{2}(?::\d{2})?|\s+\d{1,2}:\d{2}(?::\d{2})?)?)'
    
    # 日期格式（不包含时间）
    date_pattern = r'(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})'
    
    # 尝试匹配日期时间范围格式（优先匹配带时间的格式）
    for sep in separators:
        # 匹配格式：2025-08-18-15:01~2025-08-25-15:01
        # 使用更灵活的匹配：允许日期和时间之间用-或空格分隔
        pattern = rf'(\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}(?:[-]\d{{1,2}}:\d{{2}}(?::\d{{2}})?|\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?)\s*{sep}\s*(\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}(?:[-]\d{{1,2}}:\d{{2}}(?::\d{{2}})?|\s+\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?)'
        match = re.search(pattern, s)
        if match:
            start_str = match.group(1).strip()
            end_str = match.group(2).strip()
            # 清理开始时间：将日期和时间之间的-替换为空格
            start_str = re.sub(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})-(\d{1,2}:\d{2})', r'\1 \2', start_str)
            end_str = re.sub(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})-(\d{1,2}:\d{2})', r'\1 \2', end_str)
            return (start_str, end_str)
        
        # 匹配日期格式：2025-08-25~2025-08-26
        pattern = f'{date_pattern}\\s*{sep}\\s*{date_pattern}'
        match = re.search(pattern, s)
        if match:
            return (match.group(1).strip(), match.group(2).strip())
    
    return None


def detect_field_type_from_samples(samples: List[Any], field_name: str = "") -> str:
    """
    从样本数据中检测字段类型
    
    策略：
    1. 分析多个样本值，统计包含时间的比例
    2. 如果>=50%的样本包含时间，建议使用datetime
    3. 如果<50%的样本包含时间，建议使用date
    4. 如果字段名包含"time"关键词，优先使用datetime
    
    Args:
        samples: 样本数据列表（至少1个样本）
        field_name: 字段名称（用于关键词检测）
    
    Returns:
        "datetime" 或 "date"
    """
    if not samples:
        # 默认根据字段名判断
        if field_name and 'time' in field_name.lower():
            return "datetime"
        return "date"
    
    # 统计包含时间的样本数
    datetime_count = 0
    valid_samples = 0
    
    for sample in samples:
        if sample is None or str(sample).strip() == "":
            continue
        
        valid_samples += 1
        if detect_datetime_in_value(sample):
            datetime_count += 1
    
    if valid_samples == 0:
        # 如果没有有效样本，根据字段名判断
        if field_name and 'time' in field_name.lower():
            return "datetime"
        return "date"
    
    # 如果>=50%的样本包含时间，建议datetime
    datetime_ratio = datetime_count / valid_samples if valid_samples > 0 else 0
    
    # 如果字段名包含"time"，提高权重
    if field_name and 'time' in field_name.lower():
        if datetime_ratio >= 0.3:  # 降低阈值到30%
            return "datetime"
        return "datetime"  # 字段名包含time，即使样本没有时间也建议datetime
    
    # 如果字段名包含"date"且样本不包含时间，使用date
    if field_name and 'date' in field_name.lower() and datetime_ratio < 0.5:
        return "date"
    
    # 根据样本比例决定
    if datetime_ratio >= 0.5:
        return "datetime"
    else:
        return "date"


def enhance_mapping_with_type_detection(
    mapping: Dict[str, Any],
    original_column: str,
    sample_values: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    增强映射建议，添加自动检测的字段类型
    
    [*] 新增：支持时间范围字段的自动识别和拆分
    
    Args:
        mapping: 原始映射建议
        original_column: 原始列名
        sample_values: 样本数据值列表（可选）
    
    Returns:
        增强后的映射建议（包含detected_type字段）
        如果是时间范围字段，会添加is_date_range=True和split_fields信息
    """
    enhanced = mapping.copy()
    
    # [*] 新增：检测是否为时间范围字段（优先检测，即使standard_field为"未映射"也要检测）
    if sample_values:
        # 检查样本中是否包含时间范围格式
        range_count = 0
        valid_samples = [s for s in sample_values[:5] if s and str(s).strip()]
        for sample in valid_samples:
            if detect_date_range_format(sample):
                range_count += 1
        
        # 如果>=50%的样本是时间范围格式，标记为时间范围字段
        if range_count >= len(valid_samples) * 0.5 and len(valid_samples) > 0:
            enhanced["is_date_range"] = True
            enhanced["detected_type"] = "date_range"
            enhanced["split_fields"] = {
                "start_time": "开始时间",
                "end_time": "结束时间"
            }
            enhanced["detection_reason"] = f"检测到时间范围格式（{range_count}/{len(valid_samples)}个样本），将自动拆分为开始时间和结束时间"
            # [*] 重要：即使standard_field已有值（如"datetime"），时间范围字段也应该优先拆分
            # 清空standard_field，让前端根据is_date_range自动拆分，而不是映射到单个datetime字段
            enhanced["standard_field"] = None  # 或保留原值，但前端会优先检查is_date_range
            enhanced["standard"] = None  # 兼容字段
            return enhanced
    
    # 原有的日期时间检测逻辑
    # 获取标准字段名
    standard_field = mapping.get("standard") or mapping.get("standard_field")
    
    if not standard_field or standard_field == "未映射":
        # 如果没有标准字段，仍然尝试检测日期时间类型
        if sample_values:
            detected_type = detect_field_type_from_samples(sample_values, original_column)
            enhanced["detected_type"] = detected_type
            enhanced["detection_confidence"] = 0.7
        return enhanced
    
    # 检测字段类型
    if sample_values:
        detected_type = detect_field_type_from_samples(sample_values, original_column)
    else:
        # 没有样本数据，根据字段名和标准字段名判断
        if 'time' in original_column.lower() or 'time' in standard_field.lower():
            detected_type = "datetime"
        else:
            detected_type = "date"
    
    # 添加到映射建议中
    enhanced["detected_type"] = detected_type
    enhanced["detection_confidence"] = 0.95 if sample_values else 0.7
    
    # 如果标准字段是字典中的字段，检查字典中的data_type
    # 如果字典中有定义，优先使用字典中的类型
    # 但可以根据检测结果给出建议
    if "data_type" not in enhanced:
        enhanced["data_type"] = detected_type
    elif enhanced.get("data_type") == "date" and detected_type == "datetime":
        # 如果字典定义为date，但检测出datetime，给出建议
        enhanced["suggested_type"] = "datetime"
        enhanced["detection_reason"] = "数据样本包含时间信息，建议使用datetime类型"
    
    return enhanced

