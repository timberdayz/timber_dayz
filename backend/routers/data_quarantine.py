"""
数据隔离区 API

兼容两类数据结构：
- modern: 使用 SSOT `DataQuarantine` ORM 字段
- legacy: 使用线上遗留 `core.data_quarantine(platform, data_type, quarantine_reason, raw_data, created_at)`
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.schemas.data_quarantine import ReprocessRequest
from backend.utils.api_response import error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import CatalogFile, DataQuarantine
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/data-quarantine", tags=["数据隔离区"])

ERROR_TYPES = {
    "missing_c_class_core_field": "C类数据计算所需核心字段缺失",
    "invalid_currency_policy": "货币策略不符合要求",
    "data_domain_mismatch": "数据域不匹配",
    "validation_error": "数据验证失败",
    "data_type_error": "数据类型错误",
    "required_field_missing": "必填字段缺失",
    "unknown": "未知错误",
}


def detect_quarantine_schema(column_names: set[str]) -> str:
    modern_columns = {
        "catalog_file_id",
        "platform_code",
        "data_domain",
        "error_type",
        "error_msg",
        "row_number",
    }
    legacy_columns = {
        "platform",
        "data_type",
        "quarantine_reason",
        "raw_data",
        "created_at",
    }
    if modern_columns.issubset(column_names):
        return "modern"
    if legacy_columns.issubset(column_names):
        return "legacy"
    return "unknown"


def _parse_raw_data(raw_data: Any) -> Dict[str, Any]:
    if isinstance(raw_data, dict):
        return raw_data
    if isinstance(raw_data, str):
        try:
            parsed = json.loads(raw_data)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def build_legacy_file_groups(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        raw_data = _parse_raw_data(row.get("raw_data"))
        file_name = (
            raw_data.get("source_file")
            or raw_data.get("file_name")
            or f"legacy-{row.get('platform', 'unknown')}-{row.get('data_type', 'unknown')}"
        )
        key = (file_name, row.get("platform"), row.get("data_type"))
        if key not in grouped:
            created_at = row.get("created_at")
            grouped[key] = {
                "file_id": row.get("id"),
                "file_name": file_name,
                "platform_code": row.get("platform"),
                "data_domain": row.get("data_type"),
                "error_count": 0,
                "error_types": {},
                "created_at": (
                    created_at.isoformat()
                    if hasattr(created_at, "isoformat")
                    else created_at
                ),
            }
        grouped[key]["error_count"] += 1
        error_type = row.get("quarantine_reason") or "unknown"
        grouped[key]["error_types"][error_type] = (
            grouped[key]["error_types"].get(error_type, 0) + 1
        )
    return sorted(grouped.values(), key=lambda item: item["error_count"], reverse=True)


def build_legacy_filter_clause(
    platform: Optional[str] = None,
    data_domain: Optional[str] = None,
) -> tuple[str, Dict[str, str]]:
    clauses: List[str] = []
    params: Dict[str, str] = {}
    if platform:
        clauses.append("platform = :platform")
        params["platform"] = platform
    if data_domain:
        clauses.append("data_type = :data_domain")
        params["data_domain"] = data_domain
    if not clauses:
        return "", {}
    return " where " + " and ".join(clauses), params


async def _get_quarantine_column_names(db: AsyncSession) -> set[str]:
    result = await db.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'core' and table_name = 'data_quarantine'
            """
        )
    )
    return {row[0] for row in result.fetchall()}


async def _list_legacy_rows(
    db: AsyncSession,
    platform: Optional[str] = None,
    data_domain: Optional[str] = None,
) -> List[Dict[str, Any]]:
    where_clause, params = build_legacy_filter_clause(
        platform=platform, data_domain=data_domain
    )
    result = await db.execute(
        text(
            f"""  # nosec B608
            select id, platform, data_type, quarantine_reason, raw_data, created_at
            from core.data_quarantine
            {where_clause}
            order by created_at desc
            """
        ),
        params,
    )
    return [
        {
            "id": row[0],
            "platform": row[1],
            "data_type": row[2],
            "quarantine_reason": row[3],
            "raw_data": row[4],
            "created_at": row[5],
        }
        for row in result.fetchall()
    ]


@router.get("/list")
async def list_quarantine_data(
    file_id: Optional[int] = Query(None),
    platform: Optional[str] = Query(None),
    data_domain: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if schema_mode == "legacy":
            rows = await _list_legacy_rows(
                db, platform=platform, data_domain=data_domain
            )
            if error_type:
                rows = [
                    row for row in rows if row.get("quarantine_reason") == error_type
                ]
            total = len(rows)
            rows = rows[(page - 1) * page_size : page * page_size]
            data = [
                {
                    "id": row["id"],
                    "file_id": row["id"],
                    "file_name": _parse_raw_data(row["raw_data"]).get("source_file")
                    or _parse_raw_data(row["raw_data"]).get("file_name")
                    or f"legacy-{row['platform']}-{row['data_type']}",
                    "platform_code": row["platform"],
                    "data_domain": row["data_type"],
                    "row_index": row["id"],
                    "error_type": row["quarantine_reason"],
                    "error_message": ERROR_TYPES.get(
                        row["quarantine_reason"], row["quarantine_reason"]
                    ),
                    "error_type_label": ERROR_TYPES.get(
                        row["quarantine_reason"], row["quarantine_reason"]
                    ),
                    "created_at": (
                        row["created_at"].isoformat()
                        if hasattr(row["created_at"], "isoformat")
                        else row["created_at"]
                    ),
                }
                for row in rows
            ]
            return pagination_response(
                data=data, page=page, page_size=page_size, total=total
            )

        query = select(DataQuarantine)
        conditions = []
        if file_id:
            conditions.append(DataQuarantine.catalog_file_id == file_id)
        if platform:
            conditions.append(DataQuarantine.platform_code == platform)
        if data_domain:
            conditions.append(DataQuarantine.data_domain == data_domain)
        if error_type:
            conditions.append(DataQuarantine.error_type == error_type)
        if conditions:
            query = query.where(and_(*conditions))

        count_query = select(func.count()).select_from(DataQuarantine)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = (await db.execute(count_query)).scalar_one()

        result = await db.execute(
            query.order_by(DataQuarantine.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = result.scalars().all()
        data = []
        for item in items:
            file_info = None
            if item.catalog_file_id:
                file_info = (
                    await db.execute(
                        select(CatalogFile).where(
                            CatalogFile.id == item.catalog_file_id
                        )
                    )
                ).scalar_one_or_none()
            data.append(
                {
                    "id": item.id,
                    "file_id": item.catalog_file_id or item.id,
                    "file_name": file_info.file_name if file_info else item.source_file,
                    "platform_code": item.platform_code,
                    "data_domain": item.data_domain,
                    "row_index": item.row_number,
                    "error_type": item.error_type,
                    "error_message": item.error_msg,
                    "error_type_label": ERROR_TYPES.get(
                        item.error_type, item.error_type
                    ),
                    "created_at": (
                        item.created_at.isoformat() if item.created_at else None
                    ),
                }
            )
        return pagination_response(
            data=data, page=page, page_size=page_size, total=total
        )
    except Exception as exc:
        logger.error(f"Failed to list quarantine data: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/detail/{quarantine_id}")
async def get_quarantine_detail(
    quarantine_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if schema_mode == "legacy":
            result = await db.execute(
                text(
                    """
                    select id, platform, data_type, quarantine_reason, raw_data, created_at
                    from core.data_quarantine
                    where id = :quarantine_id
                    """
                ),
                {"quarantine_id": quarantine_id},
            )
            row = result.fetchone()
            if not row:
                return error_response(
                    code=ErrorCode.DATA_QUARANTINED,
                    message=f"隔离数据不存在: ID={quarantine_id}",
                    error_type=get_error_type(ErrorCode.DATA_QUARANTINED),
                    status_code=404,
                )
            raw_data = _parse_raw_data(row[4])
            file_name = (
                raw_data.get("source_file")
                or raw_data.get("file_name")
                or f"legacy-{row[1]}-{row[2]}"
            )
            return {
                "success": True,
                "data": {
                    "id": row[0],
                    "file_id": row[0],
                    "file_name": file_name,
                    "platform_code": row[1],
                    "data_domain": row[2],
                    "row_index": row[0],
                    "raw_data": raw_data,
                    "error_type": row[3],
                    "error_message": ERROR_TYPES.get(row[3], row[3]),
                    "validation_errors": {},
                    "created_at": (
                        row[5].isoformat() if hasattr(row[5], "isoformat") else row[5]
                    ),
                },
            }

        result = await db.execute(
            select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return error_response(
                code=ErrorCode.DATA_QUARANTINED,
                message=f"隔离数据不存在: ID={quarantine_id}",
                error_type=get_error_type(ErrorCode.DATA_QUARANTINED),
                status_code=404,
            )
        file_info = None
        if item.catalog_file_id:
            file_info = (
                await db.execute(
                    select(CatalogFile).where(CatalogFile.id == item.catalog_file_id)
                )
            ).scalar_one_or_none()
        return {
            "success": True,
            "data": {
                "id": item.id,
                "file_id": item.catalog_file_id or item.id,
                "file_name": file_info.file_name if file_info else item.source_file,
                "platform_code": item.platform_code,
                "data_domain": item.data_domain,
                "row_index": item.row_number,
                "raw_data": _parse_raw_data(item.row_data),
                "error_type": item.error_type,
                "error_message": item.error_msg,
                "validation_errors": {},
                "created_at": item.created_at.isoformat() if item.created_at else None,
            },
        }
    except Exception as exc:
        logger.error(f"Failed to get quarantine detail: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取隔离数据详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.post("/reprocess")
async def reprocess_quarantine_data(
    request: ReprocessRequest,
    db: AsyncSession = Depends(get_async_db),
):
    schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
    if schema_mode == "legacy":
        return {
            "success": True,
            "processed": len(request.quarantine_ids),
            "succeeded": 0,
            "failed": len(request.quarantine_ids),
            "errors": [
                {
                    "quarantine_id": qid,
                    "error": "legacy schema does not support reprocess yet",
                }
                for qid in request.quarantine_ids
            ],
        }

    processed = 0
    succeeded = 0
    failed = 0
    errors = []
    try:
        for quarantine_id in request.quarantine_ids:
            result = await db.execute(
                select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
            )
            item = result.scalar_one_or_none()
            if not item:
                failed += 1
                errors.append(
                    {"quarantine_id": quarantine_id, "error": "隔离数据不存在"}
                )
                continue
            processed += 1
            item.is_resolved = True
            item.resolved_at = datetime.now(timezone.utc)
            item.resolution_note = (
                f"手动重新处理 corrections={request.corrections or {}}"
            )
            succeeded += 1
        await db.commit()
        return {
            "success": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors,
        }
    except Exception as exc:
        await db.rollback()
        logger.error(f"Batch reprocess failed: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_ISOLATION_FAILED,
            message="批量重新处理失败",
            error_type=get_error_type(ErrorCode.DATA_ISOLATION_FAILED),
            detail=str(exc),
            status_code=500,
        )


@router.post("/delete")
async def delete_quarantine_data(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if request.get("all") is True:
            if schema_mode == "legacy":
                deleted_count = (
                    await db.execute(text("select count(*) from core.data_quarantine"))
                ).scalar_one()
                await db.execute(text("delete from core.data_quarantine"))
                await db.commit()
                return {"success": True, "deleted": deleted_count}
            deleted_count = (
                await db.execute(select(func.count()).select_from(DataQuarantine))
            ).scalar_one()
            await db.execute(delete(DataQuarantine))
            await db.commit()
            return {"success": True, "deleted": deleted_count}

        quarantine_ids = request.get("quarantine_ids", [])
        if not quarantine_ids:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="quarantine_ids 不能为空",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                status_code=400,
            )

        if schema_mode == "legacy":
            await db.execute(
                text("delete from core.data_quarantine where id = any(:ids)"),
                {"ids": quarantine_ids},
            )
            await db.commit()
            return {"success": True, "deleted": len(quarantine_ids)}

        deleted_count = 0
        for quarantine_id in quarantine_ids:
            result = await db.execute(
                select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
            )
            item = result.scalar_one_or_none()
            if item:
                await db.delete(item)
                deleted_count += 1
        await db.commit()
        return {"success": True, "deleted": deleted_count}
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to delete quarantine data: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/files")
async def list_quarantine_files(
    platform: Optional[str] = Query(None),
    data_domain: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if schema_mode == "legacy":
            rows = await _list_legacy_rows(
                db, platform=platform, data_domain=data_domain
            )
            data = build_legacy_file_groups(rows)
            return {"success": True, "data": data, "total": len(data)}

        query = (
            select(DataQuarantine, CatalogFile)
            .join(
                CatalogFile,
                CatalogFile.id == DataQuarantine.catalog_file_id,
                isouter=True,
            )
            .order_by(DataQuarantine.created_at.desc())
        )
        conditions = []
        if platform:
            conditions.append(DataQuarantine.platform_code == platform)
        if data_domain:
            conditions.append(DataQuarantine.data_domain == data_domain)
        if conditions:
            query = query.where(and_(*conditions))

        result = await db.execute(query)
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for item, file_info in result.fetchall():
            file_name = file_info.file_name if file_info else item.source_file
            key = (
                item.catalog_file_id,
                file_name,
                item.platform_code,
                item.data_domain,
            )
            if key not in grouped:
                grouped[key] = {
                    "file_id": item.catalog_file_id or item.id,
                    "file_name": file_name,
                    "platform_code": item.platform_code,
                    "data_domain": item.data_domain,
                    "error_count": 0,
                    "error_types": {},
                    "created_at": (
                        item.created_at.isoformat() if item.created_at else None
                    ),
                }
            grouped[key]["error_count"] += 1
            error_type = item.error_type or "unknown"
            grouped[key]["error_types"][error_type] = (
                grouped[key]["error_types"].get(error_type, 0) + 1
            )
        data = sorted(
            grouped.values(), key=lambda value: value["error_count"], reverse=True
        )
        return {"success": True, "data": data, "total": len(data)}
    except Exception as exc:
        logger.error(f"Failed to list quarantine files: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询隔离文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/files/{file_id}/rows")
async def list_quarantine_rows_by_file(
    file_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if schema_mode == "legacy":
            rows = await _list_legacy_rows(db)
            groups = build_legacy_file_groups(rows)
            target_group = next(
                (item for item in groups if item["file_id"] == file_id), None
            )
            if not target_group:
                return error_response(
                    code=ErrorCode.FILE_NOT_FOUND,
                    message=f"文件不存在: ID={file_id}",
                    error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                    status_code=404,
                )
            file_name = target_group["file_name"]
            matched = []
            for row in rows:
                raw_data = _parse_raw_data(row["raw_data"])
                row_file_name = (
                    raw_data.get("source_file")
                    or raw_data.get("file_name")
                    or f"legacy-{row['platform']}-{row['data_type']}"
                )
                if (
                    row_file_name == file_name
                    and row["platform"] == target_group["platform_code"]
                    and row["data_type"] == target_group["data_domain"]
                ):
                    matched.append(row)
            total = len(matched)
            matched = matched[(page - 1) * page_size : page * page_size]
            data = [
                {
                    "id": row["id"],
                    "file_id": file_id,
                    "file_name": file_name,
                    "platform_code": row["platform"],
                    "data_domain": row["data_type"],
                    "row_index": row["id"],
                    "error_type": row["quarantine_reason"],
                    "error_message": ERROR_TYPES.get(
                        row["quarantine_reason"], row["quarantine_reason"]
                    ),
                    "error_type_label": ERROR_TYPES.get(
                        row["quarantine_reason"], row["quarantine_reason"]
                    ),
                    "created_at": (
                        row["created_at"].isoformat()
                        if hasattr(row["created_at"], "isoformat")
                        else row["created_at"]
                    ),
                }
                for row in matched
            ]
            return {
                "success": True,
                "data": data,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": total > page * page_size,
            }

        result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        file_info = result.scalar_one_or_none()
        if not file_info:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在: ID={file_id}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                status_code=404,
            )
        total = (
            await db.execute(
                select(func.count())
                .select_from(DataQuarantine)
                .where(DataQuarantine.catalog_file_id == file_id)
            )
        ).scalar_one()
        result = await db.execute(
            select(DataQuarantine)
            .where(DataQuarantine.catalog_file_id == file_id)
            .order_by(DataQuarantine.row_number.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = result.scalars().all()
        data = [
            {
                "id": item.id,
                "file_id": item.catalog_file_id,
                "file_name": file_info.file_name,
                "platform_code": item.platform_code,
                "data_domain": item.data_domain,
                "row_index": item.row_number,
                "error_type": item.error_type,
                "error_message": item.error_msg,
                "error_type_label": ERROR_TYPES.get(item.error_type, item.error_type),
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in rows
        ]
        return {
            "success": True,
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": total > page * page_size,
        }
    except Exception as exc:
        logger.error(f"Failed to list quarantine rows by file: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询文件隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )


@router.get("/stats")
async def get_quarantine_stats(
    platform: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        schema_mode = detect_quarantine_schema(await _get_quarantine_column_names(db))
        if schema_mode == "legacy":
            where_clause, params = build_legacy_filter_clause(platform=platform)
            result = await db.execute(
                text(
                    f"""  # nosec B608
                    select platform, data_type, quarantine_reason, count(*) as count
                    from core.data_quarantine
                    {where_clause}
                    group by platform, data_type, quarantine_reason
                    """
                ),
                params,
            )
            by_platform: Dict[str, int] = {}
            by_error_type: Dict[str, int] = {}
            by_data_domain: Dict[str, int] = {}
            total = 0
            for (
                platform_value,
                data_type,
                quarantine_reason,
                count,
            ) in result.fetchall():
                total += count
                by_platform[platform_value or "unknown"] = (
                    by_platform.get(platform_value or "unknown", 0) + count
                )
                by_error_type[quarantine_reason or "unknown"] = (
                    by_error_type.get(quarantine_reason or "unknown", 0) + count
                )
                by_data_domain[data_type or "unknown"] = (
                    by_data_domain.get(data_type or "unknown", 0) + count
                )
            return {
                "success": True,
                "data": {
                    "total": total,
                    "by_platform": by_platform,
                    "by_error_type": by_error_type,
                    "by_data_domain": by_data_domain,
                },
            }

        query = select(func.count()).select_from(DataQuarantine)
        if platform:
            query = query.where(DataQuarantine.platform_code == platform)
        total = (await db.execute(query)).scalar_one()

        by_platform = {}
        result = await db.execute(
            select(DataQuarantine.platform_code, func.count()).group_by(
                DataQuarantine.platform_code
            )
        )
        for platform_code, count in result.fetchall():
            by_platform[platform_code or "unknown"] = count

        by_error_type = {}
        result = await db.execute(
            select(DataQuarantine.error_type, func.count()).group_by(
                DataQuarantine.error_type
            )
        )
        for error_type, count in result.fetchall():
            by_error_type[error_type or "unknown"] = count

        by_data_domain = {}
        result = await db.execute(
            select(DataQuarantine.data_domain, func.count()).group_by(
                DataQuarantine.data_domain
            )
        )
        for domain, count in result.fetchall():
            by_data_domain[domain or "unknown"] = count

        return {
            "success": True,
            "data": {
                "total": total,
                "by_platform": by_platform,
                "by_error_type": by_error_type,
                "by_data_domain": by_data_domain,
            },
        }
    except Exception as exc:
        logger.error(f"Failed to get quarantine stats: {exc}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取隔离数据统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(exc),
            status_code=500,
        )
