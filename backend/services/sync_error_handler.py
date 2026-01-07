#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步错误处理服务（Sync Error Handler）

v4.12.0新增：
- 统一的错误处理机制
- 定义错误类型枚举
- 统一错误格式（错误码、错误信息、恢复建议）

职责：
- 统一错误格式和处理机制
- 提供错误恢复建议
- 记录错误日志
"""

from enum import Enum
from typing import Optional, Dict, Any
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SyncErrorType(Enum):
    """数据同步错误类型枚举"""
    FILE_ERROR = "file_error"  # 文件相关错误（文件不存在、读取失败等）
    VALIDATION_ERROR = "validation_error"  # 数据验证错误（字段缺失、格式错误等）
    INGESTION_ERROR = "ingestion_error"  # 数据入库错误（数据库错误、约束冲突等）
    TEMPLATE_ERROR = "template_error"  # 模板相关错误（模板不存在、映射失败等）
    NETWORK_ERROR = "network_error"  # 网络错误（HTTP请求失败等）
    SYSTEM_ERROR = "system_error"  # 系统错误（内存不足、超时等）


class SyncErrorHandler:
    """
    数据同步错误处理类
    
    职责：
    - 统一错误格式和处理机制
    - 提供错误恢复建议
    - 记录错误日志
    """
    
    # 错误码定义（2xxx系列：业务错误）
    ERROR_CODES = {
        SyncErrorType.FILE_ERROR: {
            "FILE_NOT_FOUND": 2001,
            "FILE_READ_FAILED": 2002,
            "FILE_FORMAT_INVALID": 2003,
            "FILE_PATH_INVALID": 2004,
        },
        SyncErrorType.VALIDATION_ERROR: {
            "MISSING_REQUIRED_FIELD": 2101,
            "INVALID_DATA_FORMAT": 2102,
            "DATA_TYPE_MISMATCH": 2103,
            "DATA_RANGE_INVALID": 2104,
        },
        SyncErrorType.INGESTION_ERROR: {
            "DATABASE_ERROR": 2201,
            "CONSTRAINT_VIOLATION": 2202,
            "DUPLICATE_KEY": 2203,
            "TRANSACTION_FAILED": 2204,
        },
        SyncErrorType.TEMPLATE_ERROR: {
            "TEMPLATE_NOT_FOUND": 2301,
            "MAPPING_FAILED": 2302,
            "HEADER_ROW_INVALID": 2303,
        },
        SyncErrorType.NETWORK_ERROR: {
            "HTTP_REQUEST_FAILED": 2401,
            "CONNECTION_TIMEOUT": 2402,
            "SERVICE_UNAVAILABLE": 2403,
        },
        SyncErrorType.SYSTEM_ERROR: {
            "MEMORY_ERROR": 2501,
            "TIMEOUT_ERROR": 2502,
            "UNKNOWN_ERROR": 2599,
        },
    }
    
    # 错误恢复建议
    RECOVERY_SUGGESTIONS = {
        2001: "请检查文件是否存在，确认文件路径正确",
        2002: "请检查文件权限，确认文件未被其他程序占用",
        2003: "请检查文件格式，确认文件为有效的Excel文件",
        2004: "请检查文件路径，确认路径在允许的目录中",
        2101: "请检查数据文件，补充缺失的必填字段",
        2102: "请检查数据格式，确保数据符合字段要求",
        2103: "请检查数据类型，确保数据与字段类型匹配",
        2104: "请检查数据范围，确保数据在有效范围内",
        2201: "请检查数据库连接，确认数据库服务正常",
        2202: "请检查数据约束，确保数据符合数据库约束",
        2203: "请检查数据唯一性，避免重复数据",
        2204: "请检查事务状态，确认事务未超时",
        2301: "请创建或选择正确的字段映射模板",
        2302: "请检查字段映射配置，确认映射规则正确",
        2303: "请检查表头行设置，确认表头行位置正确",
        2401: "请检查网络连接，确认服务可用",
        2402: "请增加超时时间，或检查服务响应速度",
        2403: "请稍后重试，或联系系统管理员",
        2501: "请减少批量处理数量，或增加系统内存",
        2502: "请增加超时时间，或优化数据处理逻辑",
        2599: "请联系系统管理员，查看详细错误日志",
    }
    
    @classmethod
    def create_error(
        cls,
        error_type: SyncErrorType,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ) -> Dict[str, Any]:
        """
        创建统一格式的错误响应
        
        Args:
            error_type: 错误类型
            error_code: 错误码（如FILE_NOT_FOUND）
            message: 错误信息
            details: 错误详情（可选）
            original_error: 原始异常（可选）
            
        Returns:
            统一格式的错误字典
        """
        # 获取错误码数值
        error_code_map = cls.ERROR_CODES.get(error_type, {})
        error_code_value = error_code_map.get(error_code, 2599)
        
        # 获取恢复建议
        recovery_suggestion = cls.RECOVERY_SUGGESTIONS.get(error_code_value, "请联系系统管理员")
        
        # 构建错误响应
        error_response = {
            "success": False,
            "error_type": error_type.value,
            "error_code": error_code_value,
            "error_code_name": error_code,
            "message": message,
            "recovery_suggestion": recovery_suggestion,
            "details": details or {},
        }
        
        # 如果有原始异常，记录详细信息
        if original_error:
            error_response["details"]["original_error"] = str(original_error)
            error_response["details"]["error_type"] = type(original_error).__name__
        
        # 记录错误日志
        logger.error(
            f"[SyncError] {error_type.value}: {error_code} ({error_code_value}) - {message}",
            extra={
                "error_type": error_type.value,
                "error_code": error_code_value,
                "error_code_name": error_code,
                "details": details,
                "original_error": str(original_error) if original_error else None,
            }
        )
        
        return error_response
    
    @classmethod
    def handle_exception(
        cls,
        exception: Exception,
        error_type: Optional[SyncErrorType] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        处理异常，转换为统一格式的错误响应
        
        Args:
            exception: 异常对象
            error_type: 错误类型（如果为None，则自动推断）
            context: 上下文信息（可选）
            
        Returns:
            统一格式的错误字典
        """
        # 自动推断错误类型
        if error_type is None:
            error_type = cls._infer_error_type(exception)
        
        # 根据异常类型确定错误码
        error_code = cls._get_error_code(exception, error_type)
        
        # 构建错误信息
        message = str(exception) or "未知错误"
        
        # 构建错误详情
        details = context or {}
        details["exception_type"] = type(exception).__name__
        
        return cls.create_error(
            error_type=error_type,
            error_code=error_code,
            message=message,
            details=details,
            original_error=exception
        )
    
    @classmethod
    def _infer_error_type(cls, exception: Exception) -> SyncErrorType:
        """根据异常类型推断错误类型"""
        exception_type = type(exception).__name__
        exception_str = str(exception).lower()
        
        # 文件相关错误
        if "file" in exception_str or "path" in exception_str or "not found" in exception_str:
            return SyncErrorType.FILE_ERROR
        
        # 验证相关错误
        if "validation" in exception_str or "invalid" in exception_str or "missing" in exception_str:
            return SyncErrorType.VALIDATION_ERROR
        
        # 数据库相关错误
        if "database" in exception_str or "sql" in exception_str or "constraint" in exception_str:
            return SyncErrorType.INGESTION_ERROR
        
        # 模板相关错误
        if "template" in exception_str or "mapping" in exception_str:
            return SyncErrorType.TEMPLATE_ERROR
        
        # 网络相关错误
        if "http" in exception_str or "network" in exception_str or "connection" in exception_str:
            return SyncErrorType.NETWORK_ERROR
        
        # 默认系统错误
        return SyncErrorType.SYSTEM_ERROR
    
    @classmethod
    def _get_error_code(cls, exception: Exception, error_type: SyncErrorType) -> str:
        """根据异常类型和错误类型获取错误码"""
        exception_type = type(exception).__name__
        exception_str = str(exception).lower()
        
        # 文件错误
        if error_type == SyncErrorType.FILE_ERROR:
            if "not found" in exception_str:
                return "FILE_NOT_FOUND"
            elif "read" in exception_str or "open" in exception_str:
                return "FILE_READ_FAILED"
            elif "format" in exception_str or "invalid" in exception_str:
                return "FILE_FORMAT_INVALID"
            elif "path" in exception_str:
                return "FILE_PATH_INVALID"
        
        # 验证错误
        elif error_type == SyncErrorType.VALIDATION_ERROR:
            if "missing" in exception_str or "required" in exception_str:
                return "MISSING_REQUIRED_FIELD"
            elif "format" in exception_str:
                return "INVALID_DATA_FORMAT"
            elif "type" in exception_str:
                return "DATA_TYPE_MISMATCH"
            elif "range" in exception_str:
                return "DATA_RANGE_INVALID"
        
        # 入库错误
        elif error_type == SyncErrorType.INGESTION_ERROR:
            if "constraint" in exception_str or "violation" in exception_str:
                return "CONSTRAINT_VIOLATION"
            elif "duplicate" in exception_str or "unique" in exception_str:
                return "DUPLICATE_KEY"
            elif "transaction" in exception_str:
                return "TRANSACTION_FAILED"
            else:
                return "DATABASE_ERROR"
        
        # 模板错误
        elif error_type == SyncErrorType.TEMPLATE_ERROR:
            if "not found" in exception_str:
                return "TEMPLATE_NOT_FOUND"
            elif "mapping" in exception_str:
                return "MAPPING_FAILED"
            elif "header" in exception_str:
                return "HEADER_ROW_INVALID"
        
        # 网络错误
        elif error_type == SyncErrorType.NETWORK_ERROR:
            if "timeout" in exception_str:
                return "CONNECTION_TIMEOUT"
            elif "unavailable" in exception_str:
                return "SERVICE_UNAVAILABLE"
            else:
                return "HTTP_REQUEST_FAILED"
        
        # 系统错误
        elif error_type == SyncErrorType.SYSTEM_ERROR:
            if "memory" in exception_str:
                return "MEMORY_ERROR"
            elif "timeout" in exception_str:
                return "TIMEOUT_ERROR"
        
        # 默认错误码
        return "UNKNOWN_ERROR"

