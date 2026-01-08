"""
统一API响应格式工具函数
提供统一的成功响应、错误响应、分页响应和列表响应格式
"""

from datetime import datetime
from typing import Any, Optional, Dict, List
from fastapi import Request
from fastapi.responses import JSONResponse
from backend.utils.data_formatter import format_response_data


def get_timestamp() -> str:
    """获取ISO 8601格式的时间戳（UTC）"""
    return datetime.utcnow().isoformat() + "Z"


def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200,
    request_id: Optional[str] = None
) -> JSONResponse:
    """
    统一成功响应格式
    
    Args:
        data: 响应数据（可以是字典、列表等）
        message: 可选的成功消息
        status_code: HTTP状态码（默认200）
    
    Returns:
        JSONResponse: 统一格式的成功响应
    
    Note:
        - 自动格式化data中的日期时间字段为ISO 8601格式
        - 自动格式化data中的Decimal字段为float（保留2位小数）
    """
    # 格式化响应数据（日期时间、金额等）
    formatted_data = format_response_data(data) if data is not None else None
    
    response_data = {
        "success": True,
        "data": formatted_data,
        "timestamp": get_timestamp()
    }
    
    if message:
        response_data["message"] = message
    
    if request_id:
        response_data["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


def error_response(
    code: int,
    message: str,
    error_type: str = "BusinessError",
    detail: Optional[Any] = None,
    recovery_suggestion: Optional[str] = None,
    status_code: int = 200,
    request_id: Optional[str] = None,
    data: Optional[Any] = None
) -> JSONResponse:
    """
    统一错误响应格式
    
    Args:
        code: 4位数字错误码
        message: 用户友好的错误消息
        error_type: 错误类型（SystemError、BusinessError、DataError、UserError）
        detail: 详细错误信息（可选，可以是字符串或字典）
        recovery_suggestion: 错误恢复建议（可选）
        status_code: HTTP状态码（默认200，业务错误也返回200）
        request_id: 请求ID（可选）
        data: 额外的错误数据（可选，用于传递结构化数据如表头变化详情）
    
    Returns:
        JSONResponse: 统一格式的错误响应
    """
    error_data = {
        "code": code,
        "type": error_type
    }
    
    if detail:
        # [*] v4.14.0修复：支持detail为字符串或字典
        if isinstance(detail, dict):
            error_data["detail"] = detail
        else:
            error_data["detail"] = str(detail)
    
    if recovery_suggestion:
        error_data["recovery_suggestion"] = recovery_suggestion
    
    response_data = {
        "success": False,
        "error": error_data,
        "message": message,
        "timestamp": get_timestamp()
    }
    
    # [*] v4.14.0新增：支持在错误响应中包含额外的结构化数据
    if data is not None:
        formatted_data = format_response_data(data)
        response_data["data"] = formatted_data
    
    if request_id:
        response_data["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=response_data
    )


def pagination_response(
    data: List[Any],
    page: int,
    page_size: int,
    total: int,
    message: Optional[str] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """
    统一分页响应格式
    
    Args:
        data: 数据数组
        page: 当前页码（从1开始）
        page_size: 每页数量
        total: 总记录数
        message: 可选的成功消息
    
    Returns:
        JSONResponse: 统一格式的分页响应
    
    Note:
        - 自动格式化data中的日期时间字段为ISO 8601格式
        - 自动格式化data中的Decimal字段为float（保留2位小数）
    """
    # 格式化响应数据（日期时间、金额等）
    formatted_data = format_response_data(data) if data else []
    
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    pagination_data = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages
    }
    
    response_data = {
        "success": True,
        "data": formatted_data,
        "pagination": pagination_data,
        "timestamp": get_timestamp()
    }
    
    if message:
        response_data["message"] = message
    
    if request_id:
        response_data["request_id"] = request_id
    
    return JSONResponse(
        status_code=200,
        content=response_data
    )


def list_response(
    data: List[Any],
    total: Optional[int] = None,
    message: Optional[str] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """
    统一列表响应格式（无分页）
    
    Args:
        data: 数据数组
        total: 总记录数（可选）
        message: 可选的成功消息
    
    Returns:
        JSONResponse: 统一格式的列表响应
    
    Note:
        - 自动格式化data中的日期时间字段为ISO 8601格式
        - 自动格式化data中的Decimal字段为float（保留2位小数）
    """
    # 格式化响应数据（日期时间、金额等）
    formatted_data = format_response_data(data) if data else []
    
    response_data = {
        "success": True,
        "data": formatted_data,
        "timestamp": get_timestamp()
    }
    
    if total is not None:
        response_data["total"] = total
    
    if message:
        response_data["message"] = message
    
    if request_id:
        response_data["request_id"] = request_id
    
    return JSONResponse(
        status_code=200,
        content=response_data
    )


