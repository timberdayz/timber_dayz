"""
数据库设计规范验证API路由

[*] v4.12.0新增:提供数据库设计规范验证API

[*] 2026-10-31 修复:这组端点从第一版起就是**全线 500**。

    根因：路由是 `async def` + `Depends(get_async_db)`（拿到 AsyncSession），
    却把**异步会话直接喂给同步校验器**：
      - `validate_database_design(db)` 内部 `inspect(db.bind)` →
        "Inspection on an AsyncEngine is currently not supported"；
      - `validate_data_ingestion_process(db)` 内部 `db.execute()` 返回的是协程，
        后面 `.fetchall()` 直接炸；
      - `validate_field_mapping(db)` 的签名是 `(mapped_rows, data_domain)`，
        本来就不是「拿会话」的函数 —— 传会话进去必错。

    修法（按校验器性质分两类）：
      1. **依赖 SQLAlchemy Inspector 的同步校验器**（表结构 / 物化视图 / 入库流程）
         —— Inspector 只认同步引擎，放到 **worker 线程 + 仓库同步引擎** 里跑：
         既不阻塞事件循环（实测 3.2s，不占着主循环），也不碰 asyncpg 的
         greenlet 桥接（详见 `_run_sync_validator` 的说明）。
      2. **字典校验**（`/validate/field-mapping`）—— 用请求自己的 AsyncSession
         直接查，纯读、不写库。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.models.database import SessionLocal, get_async_db
from backend.services.database_design_validator import validate_database_design
from backend.services.data_ingestion_validator import validate_data_ingestion_process
from backend.services.field_mapping_validator import validate_field_mapping_dictionary
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/database-design", tags=["数据库设计规范验证"])


async def _run_sync_validator(func, *args, **kwargs):
    """在线程池里跑一个同步校验器（阻塞型 IO 不占着事件循环）。

    为什么不用「从异步会话派生的同步引擎」（`async_engine.sync_engine`）：
    那条路的连接是 **asyncpg** 的，靠 SQLAlchemy 的 greenlet 桥接，
    **只能在事件循环所在的那个线程里用**。丢到 worker 线程会直接报
    `MissingGreenlet: greenlet_spawn has not been called`（2026-10-31 实测）。

    所以这里用仓库自己的**同步引擎**（`backend.models.database.engine`）
    开一个会话，放到线程池里跑：
      - SQLAlchemy Inspector 本来就只认同步引擎；
      - 校验器是只读元数据操作，耗时 3~6 秒，放 worker 线程不占主循环；
      - 同步引擎用 psycopg2（requirements.txt 里是硬依赖），与 asyncpg 互不干扰。
    """

    def _work():
        db = SessionLocal()
        try:
            return func(db, *args, **kwargs)
        finally:
            db.close()

    return await run_in_threadpool(_work)


@router.get("/validate")
async def validate_design():
    """
    验证数据库设计是否符合规范

    [*] v4.12.0新增:验证数据库模型、索引、外键、物化视图是否符合设计规范

    返回:
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
        result = await _run_sync_validator(validate_database_design)

        # 转换为字典格式
        issues_dict = []
        for issue in result.issues:
            issues_dict.append(
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "table_name": issue.table_name,
                    "field_name": issue.field_name,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion,
                }
            )

        data = {
            "is_valid": result.is_valid,
            "summary": result.summary,
            "issues": issues_dict,
        }

        return success_response(data=data)
    except Exception as e:
        logger.error(f"验证数据库设计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500,
        )


@router.get("/validate/tables")
async def validate_tables():
    """验证表结构"""
    try:
        validator = await _run_sync_validator(validate_database_design)
        table_issues = [
            i
            for i in validator.issues
            if i.category in ["primary_key", "nullable", "index", "foreign_key"]
        ]

        data = {
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "table_name": issue.table_name,
                    "field_name": issue.field_name,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion,
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
            status_code=500,
        )


@router.get("/validate/materialized-views")
async def validate_materialized_views():
    """验证物化视图"""
    try:
        validator = await _run_sync_validator(validate_database_design)
        mv_issues = [i for i in validator.issues if i.category == "materialized_view"]

        return {
            "success": True,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "table_name": issue.table_name,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion,
                }
                for issue in mv_issues
            ],
        }
    except Exception as e:
        logger.error(f"验证物化视图失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证物化视图失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500,
        )


@router.get("/validate/field-mapping")
async def validate_field_mapping_endpoint(db: AsyncSession = Depends(get_async_db)):
    """
    验证字段映射

    [*] v4.12.0新增:验证字段映射是否符合设计规范

    返回:
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
        # 字段映射字典（core.field_mapping_dictionary）是采集映射的单一数据源，
        # 这里直接校验它本身够不够用：数值型字段的 data_type 有没有被写成 string、
        # 分组/类型有没有填、有没有域一个必填字段都没标。
        # 用请求自己的 AsyncSession 直接查（纯读），不另开会话。
        result = await validate_field_mapping_dictionary(db)

        data = {
            "is_valid": result["is_valid"],
            "summary": result["summary"],
            "issues": result["issues"],
        }

        return success_response(data=data)
    except Exception as e:
        logger.error(f"验证字段映射失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500,
        )


@router.get("/validate/data-ingestion")
async def validate_data_ingestion():
    """
    验证数据入库流程

    [*] v4.12.0新增:验证数据入库流程是否符合设计规范

    返回:
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
        result = await _run_sync_validator(validate_data_ingestion_process)

        # 转换为字典格式
        issues_dict = []
        for issue in result.issues:
            issues_dict.append(
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "issue": issue.issue,
                    "suggestion": issue.suggestion,
                    "code_location": issue.code_location,
                }
            )

        return {
            "success": True,
            "is_valid": result.is_valid,
            "summary": result.summary,
            "issues": issues_dict,
        }
    except Exception as e:
        logger.error(f"验证数据入库流程失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="验证数据入库流程失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数,或联系系统管理员",
            status_code=500,
        )
