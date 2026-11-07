#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准字段定义 / 语义别名路由(批次 D · API-1 / API-5)。

为什么要这几个接口
----------------
前端以前在 ``frontend/src/domains/data_platform/utils/headerBindings.js``
里**自己抄了一份**标准字段定义(360 行)。实测两份已经漂了:

* 41 个字段里, 前端普遍缺 ``domain`` / ``required`` / ``system_scope``
  ⇒ 前端算出来的 ``required`` 永远是 false, 与后端契约判定对不上;
* ``product_name`` 前端叫「商品名」后端叫「商品名称」;
* 5 个字段的别名列表对不上。

⇒ 用户在前端看到的选项 ≠ 后端实际认定(FE-1), 前端推断与后端推断各写各的(FE-2)。

这几个接口把「唯一一份定义」暴露出来, 前端不再抄:

* ``GET  /semantic-fields/definitions``      —— 标准字段 + 别名 + required + hash_eligible + 域适用范围;
* ``GET  /semantic-fields/aliases``          —— 别名表(含运行时沉淀出来的);
* ``GET  /semantic-fields/aliases/conflicts``—— 冲突清单(同一个列名撞两个含义);
* ``POST /semantic-fields/aliases/resolve``  —— 别名裁决(API-5);
* ``POST /semantic-fields/resolve-columns``  —— 批量「列名 → 语义键」解析(前端不再自己猜)。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.semantic_fields import (
    SemanticAliasConflict,
    SemanticAliasConflictListData,
    SemanticAliasConflictListResponse,
    SemanticAliasListData,
    SemanticAliasListResponse,
    SemanticAliasResolveData,
    SemanticAliasResolveRequest,
    SemanticAliasResolveResponse,
    SemanticAliasRow,
    SemanticColumnResolveData,
    SemanticColumnResolveItem,
    SemanticColumnResolveRequest,
    SemanticColumnResolveResponse,
    SemanticFieldDefinitionsData,
    SemanticFieldDefinitionsResponse,
)
from backend.services.semantic_field_registry import (
    build_semantic_field_definitions_payload,
    infer_semantic_key_for_domain,
    is_canonical_semantic_key,
    load_runtime_aliases,
)
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

_ALIAS_TABLE = "semantic.semantic_field_aliases"


@router.get(
    "/semantic-fields/definitions",
    response_model=SemanticFieldDefinitionsResponse,
)
async def get_semantic_field_definitions(
    db: AsyncSession = Depends(get_async_db),
):
    """API-1: 标准字段定义的只读投影(前端唯一来源)。"""
    try:
        # 运行时别名随时可能被沉淀/裁决刷新, 这里保证读到的是最新状态。
        await load_runtime_aliases(db)
        payload = build_semantic_field_definitions_payload()
        return SemanticFieldDefinitionsResponse(
            success=True,
            data=SemanticFieldDefinitionsData(**payload),
            message="获取标准字段定义成功",
        )
    except Exception as exc:
        logger.error(f"获取标准字段定义失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"获取标准字段定义失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(exc),
            recovery_suggestion="请稍后重试, 或联系系统管理员",
            status_code=500,
        )


@router.get(
    "/semantic-fields/aliases",
    response_model=SemanticAliasListResponse,
)
async def list_semantic_aliases(
    data_domain: Optional[str] = Query(
        None, description="按数据域过滤, '*' 表示不限域"
    ),
    status: Optional[str] = Query(
        None, description="按状态过滤: active / disabled / conflict"
    ),
    source: Optional[str] = Query(
        None, description="按来源过滤: builtin / template_confirmed / manual"
    ),
    limit: int = Query(200, ge=1, le=2000, description="最多返回多少行"),
    db: AsyncSession = Depends(get_async_db),
):
    """列出语义别名表(含用户在模板里沉淀出来的)。"""
    try:
        conditions: List[str] = []
        params: Dict[str, Any] = {"limit": limit}
        if data_domain:
            conditions.append("data_domain = :data_domain")
            params["data_domain"] = data_domain
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if source:
            conditions.append("source = :source")
            params["source"] = source
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = text(
            f"""
            SELECT id, data_domain, standard_field, raw_alias, platform_code, granularity,
                   source, confidence, status, created_at, updated_at
            FROM {_ALIAS_TABLE}
            {where_clause}
            ORDER BY data_domain, raw_alias, id
            LIMIT :limit
            """
        )
        rows = list((await db.execute(sql, params)).mappings().all())
        aliases = [
            SemanticAliasRow(
                id=int(row["id"]) if row.get("id") is not None else None,
                data_domain=str(row.get("data_domain") or ""),
                standard_field=str(row.get("standard_field") or ""),
                raw_alias=str(row.get("raw_alias") or ""),
                platform_code=row.get("platform_code"),
                granularity=row.get("granularity"),
                source=str(row.get("source") or "builtin"),
                confidence=float(row.get("confidence") or 1.0),
                status=str(row.get("status") or "active"),
                created_at=(
                    row["created_at"].isoformat() if row.get("created_at") else None
                ),
                updated_at=(
                    row["updated_at"].isoformat() if row.get("updated_at") else None
                ),
            )
            for row in rows
        ]
        return SemanticAliasListResponse(
            success=True,
            data=SemanticAliasListData(aliases=aliases, total=len(aliases)),
            message="获取语义别名列表成功",
        )
    except Exception as exc:
        logger.error(f"获取语义别名列表失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message=f"获取语义别名列表失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.get(
    "/semantic-fields/aliases/conflicts",
    response_model=SemanticAliasConflictListResponse,
)
async def list_semantic_alias_conflicts(
    db: AsyncSession = Depends(get_async_db),
):
    """列出待裁决的别名冲突。

    冲突的形态是: 同一个 (域, 列名, 平台, 粒度) 下,
    有一条 ``status='active'`` 的生效记录, 又有一条 ``status='conflict'`` 的候选记录
    —— 后者的 ``standard_field`` 带 ``__conflict__`` 前缀, 记录的是「新断言的语义键」。
    """
    try:
        sql = text(
            f"""
            SELECT conflict.id AS conflict_id,
                   conflict.data_domain,
                   conflict.raw_alias,
                   conflict.platform_code,
                   conflict.granularity,
                   conflict.source,
                   conflict.status,
                   conflict.standard_field AS conflicting_standard_field,
                   active.standard_field AS active_standard_field
            FROM {_ALIAS_TABLE} AS conflict
            JOIN {_ALIAS_TABLE} AS active
              ON active.data_domain = conflict.data_domain
             AND active.raw_alias = conflict.raw_alias
             AND COALESCE(active.platform_code, '') = COALESCE(conflict.platform_code, '')
             AND COALESCE(active.granularity, '') = COALESCE(conflict.granularity, '')
             AND active.status = 'active'
            WHERE conflict.status = 'conflict'
            ORDER BY conflict.data_domain, conflict.raw_alias, conflict.id
            """
        )
        rows = list((await db.execute(sql)).mappings().all())
        conflicts = []
        for row in rows:
            conflicting_key = str(row.get("conflicting_standard_field") or "")
            if conflicting_key.startswith("__conflict__"):
                conflicting_key = conflicting_key[len("__conflict__") :]
            conflicts.append(
                SemanticAliasConflict(
                    data_domain=str(row.get("data_domain") or ""),
                    raw_alias=str(row.get("raw_alias") or ""),
                    platform_code=row.get("platform_code"),
                    granularity=row.get("granularity"),
                    active_semantic_key=str(row.get("active_standard_field") or ""),
                    conflicting_semantic_key=conflicting_key,
                    conflict_id=(
                        int(row["conflict_id"])
                        if row.get("conflict_id") is not None
                        else None
                    ),
                    source=str(row.get("source") or "manual"),
                    status=str(row.get("status") or "conflict"),
                )
            )
        return SemanticAliasConflictListResponse(
            success=True,
            data=SemanticAliasConflictListData(
                conflicts=conflicts, total=len(conflicts)
            ),
            message="获取别名冲突列表成功",
        )
    except Exception as exc:
        logger.error(f"获取别名冲突列表失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message=f"获取别名冲突列表失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.post(
    "/semantic-fields/aliases/resolve",
    response_model=SemanticAliasResolveResponse,
)
async def resolve_semantic_alias(
    payload: SemanticAliasResolveRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """API-5: 裁决一个别名冲突。

    三种动作:

    * ``accept``  —— 用户选了 ``semantic_key``: 该列名**改判**到这个语义键
      (原 active 行被停用, 新语义键写成 active), 冲突行清掉;
    * ``disable`` —— 用户说「这条别名先别用」: 原 active 行停用, 冲突行清掉;
    * ``reject``  —— 用户说「新断言是错的」: 原 active 行保持, 冲突行清掉。

    三种动作都**不会**删除历史行(只改 status), 便于回溯。
    """
    try:
        semantic_key = str(payload.semantic_key or "").strip()
        raw_alias = str(payload.raw_alias or "").strip()
        data_domain = str(payload.data_domain or "").strip() or "*"
        if not semantic_key or not raw_alias:
            raise ValueError("semantic_key 与 raw_alias 都不能为空")

        now = await db.execute(text("SELECT now()"))
        now_value = now.scalar()

        affected = 0
        if payload.action == "accept":
            if not is_canonical_semantic_key(semantic_key):
                raise ValueError(f"未知语义键: {semantic_key}")
            # 1. 原 active 行停用(同 (域, 列名, 平台, 粒度) 下指向别的语义键的)
            disable_sql = text(
                f"""
                UPDATE {_ALIAS_TABLE}
                SET status = 'disabled', updated_at = :now
                WHERE data_domain = :data_domain
                  AND raw_alias = :raw_alias
                  AND COALESCE(platform_code, '') = COALESCE(:platform_code, '')
                  AND COALESCE(granularity, '') = COALESCE(:granularity, '')
                  AND status = 'active'
                  AND standard_field <> :semantic_key
                """
            )
            affected += int(
                (
                    await db.execute(
                        disable_sql,
                        {
                            "now": now_value,
                            "data_domain": data_domain,
                            "raw_alias": raw_alias,
                            "platform_code": payload.platform_code,
                            "granularity": payload.granularity,
                            "semantic_key": semantic_key,
                        },
                    )
                ).rowcount
                or 0
            )
            # 2. 新语义键写成 active
            upsert_sql = text(
                f"""
                INSERT INTO {_ALIAS_TABLE} (
                    data_domain, standard_field, raw_alias, platform_code, granularity,
                    source, confidence, status, created_at, updated_at
                )
                VALUES (
                    :data_domain, :semantic_key, :raw_alias, :platform_code, :granularity,
                    'manual', 1.000, 'active', :now, :now
                )
                ON CONFLICT (data_domain, standard_field, raw_alias,
                             COALESCE(platform_code, ''), COALESCE(granularity, ''))
                DO UPDATE SET status = 'active', updated_at = EXCLUDED.updated_at
                """
            )
            affected += int(
                (
                    await db.execute(
                        upsert_sql,
                        {
                            "now": now_value,
                            "data_domain": data_domain,
                            "semantic_key": semantic_key,
                            "raw_alias": raw_alias,
                            "platform_code": payload.platform_code,
                            "granularity": payload.granularity,
                        },
                    )
                ).rowcount
                or 0
            )
        elif payload.action == "disable":
            disable_sql = text(
                f"""
                UPDATE {_ALIAS_TABLE}
                SET status = 'disabled', updated_at = :now
                WHERE data_domain = :data_domain
                  AND raw_alias = :raw_alias
                  AND COALESCE(platform_code, '') = COALESCE(:platform_code, '')
                  AND COALESCE(granularity, '') = COALESCE(:granularity, '')
                  AND status = 'active'
                """
            )
            affected += int(
                (
                    await db.execute(
                        disable_sql,
                        {
                            "now": now_value,
                            "data_domain": data_domain,
                            "raw_alias": raw_alias,
                            "platform_code": payload.platform_code,
                            "granularity": payload.granularity,
                        },
                    )
                ).rowcount
                or 0
            )

        # 3. 冲突行清掉(无论 accept / disable / reject, 裁决完就不再是冲突)
        clear_conflict_sql = text(
            f"""
            UPDATE {_ALIAS_TABLE}
            SET status = 'disabled', updated_at = :now
            WHERE data_domain = :data_domain
              AND raw_alias = :raw_alias
              AND COALESCE(platform_code, '') = COALESCE(:platform_code, '')
              AND COALESCE(granularity, '') = COALESCE(:granularity, '')
              AND status = 'conflict'
            """
        )
        affected += int(
            (
                await db.execute(
                    clear_conflict_sql,
                    {
                        "now": now_value,
                        "data_domain": data_domain,
                        "raw_alias": raw_alias,
                        "platform_code": payload.platform_code,
                        "granularity": payload.granularity,
                    },
                )
            ).rowcount
            or 0
        )
        await db.commit()

        # 裁决结果立刻进推断索引 —— 不用等重启。
        await load_runtime_aliases(db)

        messages = {
            "accept": f"已把「{raw_alias}」改判为 {semantic_key}",
            "disable": f"已停用「{raw_alias}」的生效别名",
            "reject": f"已驳回「{raw_alias}」的新断言, 原有别名保持不变",
        }
        return SemanticAliasResolveResponse(
            success=True,
            data=SemanticAliasResolveData(
                action=payload.action,
                data_domain=data_domain,
                raw_alias=raw_alias,
                semantic_key=semantic_key,
                affected_rows=affected,
                message=messages.get(payload.action, "裁决完成"),
            ),
            message=messages.get(payload.action, "裁决完成"),
        )
    except ValueError as exc:
        return error_response(
            code=ErrorCode.PARAMETER_INVALID,
            message=f"别名裁决失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.PARAMETER_INVALID),
            detail=str(exc),
            recovery_suggestion="请检查语义键与列名是否正确",
            status_code=400,
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"别名裁决失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message=f"别名裁决失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            recovery_suggestion="请检查数据库连接和权限, 或联系系统管理员",
            status_code=500,
        )


@router.post(
    "/semantic-fields/resolve-columns",
    response_model=SemanticColumnResolveResponse,
)
async def resolve_semantic_columns(
    payload: SemanticColumnResolveRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """批量「列名 → 语义键」解析。

    前端以前自己写一套逐字相等的匹配, 与后端各写各的(FE-2) ——
    前端显示「已自动识别」, 后端却不认。
    现在前端把整批列名交给后端解析, **两边用的是同一套规则**。
    """
    try:
        await load_runtime_aliases(db)
        data_domain = str(payload.data_domain or "").strip()
        results: List[SemanticColumnResolveItem] = []
        for column in payload.columns or []:
            raw = str(column or "")
            if not raw.strip():
                continue
            semantic_key = infer_semantic_key_for_domain(data_domain, raw)
            results.append(
                SemanticColumnResolveItem(
                    column=raw,
                    semantic_key=semantic_key,
                    source="registry" if semantic_key else "none",
                )
            )
        return SemanticColumnResolveResponse(
            success=True,
            data=SemanticColumnResolveData(results=results, data_domain=data_domain),
            message="列名语义解析完成",
        )
    except Exception as exc:
        logger.error(f"列名语义解析失败: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=f"列名语义解析失败: {str(exc)}",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(exc),
            recovery_suggestion="请稍后重试, 或联系系统管理员",
            status_code=500,
        )
