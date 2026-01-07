"""
API数据格式标准化工具函数
提供日期时间、金额、分页等数据格式的统一处理
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional, Dict, List


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    """
    格式化datetime为ISO 8601格式（UTC）
    
    Args:
        value: datetime对象或None
    
    Returns:
        ISO 8601格式字符串（如"2025-01-16T10:30:00Z"）或None
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # 确保使用UTC时区
        if value.tzinfo is None:
            # 如果没有时区信息，假设是UTC
            return value.isoformat() + "Z"
        else:
            # 转换为UTC（使用timezone.utc）
            from datetime import timezone
            utc_value = value.astimezone(timezone.utc)
            return utc_value.isoformat().replace('+00:00', 'Z')
    return str(value)


def format_date(value: Optional[date]) -> Optional[str]:
    """
    格式化date为ISO 8601格式（YYYY-MM-DD）
    
    Args:
        value: date对象或None
    
    Returns:
        ISO 8601日期格式字符串（如"2025-01-16"）或None
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def format_decimal(value: Optional[Decimal], decimals: int = 2) -> Optional[float]:
    """
    格式化Decimal为float（保留指定小数位）
    
    Args:
        value: Decimal对象或None
        decimals: 保留小数位数（默认2）
    
    Returns:
        float值或None
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value.quantize(Decimal(10) ** -decimals))
    if isinstance(value, (int, float)):
        return round(float(value), decimals)
    return None


def format_response_data(data: Any) -> Any:
    """
    递归格式化响应数据中的日期时间和金额字段
    
    自动处理：
    - datetime对象 → ISO 8601格式字符串
    - date对象 → ISO 8601日期格式字符串
    - Decimal对象 → float（保留2位小数）
    
    Args:
        data: 要格式化的数据（可以是字典、列表、对象等）
    
    Returns:
        格式化后的数据
    """
    if data is None:
        return None
    
    # 处理datetime
    if isinstance(data, datetime):
        return format_datetime(data)
    
    # 处理date
    if isinstance(data, date):
        return format_date(data)
    
    # 处理Decimal
    if isinstance(data, Decimal):
        return format_decimal(data)
    
    # 处理字典
    if isinstance(data, dict):
        return {key: format_response_data(value) for key, value in data.items()}
    
    # 处理列表
    if isinstance(data, list):
        return [format_response_data(item) for item in data]
    
    # 处理其他类型（直接返回）
    return data

