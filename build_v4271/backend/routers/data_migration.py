"""
数据迁移 API 端点

提供数据导出和导入功能,支持小数据量配置类数据的快速同步

安全措施:
- 表名白名单验证(只允许 ORM 定义的表)
- 列名白名单验证(只允许表中存在的列)
- 参数化查询(防止 SQL 注入)
- 分页支持(防止内存溢出)
- 仅管理员可访问
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import get_async_db, Base
from backend.dependencies.auth import require_admin
from modules.core.db import DimUser
from modules.core.logger import get_logger
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from typing import List, Dict, Any, Optional
import re

logger = get_logger(__name__)
router = APIRouter(prefix="/data", tags=["数据迁移"])


# [安全] 白名单验证:只允许导出/导入 ORM 定义的表
def get_allowed_tables() -> set:
    """获取允许操作的表名白名单(从 ORM 元数据获取)"""
    return set(Base.metadata.tables.keys())


def validate_table_name(table_name: str) -> bool:
    """验证表名是否在白名单中,防止 SQL 注入"""
    # 1. 白名单验证
    if table_name not in get_allowed_tables():
        return False
    # 2. 格式验证(只允许字母、数字、下划线)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        return False
    return True


def validate_column_names(columns: List[str], valid_columns: set) -> bool:
    """验证列名是否有效,防止 SQL 注入"""
    for col in columns:
        if col not in valid_columns:
            return False
        # 格式验证
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
            return False
    return True


@router.post("/export")
async def export_data(
    tables: List[str],
    limit: Optional[int] = 10000,  # [性能] 添加分页支持,默认最多 10000 条
    offset: Optional[int] = 0,
    current_user: DimUser = Depends(require_admin),  # 仅管理员可访问
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出指定表的数据(仅管理员)

    安全措施:
    - 表名白名单验证(只允许 ORM 定义的表)
    - 参数化查询(防止 SQL 注入)
    - 分页支持(防止内存溢出)
    """
    data = {}

    for table_name in tables:
        try:
            # [安全] 白名单验证
            if not validate_table_name(table_name):
                return error_response(
                    code=ErrorCode.PARAMETER_INVALID,
                    message=f"不允许导出表 {table_name}(不在白名单中)",
                    error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
                    detail=f"表 {table_name} 不在白名单中",
                    recovery_suggestion="请使用正确的表名或联系管理员添加表到白名单",
                    status_code=400
                )

            # 验证表是否存在
            result = await db.execute(
                text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name)"),
                {"table_name": table_name}
            )
            if not result.scalar():
                return error_response(
                    code=ErrorCode.DATA_NOT_FOUND,
                    message=f"表 {table_name} 不存在",
                    error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                    detail=f"表 {table_name} 在数据库中不存在",
                    recovery_suggestion="请检查表名是否正确,或确认表是否已创建",
                    status_code=404
                )

            # [安全] 使用参数化查询 + 白名单验证后的表名
            # 注意:表名无法参数化,必须先做白名单/格式校验
            # [性能] 添加分页支持
            query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
            result = await db.execute(query, {"limit": limit, "offset": offset})
            rows = result.fetchall()
            # 转换为字典列表
            columns = result.keys()
            data[table_name] = [dict(zip(columns, row)) for row in rows]
        except HTTPException:
            # 重新抛出依赖注入中的 HTTPException(如 require_admin),依赖注入函数已记录日志
            raise
        except Exception as e:
            logger.error(f"导出表 {table_name} 失败: {str(e)}", exc_info=True)
            return error_response(
                code=ErrorCode.DATABASE_QUERY_ERROR,
                message=f"导出表 {table_name} 失败",
                error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                detail=str(e),
                recovery_suggestion="请稍后重试,如问题持续存在请联系系统管理员",
                status_code=500
            )

    return {
        "success": True,
        "data": data,
        "message": f"成功导出 {len(tables)} 张表的数据",
        "pagination": {"limit": limit, "offset": offset}
    }


@router.post("/import")
async def import_data(
    data: Dict[str, List[Dict[str, Any]]],
    on_conflict: str = "skip",  # [功能] 冲突处理策略:skip(跳过)、update(更新)、error(报错)
    current_user: DimUser = Depends(require_admin),  # 仅管理员可访问
    db: AsyncSession = Depends(get_async_db)
):
    """
    导入数据(仅管理员)

    安全措施:
    - 表名白名单验证(只允许 ORM 定义的表)
    - 列名白名单验证(只允许表中存在的列)
    - 参数化查询(防止 SQL 注入)

    冲突处理策略:
    - skip:跳过冲突记录(ON CONFLICT DO NOTHING)
    - update:更新冲突记录(真正的 UPSERT,自动检测主键列)
      - 自动获取表的主键列(支持单列和复合主键)
      - 如果主键冲突,更新所有非主键列
      - 如果表没有主键或主键列不在导入数据中,会报错
    - error:遇到冲突时报错
    """
    if on_conflict not in ("skip", "update", "error"):
        return error_response(
            code=ErrorCode.PARAMETER_INVALID,
            message="on_conflict 参数必须是 skip、update 或 error",
            error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
            detail=f"无效的 on_conflict 值: {on_conflict}",
            recovery_suggestion="请使用 skip、update 或 error 作为 on_conflict 参数值",
            status_code=400
        )

    try:
        imported_tables = []
        skipped_count = 0

        for table_name, records in data.items():
            if not records:
                continue

            try:
                # [安全] 白名单验证
                if not validate_table_name(table_name):
                    return error_response(
                        code=ErrorCode.PARAMETER_INVALID,
                        message=f"不允许导入表 {table_name}(不在白名单中)",
                        error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
                        detail=f"表 {table_name} 不在白名单中",
                        recovery_suggestion="请使用正确的表名或联系管理员添加表到白名单",
                        status_code=400
                    )

                # 验证表是否存在
                result = await db.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :table_name)"),
                    {"table_name": table_name}
                )
                if not result.scalar():
                    return error_response(
                        code=ErrorCode.DATA_NOT_FOUND,
                        message=f"表 {table_name} 不存在",
                        error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                        detail=f"表 {table_name} 在数据库中不存在",
                        recovery_suggestion="请检查表名是否正确,或确认表是否已创建",
                        status_code=404
                    )

                # [安全] 获取表的有效列名(用于白名单验证)
                result = await db.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table_name"),
                    {"table_name": table_name}
                )
                valid_columns = {row[0] for row in result.fetchall()}

                if records:
                    # 获取列名并验证
                    columns = list(records[0].keys())

                    # [安全] 列名白名单验证
                    if not validate_column_names(columns, valid_columns):
                        invalid_cols = set(columns) - valid_columns
                        return error_response(
                            code=ErrorCode.PARAMETER_INVALID,
                            message=f"无效列名: {invalid_cols}",
                            error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
                            detail=f"表 {table_name} 中不存在以下列: {invalid_cols}",
                            recovery_suggestion="请检查列名是否正确,或确认列是否存在于表中",
                            status_code=400
                        )

                    # [安全] 构建参数化插入语句
                    # 注意:表名和列名不能参数化,但已通过白名单验证确保安全
                    # 为安全起见,列名使用引号转义
                    columns_str = ", ".join([f'"{col}"' for col in columns])
                    placeholders = ", ".join([f":{col}" for col in columns])

                    # [功能] 根据冲突处理策略构建 SQL
                    # 注意:表名已通过白名单验证,为安全起见使用引号转义
                    if on_conflict == "skip":
                        sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                    elif on_conflict == "error":
                        sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'
                    else:  # update:实现真正的 UPSERT
                        # [功能] 获取表的主键列
                        pk_result = await db.execute(
                            text("""
                                SELECT a.attname
                                FROM pg_constraint c
                                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                                WHERE c.contype = 'p'
                                AND c.conrelid = :table_name::regclass
                                ORDER BY array_position(c.conkey, a.attnum)
                            """),
                            {"table_name": table_name}
                        )
                        pk_columns = [row[0] for row in pk_result.fetchall()]
                        
                        if not pk_columns:
                            # 表没有主键,降级为 skip
                            return error_response(
                                code=ErrorCode.DATA_VALIDATION_FAILED,
                                message=f"表 {table_name} 没有主键,无法使用 update 策略",
                                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                                detail=f"表 {table_name} 缺少主键约束",
                                recovery_suggestion="请使用 skip 或 error 策略,或为表添加主键",
                                status_code=400
                            )
                        
                        # 验证主键列是否在导入的列中
                        missing_pk_cols = set(pk_columns) - set(columns)
                        if missing_pk_cols:
                            return error_response(
                                code=ErrorCode.DATA_VALIDATION_FAILED,
                                message=f"主键列 {missing_pk_cols} 不在导入数据中,无法使用 update 策略",
                                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                                detail=f"表 {table_name} 的主键列 {missing_pk_cols} 未在导入数据中提供",
                                recovery_suggestion="请确保导入数据中包含所有主键列",
                                status_code=400
                            )
                        
                        # 构建 ON CONFLICT 子句(支持复合主键)
                        # 注意:必须对列名进行转义(虽然已通过白名单验证,但为安全起见使用引号)
                        pk_cols_str = ", ".join([f'"{col}"' for col in pk_columns])
                        conflict_clause = f"ON CONFLICT ({pk_cols_str})"
                        
                        # 构建 UPDATE SET 子句(更新所有非主键列)
                        update_columns = [col for col in columns if col not in pk_columns]
                        if not update_columns:
                            # 只有主键列,降级为 skip
                            sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({pk_cols_str}) DO NOTHING'
                        else:
                            # 注意:列名已通过白名单验证,为安全起见使用引号转义
                            update_set_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_columns])
                            sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders}) {conflict_clause} DO UPDATE SET {update_set_clause}'

                    # 批量插入
                    for record in records:
                        try:
                            await db.execute(text(sql), record)
                        except Exception as e:
                            if on_conflict == "error":
                                logger.error(f"导入表 {table_name} 记录失败: {str(e)}", exc_info=True)
                                raise
                            logger.warning(f"导入表 {table_name} 记录冲突,跳过: {str(e)}")
                            skipped_count += 1

                imported_tables.append(table_name)
            except HTTPException:
                raise  # 重新抛出依赖注入中的 HTTPException
            except Exception as e:
                logger.error(f"导入表 {table_name} 失败: {str(e)}", exc_info=True)
                return error_response(
                    code=ErrorCode.DATABASE_QUERY_ERROR,
                    message=f"导入表 {table_name} 失败",
                    error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
                    detail=str(e),
                    recovery_suggestion="请检查数据格式和表结构,或稍后重试",
                    status_code=500
                )

        await db.commit()

        return {
            "success": True,
            "message": f"成功导入 {len(imported_tables)} 张表的数据",
            "imported_tables": imported_tables,
            "skipped_count": skipped_count
        }
    except HTTPException:
        await db.rollback()
        # 重新抛出依赖注入中的 HTTPException,依赖注入函数已记录日志
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"数据导入失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据导入失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据格式和表结构,或稍后重试",
            status_code=500
        )
