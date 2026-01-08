#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据隔离区API（v4.6.0新增）

功能：
1. 查询隔离数据列表（分页、筛选）
2. 查看隔离数据详情（原始数据、错误原因）
3. 重新处理隔离数据（修正后重新入库）
4. 批量操作（批量重新处理、批量删除）

路由：
- GET /api/data-quarantine/list - 查询列表
- GET /api/data-quarantine/detail/{quarantine_id} - 查看详情
- POST /api/data-quarantine/reprocess - 重新处理
- DELETE /api/data-quarantine/delete - 批量删除
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import DataQuarantine, CatalogFile
from modules.core.logger import get_logger
from backend.services.c_class_data_validator import get_c_class_data_validator

logger = get_logger(__name__)

router = APIRouter(prefix="/data-quarantine", tags=["数据隔离区"])

# C类数据计算所需字段缺失错误类型
ERROR_TYPES = {
    "missing_c_class_core_field": "C类数据计算所需核心字段缺失",
    "invalid_currency_policy": "货币策略不符合要求",
    "data_domain_mismatch": "数据域不匹配",
    "validation_error": "数据验证失败",
    "data_type_error": "数据类型错误",
    "required_field_missing": "必填字段缺失",
    "unknown": "未知错误"
}


# ==================== Request/Response Models ====================

class QuarantineListRequest(BaseModel):
    """隔离数据列表查询请求"""
    file_id: Optional[int] = None
    platform: Optional[str] = None
    data_domain: Optional[str] = None
    error_type: Optional[str] = None
    page: int = 1
    page_size: int = 20


class QuarantineDetailResponse(BaseModel):
    """隔离数据详情响应"""
    id: int
    file_id: int
    file_name: str
    platform_code: str
    data_domain: str
    row_index: int
    raw_data: dict
    error_type: str
    error_message: str
    validation_errors: Optional[dict]
    created_at: datetime
    
    class Config:
        from_attributes = True


class ReprocessRequest(BaseModel):
    """重新处理请求"""
    quarantine_ids: List[int]
    corrections: Optional[dict] = None  # 可选的数据修正


class ReprocessResponse(BaseModel):
    """重新处理响应"""
    success: bool
    processed: int
    succeeded: int
    failed: int
    errors: List[dict]


# ==================== API Endpoints ====================

@router.get("/list")
async def list_quarantine_data(
    file_id: Optional[int] = Query(None, description="文件ID"),
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    error_type: Optional[str] = Query(None, description="错误类型"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),  # [*] v4.6.1修复：增加上限到200
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询隔离数据列表
    
    参数：
        - file_id: 文件ID（可选）
        - platform: 平台代码（可选）
        - data_domain: 数据域（可选）
        - error_type: 错误类型（可选）
        - page: 页码（从1开始）
        - page_size: 每页数量（1-100）
    
    返回：
        {
            "success": true,
            "data": [...],
            "total": 100,
            "page": 1,
            "page_size": 20,
            "has_more": true
        }
    """
    try:
        # 构造查询
        query = select(DataQuarantine)
        
        # 添加筛选条件
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
        
        # 统计总数
        count_query = select(func.count()).select_from(DataQuarantine)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        result = await db.execute(count_query)
        total = result.scalar_one()
        
        # 分页查询
        query = query.order_by(DataQuarantine.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        quarantine_list = result.scalars().all()
        
        # 构造响应
        data = []
        for q in quarantine_list:
            # 查询关联的文件信息
            result = await db.execute(
                select(CatalogFile).where(CatalogFile.id == q.catalog_file_id)
            ).scalar_one_or_none()
            
            data.append({
                "id": q.id,
                "file_id": q.catalog_file_id,
                "file_name": file_info.file_name if file_info else "未知文件",
                "platform_code": q.platform_code,
                "data_domain": q.data_domain,
                "row_index": q.row_number,  # 修正：使用row_number而不是row_index
                "error_type": q.error_type,
                "error_message": q.error_msg,  # 修正：使用error_msg而不是error_message
                "error_type_label": ERROR_TYPES.get(q.error_type, q.error_type),  # 错误类型标签
                "created_at": q.created_at.isoformat(),
            })
        
        return pagination_response(
            data=data,
            page=page,
            page_size=page_size,
            total=total
        )
    
    except Exception as e:
        logger.error(f"Failed to list quarantine data: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


def _extract_missing_fields(quarantine: DataQuarantine) -> List[str]:
    """
    从隔离数据中提取缺失字段信息
    
    如果错误类型是missing_c_class_core_field，从error_msg中解析缺失字段列表
    """
    missing_fields = []
    
    if quarantine.error_type == "missing_c_class_core_field":
        # 从error_msg中解析缺失字段（格式：缺失字段: orders.order_id, products.conversion_rate）
        error_msg = quarantine.error_msg or ""
        if "缺失字段:" in error_msg:
            fields_str = error_msg.split("缺失字段:")[-1].strip()
            missing_fields = [f.strip() for f in fields_str.split(",") if f.strip()]
    
    return missing_fields


@router.get("/detail/{quarantine_id}")
async def get_quarantine_detail(
    quarantine_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取隔离数据详情
    
    参数：
        - quarantine_id: 隔离数据ID
    
    返回：
        {
            "success": true,
            "data": {
                "id": 1,
                "file_id": 123,
                "file_name": "xxx.xlsx",
                "platform_code": "shopee",
                "data_domain": "orders",
                "row_index": 5,
                "raw_data": {...},
                "error_type": "validation_error",
                "error_message": "订单号为空",
                "validation_errors": {...},
                "created_at": "2025-01-31T10:00:00"
            }
        }
    """
    try:
        # 查询隔离数据
        query = select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
        result = await db.execute(query)
        quarantine = result.scalar_one_or_none()
        
        if not quarantine:
            return error_response(
                code=ErrorCode.DATA_QUARANTINED,
                message=f"隔离数据不存在：ID={quarantine_id}",
                error_type=get_error_type(ErrorCode.DATA_QUARANTINED),
                recovery_suggestion="请检查隔离数据ID是否正确，或确认该数据已被删除",
                status_code=404
            )
        
        # 查询关联文件
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == quarantine.catalog_file_id)
        )
        file_info = result.scalar_one_or_none()
        
        # 解析row_data（可能是JSON字符串）
        import json
        try:
            raw_data = json.loads(quarantine.row_data) if isinstance(quarantine.row_data, str) else quarantine.row_data
        except:
            raw_data = {}
        
        return {
            "success": True,
            "data": {
                "id": quarantine.id,
                "file_id": quarantine.catalog_file_id,
                "file_name": file_info.file_name if file_info else "未知文件",
                "file_path": file_info.file_path if file_info else None,
                "platform_code": quarantine.platform_code,
                "data_domain": quarantine.data_domain,
                "row_index": quarantine.row_number,
                "raw_data": raw_data,
                "error_type": quarantine.error_type,
                "error_message": quarantine.error_msg,
                "error_type_label": ERROR_TYPES.get(quarantine.error_type, quarantine.error_type),  # 错误类型标签
                "validation_errors": {},  # DataQuarantine表没有此字段，返回空对象
                "missing_fields": _extract_missing_fields(quarantine),  # C类数据字段缺失详情
                "created_at": quarantine.created_at.isoformat(),
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quarantine detail: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取隔离数据详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("/reprocess")
async def reprocess_quarantine_data(
    request: ReprocessRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    重新处理隔离数据
    
    参数：
        - quarantine_ids: 隔离数据ID列表
        - corrections: 可选的数据修正（如{"order_id": "123456"}）
    
    返回：
        {
            "success": true,
            "processed": 10,
            "succeeded": 8,
            "failed": 2,
            "errors": [...]
        }
    
    流程：
    1. 读取隔离数据的raw_data
    2. 应用corrections（如果有）
    3. 重新验证
    4. 重新入库或继续隔离
    """
    try:
        processed = 0
        succeeded = 0
        failed = 0
        errors = []
        
        for quarantine_id in request.quarantine_ids:
            try:
                # 查询隔离数据
                result = await db.execute(
                    select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
                ).scalar_one_or_none()
                
                if not quarantine:
                    errors.append({
                        "quarantine_id": quarantine_id,
                        "error": "隔离数据不存在"
                    })
                    failed += 1
                    continue
                
                processed += 1
                
                # 实现重新处理逻辑（v4.6.3完整实现）
                try:
                    # 1. 读取原始数据并应用修正
                    import json
                    raw_data_dict = json.loads(quarantine.row_data) if isinstance(quarantine.row_data, str) else quarantine.row_data
                    corrections = request.corrections or {}
                    corrected_data = {**raw_data_dict, **corrections}
                    
                    # 2. 如果是C类数据字段缺失错误，检查字段是否已补充
                    if quarantine.error_type == "missing_c_class_core_field":
                        # 使用C类数据验证器检查完整性
                        validator = get_c_class_data_validator(db)
                        check_result = validator.check_b_class_completeness(
                            platform_code=quarantine.platform_code or "",
                            shop_id=quarantine.shop_id or "",
                            metric_date=datetime.now().date(),  # 使用当前日期作为示例
                            data_domain=quarantine.data_domain
                        )
                        
                        if not check_result.get("orders_complete", True) or \
                           not check_result.get("products_complete", True) or \
                           not check_result.get("inventory_complete", True):
                            # 仍有字段缺失，提示用户补充
                            missing_fields = check_result.get("missing_fields", [])
                            errors.append({
                                "quarantine_id": quarantine_id,
                                "error": f"C类数据计算所需字段仍缺失: {', '.join(missing_fields)}。请先补充缺失字段后再重新处理。"
                            })
                            failed += 1
                            continue
                    
                    # 3. 重新验证数据
                    from backend.services.data_validator_v2 import (
                        validate_orders, 
                        validate_product_metrics,
                        validate_services
                    )
                    
                    # 根据数据域选择验证器
                    validation_result = None
                    if quarantine.data_domain == "orders":
                        validation_result = validate_orders([corrected_data])
                    elif quarantine.data_domain == "products":
                        validation_result = validate_product_metrics([corrected_data])
                    elif quarantine.data_domain == "inventory":
                        # v4.10.0新增：inventory域验证
                        from backend.services.enhanced_data_validator import validate_inventory
                        validation_result = validate_inventory([corrected_data])
                    elif quarantine.data_domain == "services":
                        validation_result = validate_services([corrected_data])
                    else:
                        raise ValueError(f"不支持的数据域: {quarantine.data_domain}")
                    
                    # 4. 检查验证结果
                    if validation_result["valid_count"] > 0:
                        # 5. 重新入库到目标表
                        # v4.18.1修复：修正导入和参数顺序
                        from backend.services.data_importer import (
                            upsert_orders_v2,
                            upsert_product_metrics
                        )
                        
                        # 准备文件记录（从catalog_files获取）
                        # v4.18.1修复：使用 CatalogFile.id 而不是 CatalogFile.file_id
                        file_record = None
                        if quarantine.catalog_file_id:
                            result = await db.execute(
                                select(CatalogFile).where(CatalogFile.id == quarantine.catalog_file_id)
                            ).scalar_one_or_none()
                        
                        # 根据数据域调用入库服务
                        # v4.18.1修复：修正参数顺序 (db, rows, file_record, data_domain)
                        ingest_result = None
                        if quarantine.data_domain == "orders":
                            ingest_result = upsert_orders_v2(db, [corrected_data], file_record)
                        elif quarantine.data_domain == "products":
                            ingest_result = upsert_product_metrics(db, [corrected_data], file_record)
                        elif quarantine.data_domain == "inventory":
                            # v4.10.0新增：inventory域入库
                            ingest_result = upsert_product_metrics(db, [corrected_data], file_record, data_domain='inventory')
                        elif quarantine.data_domain == "services":
                            # v4.18.1修复：使用upsert_product_metrics代替不存在的upsert_services
                            ingest_result = upsert_product_metrics(db, [corrected_data], file_record, data_domain='services')
                        
                        # 6. 更新隔离区状态
                        quarantine.is_resolved = True
                        quarantine.resolved_at = datetime.utcnow()
                        quarantine.resolution_note = f"手动修正并重新处理：{corrections}"
                        await db.commit()
                        
                        logger.info(f"成功重新处理隔离数据 {quarantine_id}")
                        succeeded += 1
                    else:
                        # 验证失败
                        errors.append({
                            "quarantine_id": quarantine_id,
                            "error": f"数据验证失败: {validation_result['error_summary']}"
                        })
                        failed += 1
                        
                except Exception as reprocess_err:
                    logger.error(f"重新处理失败 {quarantine_id}: {reprocess_err}")
                    errors.append({
                        "quarantine_id": quarantine_id,
                        "error": str(reprocess_err)
                    })
                    failed += 1
            
            except Exception as e:
                logger.error(f"Failed to reprocess quarantine {quarantine_id}: {e}")
                errors.append({
                    "quarantine_id": quarantine_id,
                    "error": str(e)
                })
                failed += 1
        
        return {
            "success": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "errors": errors
        }
    
    except Exception as e:
        logger.error(f"Batch reprocess failed: {e}")
        return error_response(
            code=ErrorCode.DATA_ISOLATION_FAILED,
            message="批量重新处理失败",
            error_type=get_error_type(ErrorCode.DATA_ISOLATION_FAILED),
            detail=str(e),
            recovery_suggestion="请检查隔离数据格式是否正确，或联系系统管理员",
            status_code=500
        )


@router.post("/delete")
async def delete_quarantine_data(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量删除隔离数据（v4.6.1新增）
    
    参数：
        - request: {quarantine_ids: [1, 2, 3]} 或 {"all": true}（一键全部清理）
    
    返回：
        {
            "success": true,
            "deleted": 10
        }
    """
    try:
        # [*] v4.6.1新增：支持一键全部清理
        if request.get("all") == True:
            # 删除所有隔离数据
            result = await db.execute(select(func.count()).select_from(DataQuarantine))
            deleted = result.scalar_one()
            await db.execute(delete(DataQuarantine))
            await db.commit()
            
            logger.info(f"Deleted all {deleted} quarantine records")
            
            return {
                "success": True,
                "deleted": deleted
            }
        
        # 批量删除指定ID
        quarantine_ids = request.get('quarantine_ids', [])
        
        if not quarantine_ids:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="quarantine_ids不能为空",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请提供至少一个隔离数据ID",
                status_code=400
            )
        
        deleted = 0
        
        for quarantine_id in quarantine_ids:
            result = await db.execute(
                select(DataQuarantine).where(DataQuarantine.id == quarantine_id)
            ).scalar_one_or_none()
            
            if quarantine:
                await db.delete(quarantine)
                deleted += 1
        
        await db.commit()
        
        logger.info(f"Deleted {deleted} quarantine records")
        
        return {
            "success": True,
            "deleted": deleted
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete quarantine data: {e}")
        await db.rollback()
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/files")
async def list_quarantine_files(
    platform: Optional[str] = Query(None, description="平台代码"),
    data_domain: Optional[str] = Query(None, description="数据域"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    按文件分组查询隔离数据（v4.6.1新增）
    
    返回：
        {
            "success": true,
            "data": [
                {
                    "file_id": 123,
                    "file_name": "xxx.xlsx",
                    "platform_code": "shopee",
                    "data_domain": "orders",
                    "error_count": 10,
                    "error_types": {"required": 5, "data_type": 5},
                    "created_at": "2025-11-01T10:00:00"
                },
                ...
            ]
        }
    """
    try:
        # 查询按文件分组的隔离数据
        query = select(
            DataQuarantine.catalog_file_id,
            func.count().label('error_count'),
            func.min(DataQuarantine.created_at).label('first_error_time')
        ).group_by(DataQuarantine.catalog_file_id)
        
        # 添加筛选条件
        conditions = []
        if platform:
            conditions.append(DataQuarantine.platform_code == platform)
        if data_domain:
            conditions.append(DataQuarantine.data_domain == data_domain)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 执行查询
        result = await db.execute(query)
        file_groups = result.all()
        
        # 构造响应数据
        data = []
        for file_id, error_count, first_error_time in file_groups:
            # 查询文件信息
            result = await db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            ).scalar_one_or_none()
            
            if not file_info:
                continue
            
            # 查询该文件的错误类型统计
            error_types_query = select(
                DataQuarantine.error_type,
                func.count().label('count')
            ).where(DataQuarantine.catalog_file_id == file_id).group_by(DataQuarantine.error_type)
            
            error_types = {}
            result = await db.execute(error_types_query)
            for error_type, count in result.all():
                error_types[error_type or "unknown"] = count
            
            # 查询该文件的第一个隔离记录（获取platform和domain）
            result = await db.execute(
                select(DataQuarantine).where(DataQuarantine.catalog_file_id == file_id).limit(1)
            ).scalar_one_or_none()
            
            data.append({
                "file_id": file_id,
                "file_name": file_info.file_name,
                "platform_code": first_record.platform_code if first_record else None,
                "data_domain": first_record.data_domain if first_record else None,
                "error_count": error_count,
                "error_types": error_types,
                "created_at": first_error_time.isoformat() if first_error_time else None
            })
        
        # 按错误数量排序（降序）
        data.sort(key=lambda x: x["error_count"], reverse=True)
        
        return {
            "success": True,
            "data": data,
            "total": len(data)
        }
    
    except Exception as e:
        logger.error(f"Failed to list quarantine files: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询隔离文件列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/files/{file_id}/rows")
async def list_quarantine_rows_by_file(
    file_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询指定文件的隔离数据行（v4.6.1新增）
    
    参数：
        - file_id: 文件ID
        - page: 页码
        - page_size: 每页数量
    
    返回：
        {
            "success": true,
            "data": [...],
            "total": 10,
            "page": 1,
            "page_size": 20
        }
    """
    try:
        # 查询文件信息
        result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        file_info = result.scalar_one_or_none()
        
        if not file_info:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"文件不存在：ID={file_id}",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查文件ID是否正确，或确认该文件已注册",
                status_code=404
            )
        
        # 查询该文件的隔离数据
        query = select(DataQuarantine).where(DataQuarantine.catalog_file_id == file_id)
        
        # 统计总数
        count_query = select(func.count()).select_from(DataQuarantine).where(
            DataQuarantine.catalog_file_id == file_id
        )
        result = await db.execute(count_query)
        total = result.scalar_one()
        
        # 分页查询
        query = query.order_by(DataQuarantine.row_number.asc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        result = await db.execute(query)
        quarantine_list = result.scalars().all()
        
        # 构造响应
        data = []
        for q in quarantine_list:
            data.append({
                "id": q.id,
                "file_id": q.catalog_file_id,
                "file_name": file_info.file_name,
                "platform_code": q.platform_code,
                "data_domain": q.data_domain,
                "row_index": q.row_number,
                "error_type": q.error_type,
                "error_message": q.error_msg,
                "error_type_label": ERROR_TYPES.get(q.error_type, q.error_type),  # 错误类型标签
                "created_at": q.created_at.isoformat(),
            })
        
        return {
            "success": True,
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": total > page * page_size
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list quarantine rows by file: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询文件隔离数据失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/stats")
async def get_quarantine_stats(
    platform: Optional[str] = Query(None, description="平台代码"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取隔离数据统计
    
    返回：
        {
            "total": 100,
            "by_platform": {...},
            "by_error_type": {...},
            "by_data_domain": {...}
        }
    """
    try:
        # 总数
        query = select(func.count()).select_from(DataQuarantine)
        if platform:
            query = query.where(DataQuarantine.platform_code == platform)
        result = await db.execute(query)
        total = result.scalar_one()
        
        # 按平台统计
        by_platform = {}
        platform_query = select(
            DataQuarantine.platform_code,
            func.count().label('count')
        ).group_by(DataQuarantine.platform_code)
        
        result = await db.execute(platform_query)
        platform_stats = result.all()
        for platform_code, count in platform_stats:
            by_platform[platform_code] = count
        
        # 按错误类型统计
        by_error_type = {}
        error_query = select(
            DataQuarantine.error_type,
            func.count().label('count')
        ).group_by(DataQuarantine.error_type)
        
        result = await db.execute(error_query)
        error_stats = result.all()
        for error_type, count in error_stats:
            by_error_type[error_type or "unknown"] = count
        
        # 按数据域统计
        by_data_domain = {}
        domain_query = select(
            DataQuarantine.data_domain,
            func.count().label('count')
        ).group_by(DataQuarantine.data_domain)
        
        result = await db.execute(domain_query)
        domain_stats = result.all()
        for data_domain, count in domain_stats:
            by_data_domain[data_domain or "unknown"] = count
        
        return {
            "success": True,
            "data": {
                "total": total,
                "by_platform": by_platform,
                "by_error_type": by_error_type,
                "by_data_domain": by_data_domain
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get quarantine stats: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取隔离数据统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


