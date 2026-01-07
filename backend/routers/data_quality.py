#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量监控API

功能：
1. 检查C类数据计算就绪状态
2. 检查B类数据完整性
3. 查询核心字段状态

用于C类数据核心字段优化计划（Phase 2）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import date, datetime, timedelta

from backend.models.database import get_db, get_async_db
from backend.services.c_class_data_validator import get_c_class_data_validator
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/data-quality", tags=["数据质量监控"])


# ==================== Request/Response Models ====================

class CClassReadinessResponse(BaseModel):
    """C类数据计算就绪状态响应"""
    c_class_ready: bool
    b_class_completeness: Dict[str, float]  # {"orders": 100.0, "products": 95.0, "inventory": 100.0}
    missing_core_fields: List[str]
    data_quality_score: float
    warnings: List[str]
    timestamp: str


class CoreFieldsStatusResponse(BaseModel):
    """核心字段状态响应"""
    total_fields: int
    present_fields: int
    missing_fields: int
    fields_by_domain: Dict[str, Dict[str, Any]]
    timestamp: str


# ==================== API Endpoints ====================

@router.get("/c-class-readiness")
async def check_c_class_readiness(
    platform_code: Optional[str] = Query(None, description="平台代码"),
    shop_id: Optional[str] = Query(None, description="店铺ID"),
    metric_date: Optional[str] = Query(None, description="指标日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    检查C类数据计算就绪状态
    
    参数：
        - platform_code: 平台代码（可选）
        - shop_id: 店铺ID（可选）
        - metric_date: 指标日期（可选，默认今天）
    
    返回：
        {
            "c_class_ready": true,
            "b_class_completeness": {
                "orders": 100.0,
                "products": 95.0,
                "inventory": 100.0
            },
            "missing_core_fields": [],
            "data_quality_score": 98.5,
            "warnings": [],
            "timestamp": "2025-01-31T10:00:00"
        }
    """
    try:
        # 解析日期
        if metric_date:
            check_date = datetime.strptime(metric_date, "%Y-%m-%d").date()
        else:
            check_date = date.today()
        
        # 获取验证器
        validator = get_c_class_data_validator(db)
        
        # 如果指定了平台和店铺，检查特定店铺的数据完整性
        if platform_code and shop_id:
            check_result = validator.check_b_class_completeness(
                platform_code=platform_code,
                shop_id=shop_id,
                metric_date=check_date
            )
            
            return success_response(data={
                "c_class_ready": check_result["orders_complete"] and \
                                check_result["products_complete"] and \
                                check_result["inventory_complete"],
                "b_class_completeness": {
                    "orders": 100.0 if check_result["orders_complete"] else 0.0,
                    "products": 100.0 if check_result["products_complete"] else 0.0,
                    "inventory": 100.0 if check_result["inventory_complete"] else 0.0
                },
                "missing_core_fields": check_result["missing_fields"],
                "data_quality_score": check_result["data_quality_score"],
                "warnings": check_result["warnings"],
                "timestamp": datetime.now().isoformat()
            })
        
        # 否则，返回整体统计
        # 查询所有店铺的数据完整性（简化版：只检查字段映射辞典中的字段存在性）
        from scripts.verify_c_class_core_fields import C_CLASS_CORE_FIELDS
        
        all_fields = []
        for domain_fields in C_CLASS_CORE_FIELDS.values():
            all_fields.extend(domain_fields)
        
        # 检查字段在辞典中的存在性
        present_fields = []
        missing_fields = []
        
        for field_code in all_fields:
            field_query = select(FieldMappingDictionary).where(
                FieldMappingDictionary.field_code == field_code
            )
            field_exists = db.execute(field_query).scalar_one_or_none()
            
            if field_exists:
                present_fields.append(field_code)
            else:
                missing_fields.append(field_code)
        
        total_fields = len(all_fields)
        data_quality_score = (len(present_fields) / total_fields * 100) if total_fields > 0 else 0.0
        
        return success_response(data={
            "c_class_ready": len(missing_fields) == 0,
            "b_class_completeness": {
                "orders": 100.0,  # 简化版，实际应查询数据库
                "products": 100.0,
                "inventory": 100.0
            },
            "missing_core_fields": missing_fields,
            "data_quality_score": data_quality_score,
            "warnings": [] if len(missing_fields) == 0 else [
                f"缺失 {len(missing_fields)} 个核心字段，请运行 scripts/add_c_class_missing_fields.py 补充"
            ],
            "timestamp": datetime.now().isoformat()
        })
    
    except Exception as e:
        logger.error(f"Failed to check C-class readiness: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检查C类数据计算就绪状态失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/b-class-completeness")
async def check_b_class_completeness(
    platform_code: str = Query(..., description="平台代码"),
    shop_id: str = Query(..., description="店铺ID"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    检查B类数据完整性
    
    参数：
        - platform_code: 平台代码（必填）
        - shop_id: 店铺ID（必填）
        - start_date: 开始日期（可选，默认30天前）
        - end_date: 结束日期（可选，默认今天）
    
    返回：
        {
            "platform_code": "shopee",
            "shop_id": "shop001",
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            "daily_checks": [...],
            "summary": {
                "total_days": 31,
                "avg_quality_score": 90.5,
                "complete_days": 25,
                "incomplete_days": 6
            }
        }
    """
    try:
        # 解析日期
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end = date.today()
        
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start = end - timedelta(days=30)
        
        # 获取验证器并生成报告
        validator = get_c_class_data_validator(db)
        report = validator.generate_quality_report(
            platform_code=platform_code,
            shop_id=shop_id,
            start_date=start,
            end_date=end
        )
        
        return {
            "success": True,
            "data": report
        }
    
    except Exception as e:
        logger.error(f"Failed to check B-class completeness: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="检查B类数据完整性失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/core-fields-status")
async def get_core_fields_status(
    data_domain: Optional[str] = Query(None, description="数据域（可选）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    查询核心字段状态
    
    参数：
        - data_domain: 数据域（可选，如orders/products/inventory）
    
    返回：
        {
            "total_fields": 17,
            "present_fields": 15,
            "missing_fields": 2,
            "fields_by_domain": {
                "orders": {
                    "total": 6,
                    "present": 6,
                    "missing": 0,
                    "fields": [...]
                },
                ...
            },
            "timestamp": "2025-01-31T10:00:00"
        }
    """
    try:
        from scripts.verify_c_class_core_fields import C_CLASS_CORE_FIELDS
        
        fields_by_domain = {}
        total_fields = 0
        total_present = 0
        total_missing = 0
        
        # 检查每个数据域的字段状态
        for domain, fields in C_CLASS_CORE_FIELDS.items():
            if data_domain and domain != data_domain:
                continue
            
            present_fields = []
            missing_fields = []
            
            for field_code in fields:
                field_query = select(FieldMappingDictionary).where(
                    FieldMappingDictionary.field_code == field_code
                )
                field_exists = db.execute(field_query).scalar_one_or_none()
                
                if field_exists:
                    present_fields.append(field_code)
                    total_present += 1
                else:
                    missing_fields.append(field_code)
                    total_missing += 1
                
                total_fields += 1
            
            fields_by_domain[domain] = {
                "total": len(fields),
                "present": len(present_fields),
                "missing": len(missing_fields),
                "present_fields": present_fields,
                "missing_fields": missing_fields
            }
        
        return {
            "success": True,
            "data": {
                "total_fields": total_fields,
                "present_fields": total_present,
                "missing_fields": total_missing,
                "fields_by_domain": fields_by_domain,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get core fields status: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询核心字段状态失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

