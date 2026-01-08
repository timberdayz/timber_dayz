"""
数据库设计规范验证API路由

[*] v4.12.0新增：提供数据库设计规范验证API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db, get_async_db
from backend.services.database_design_validator import validate_database_design
from backend.services.data_ingestion_validator import validate_data_ingestion_process
from backend.services.field_mapping_validator import validate_field_mapping
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/database-design", tags=["数据库设计规范验证"])


@router.get("/validate")
async def validate_design(db: AsyncSession = Depends(get_async_db)):
    """
    验证数据库设计是否符合规范
    
    [*] v4.12.0新增：验证数据库模型、索引、外键、物化视图是否符合设计规范
    
    返回：
    {
        "success": True,
        "is_valid": bool,
        "summary": {
            "total_issues": int,
            "error_count": int,
            "warning_count": int,
            "info_count": int,
            "category_counts": {...}
        },
        "issues": [
            {
                "severity": "error" | "warning" | "info",
                "category": "primary_key" | "nullable" | "index" | "foreign_key" | "materialized_view",
                "table_name": str,
                "field_name": str | null,
                "issue": str,
                "suggestion": str | null
            }
        ]
    }
    """
    try:
        result = validate_database_design(db)
        
        # 转换为字典格式
        issues_dict = []
        for issue in result.issues:
            issues_dict.append({
                "severity": issue.severity,
                "category": issue.category,
                "table_name": issue.table_name,
                "field_name": issue.field_name,
                "issue": issue.issue,
                "suggestion": issue.suggestion
            })
        
        data = {
            "is_valid": result.is_valid,
            "summary": result.summary,
            "issues": issues_dict
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"验证数据库设计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/validate/tables")
async def validate_tables(db: AsyncSession = Depends(get_async_db)):
    """验证表结构"""
    try:
        validator = validate_database_design(db)
        table_issues = [i for i in validator.issues if i.category in ['primary_key', 'nullable', 'index', 'foreign_key']]
        
        data = {
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "table_name": issue.table_name,
                    "field_name": issue.field_name,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion
                }
                for issue in table_issues
            ]
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"验证表结构失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/validate/materialized-views")
async def validate_materialized_views(db: AsyncSession = Depends(get_async_db)):
    """验证物化视图"""
    try:
        validator = validate_database_design(db)
        mv_issues = [i for i in validator.issues if i.category == 'materialized_view']
        
        return {
            "success": True,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "table_name": issue.table_name,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion
                }
                for issue in mv_issues
            ]
        }
    except Exception as e:
        logger.error(f"验证物化视图失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证物化视图失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/validate/field-mapping")
async def validate_field_mapping_endpoint(db: AsyncSession = Depends(get_async_db)):
    """
    验证字段映射
    
    [*] v4.12.0新增：验证字段映射是否符合设计规范
    
    返回：
    {
        "success": True,
        "is_valid": bool,
        "summary": {
            "total_issues": int,
            "error_count": int,
            "warning_count": int,
            "info_count": int,
            "category_counts": {...}
        },
        "issues": [
            {
                "severity": "error" | "warning" | "info",
                "category": "dictionary" | "mapping" | "pattern" | "template" | "fact_table",
                "issue": str,
                "suggestion": str | null,
                "field_name": str | null,
                "code_location": str | null
            }
        ]
    }
    """
    try:
        result = validate_field_mapping(db)
        
        # 转换为字典格式
        issues_dict = []
        for issue in result.issues:
            issues_dict.append({
                "severity": issue.severity,
                "category": issue.category,
                "issue": issue.issue,
                "suggestion": issue.suggestion,
                "field_name": issue.field_name,
                "code_location": issue.code_location
            })
        
        data = {
            "is_valid": result.is_valid,
            "summary": result.summary,
            "issues": issues_dict
        }
        
        return success_response(data=data)
    except Exception as e:
        logger.error(f"验证字段映射失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/validate/data-ingestion")
async def validate_data_ingestion(db: AsyncSession = Depends(get_async_db)):
    """
    验证数据入库流程
    
    [*] v4.12.0新增：验证数据入库流程是否符合设计规范
    
    返回：
    {
        "success": True,
        "is_valid": bool,
        "summary": {
            "total_issues": int,
            "error_count": int,
            "warning_count": int,
            "info_count": int,
            "category_counts": {...}
        },
        "issues": [
            {
                "severity": "error" | "warning" | "info",
                "category": "shop_id" | "platform_code" | "field_mapping" | "validation" | "account_alias",
                "issue": str,
                "suggestion": str | null,
                "code_location": str | null
            }
        ]
    }
    """
    try:
        result = validate_data_ingestion_process(db)
        
        # 转换为字典格式
        issues_dict = []
        for issue in result.issues:
            issues_dict.append({
                "severity": issue.severity,
                "category": issue.category,
                "issue": issue.issue,
                "suggestion": issue.suggestion,
                "code_location": issue.code_location
            })
        
        return {
            "success": True,
            "is_valid": result.is_valid,
            "summary": result.summary,
            "issues": issues_dict
        }
    except Exception as e:
        logger.error(f"验证数据入库流程失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证数据入库流程失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

