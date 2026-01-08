#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据丢失分析服务（v4.13.0新增）

功能：
1. 分析数据丢失的共同特征
2. 提供数据丢失统计信息
3. 实现数据丢失预警机制
"""

from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession  # [*] v4.18.2新增：异步支持
from sqlalchemy import func, select, and_, or_
from datetime import datetime, timedelta
from collections import Counter
import asyncio  # [*] v4.18.2新增：用于run_in_executor

from modules.core.db import (
    CatalogFile,
    StagingOrders,
    StagingProductMetrics,
    StagingInventory,
    FactOrder,
    FactOrderItem,
    FactProductMetric,
    DataQuarantine
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def analyze_data_loss(
    db: AsyncSession,
    file_id: Optional[int] = None,
    task_id: Optional[str] = None,
    data_domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    [*] v4.18.2更新：完全过渡到异步架构，只接受AsyncSession
    """
    """
    分析数据丢失情况
    
    Args:
        db: 数据库会话
        file_id: 文件ID（可选）
        task_id: 任务ID（可选）
        data_domain: 数据域（可选）
    
    Returns:
        数据丢失分析结果
    """
    try:
        logger.info(f"[DataLossAnalyzer] 开始分析数据丢失: file_id={file_id}, task_id={task_id}, data_domain={data_domain}")
        
        # Step 1: 统计各层数据数量
        stats = {
            "raw_count": 0,
            "staging_count": 0,
            "fact_count": 0,
            "quarantine_count": 0,
            "loss_rate": 0.0,
            "loss_details": []
        }
        
        # Step 2: 根据数据域统计
        if data_domain == "orders":
            # Raw层：从staging表统计（staging表是raw数据的暂存）
            if file_id:
                result = await db.execute(
                    select(func.count(StagingOrders.id)).where(StagingOrders.file_id == file_id)
                )
                stats["raw_count"] = result.scalar() or 0
            elif task_id:
                result = await db.execute(
                    select(func.count(StagingOrders.id)).where(StagingOrders.ingest_task_id == task_id)
                )
                stats["raw_count"] = result.scalar() or 0
            else:
                result = await db.execute(select(func.count(StagingOrders.id)))
                stats["raw_count"] = result.scalar() or 0
            
            # Staging层：同上（staging表就是staging层）
            stats["staging_count"] = stats["raw_count"]
            
            # Fact层：从fact_order表统计
            # [*] 修复：FactOrder使用复合主键，没有id字段，使用func.count(1)或主键字段之一
            if file_id:
                result = await db.execute(
                    select(func.count(FactOrder.platform_code)).where(FactOrder.file_id == file_id)
                )
                stats["fact_count"] = result.scalar() or 0
            else:
                result = await db.execute(select(func.count(FactOrder.platform_code)))
                stats["fact_count"] = result.scalar() or 0
            
            # 隔离区：从data_quarantine表统计
            if file_id:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(
                        and_(
                            DataQuarantine.catalog_file_id == file_id,
                            DataQuarantine.data_domain == "orders"
                        )
                    )
                )
                stats["quarantine_count"] = result.scalar() or 0
            else:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(DataQuarantine.data_domain == "orders")
                )
                stats["quarantine_count"] = result.scalar() or 0
        
        elif data_domain in ["products", "traffic", "analytics"]:
            # Raw层：从staging表统计
            if file_id:
                result = await db.execute(
                    select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.file_id == file_id)
                )
                stats["raw_count"] = result.scalar() or 0
            elif task_id:
                result = await db.execute(
                    select(func.count(StagingProductMetrics.id)).where(StagingProductMetrics.ingest_task_id == task_id)
                )
                stats["raw_count"] = result.scalar() or 0
            else:
                result = await db.execute(select(func.count(StagingProductMetrics.id)))
                stats["raw_count"] = result.scalar() or 0
            
            stats["staging_count"] = stats["raw_count"]
            
            # Fact层：从fact_product_metric表统计
            # [*] 修复：FactProductMetric使用复合主键，没有id字段，使用func.count(1)或主键字段之一
            # [*] 修复：FactProductMetric使用source_catalog_id字段，不是file_id
            if file_id:
                result = await db.execute(
                    select(func.count(FactProductMetric.platform_code)).where(
                        FactProductMetric.source_catalog_id == file_id
                    )
                )
                stats["fact_count"] = result.scalar() or 0
            else:
                result = await db.execute(select(func.count(FactProductMetric.platform_code)))
                stats["fact_count"] = result.scalar() or 0
            
            # 隔离区
            if file_id:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(
                        and_(
                            DataQuarantine.catalog_file_id == file_id,
                            DataQuarantine.data_domain == data_domain
                        )
                    )
                )
                stats["quarantine_count"] = result.scalar() or 0
            else:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(DataQuarantine.data_domain == data_domain)
                )
                stats["quarantine_count"] = result.scalar() or 0
        
        elif data_domain == "inventory":
            # Raw层：从staging_inventory表统计
            if file_id:
                result = await db.execute(
                    select(func.count(StagingInventory.id)).where(StagingInventory.file_id == file_id)
                )
                stats["raw_count"] = result.scalar() or 0
            elif task_id:
                result = await db.execute(
                    select(func.count(StagingInventory.id)).where(StagingInventory.ingest_task_id == task_id)
                )
                stats["raw_count"] = result.scalar() or 0
            else:
                result = await db.execute(select(func.count(StagingInventory.id)))
                stats["raw_count"] = result.scalar() or 0
            
            stats["staging_count"] = stats["raw_count"]
            
            # Fact层：从fact_product_metric表统计（inventory数据存储在fact_product_metric表中）
            # [*] 修复：FactProductMetric使用复合主键，没有id字段，使用func.count(1)或主键字段之一
            # [*] 修复：FactProductMetric使用source_catalog_id字段，不是file_id
            if file_id:
                result = await db.execute(
                    select(func.count(FactProductMetric.platform_code)).where(
                        and_(
                            FactProductMetric.source_catalog_id == file_id,
                            FactProductMetric.data_domain == "inventory"
                        )
                    )
                )
                stats["fact_count"] = result.scalar() or 0
            else:
                result = await db.execute(
                    select(func.count(FactProductMetric.platform_code)).where(
                        FactProductMetric.data_domain == "inventory"
                    )
                )
                stats["fact_count"] = result.scalar() or 0
            
            # 隔离区
            if file_id:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(
                        and_(
                            DataQuarantine.catalog_file_id == file_id,
                            DataQuarantine.data_domain == "inventory"
                        )
                    )
                )
                stats["quarantine_count"] = result.scalar() or 0
            else:
                result = await db.execute(
                    select(func.count(DataQuarantine.id)).where(DataQuarantine.data_domain == "inventory")
                )
                stats["quarantine_count"] = result.scalar() or 0
        
        # Step 3: 计算丢失率
        if stats["raw_count"] > 0:
            lost_count = stats["raw_count"] - stats["fact_count"] - stats["quarantine_count"]
            stats["loss_rate"] = (lost_count / stats["raw_count"]) * 100
            stats["lost_count"] = lost_count
        else:
            stats["loss_rate"] = 0.0
            stats["lost_count"] = 0
        
        # Step 4: 分析丢失数据的共同特征
        if stats["quarantine_count"] > 0:
            # 查询隔离区的错误类型统计
            conditions = []
            if file_id:
                conditions.append(DataQuarantine.catalog_file_id == file_id)
            if data_domain:
                conditions.append(DataQuarantine.data_domain == data_domain)
            
            stmt = select(
                DataQuarantine.error_type,
                func.count(DataQuarantine.id).label("count")
            )
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.group_by(DataQuarantine.error_type)
            result = await db.execute(stmt)
            error_types = result.all()
            
            stats["error_type_distribution"] = {
                error_type: count for error_type, count in error_types
            }
            
            # 查询最常见的错误消息
            conditions = []
            if file_id:
                conditions.append(DataQuarantine.catalog_file_id == file_id)
            if data_domain:
                conditions.append(DataQuarantine.data_domain == data_domain)
            
            stmt = select(
                DataQuarantine.error_msg,
                func.count(DataQuarantine.id).label("count")
            )
            if conditions:
                stmt = stmt.where(and_(*conditions))
            stmt = stmt.group_by(DataQuarantine.error_msg).order_by(
                func.count(DataQuarantine.id).desc()
            ).limit(10)
            result = await db.execute(stmt)
            error_messages = result.all()
            
            stats["common_errors"] = [
                {"error_msg": msg, "count": count} for msg, count in error_messages
            ]
        
        # Step 5: 分析丢失位置
        loss_details = []
        
        # Raw -> Staging 丢失
        if stats["raw_count"] > stats["staging_count"]:
            loss_details.append({
                "stage": "Raw -> Staging",
                "lost_count": stats["raw_count"] - stats["staging_count"],
                "loss_rate": ((stats["raw_count"] - stats["staging_count"]) / stats["raw_count"] * 100) if stats["raw_count"] > 0 else 0
            })
        
        # Staging -> Fact 丢失
        if stats["staging_count"] > stats["fact_count"]:
            loss_details.append({
                "stage": "Staging -> Fact",
                "lost_count": stats["staging_count"] - stats["fact_count"],
                "loss_rate": ((stats["staging_count"] - stats["fact_count"]) / stats["staging_count"] * 100) if stats["staging_count"] > 0 else 0
            })
        
        stats["loss_details"] = loss_details
        
        logger.info(f"[DataLossAnalyzer] 分析完成: 丢失率={stats['loss_rate']:.2f}%, 丢失数量={stats.get('lost_count', 0)}")
        
        return {
            "success": True,
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"[DataLossAnalyzer] 分析数据丢失失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def check_data_loss_threshold(
    db: AsyncSession,
    file_id: Optional[int] = None,
    task_id: Optional[str] = None,
    data_domain: Optional[str] = None,
    threshold: float = 5.0
) -> Dict[str, Any]:
    """
    [*] v4.18.2更新：完全过渡到异步架构，只接受AsyncSession
    """
    """
    检查数据丢失率是否超过阈值
    
    Args:
        db: 数据库会话
        file_id: 文件ID（可选）
        task_id: 任务ID（可选）
        data_domain: 数据域（可选）
        threshold: 丢失率阈值（默认5%）
    
    Returns:
        预警信息
    """
    try:
        analysis_result = analyze_data_loss(db, file_id, task_id, data_domain)
        
        if not analysis_result.get("success"):
            return {
                "success": False,
                "error": analysis_result.get("error"),
                "timestamp": datetime.now().isoformat()
            }
        
        stats = analysis_result.get("stats", {})
        loss_rate = stats.get("loss_rate", 0.0)
        
        if loss_rate > threshold:
            return {
                "success": True,
                "alert": True,
                "loss_rate": loss_rate,
                "threshold": threshold,
                "message": f"数据丢失率 {loss_rate:.2f}% 超过阈值 {threshold}%",
                "stats": stats,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": True,
                "alert": False,
                "loss_rate": loss_rate,
                "threshold": threshold,
                "message": f"数据丢失率 {loss_rate:.2f}% 在正常范围内",
                "stats": stats,
                "timestamp": datetime.now().isoformat()
            }
    
    except Exception as e:
        logger.error(f"[DataLossAnalyzer] 检查数据丢失阈值失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# ==================== 异步包装函数（v4.18.2新增）====================

async def async_analyze_data_loss(
    db: AsyncSession,
    file_id: Optional[int] = None,
    task_id: Optional[str] = None,
    data_domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    异步分析数据丢失（[*] v4.18.2更新：直接调用异步函数）
    
    [*] v4.18.2更新：analyze_data_loss已改为异步函数，直接调用
    """
    return await analyze_data_loss(db, file_id, task_id, data_domain)


async def async_check_data_loss_threshold(
    db: AsyncSession,
    file_id: Optional[int] = None,
    task_id: Optional[str] = None,
    data_domain: Optional[str] = None,
    threshold: float = 5.0
) -> Dict[str, Any]:
    """
    异步检查数据丢失阈值（[*] v4.18.2更新：直接调用异步函数）
    
    [*] v4.18.2更新：check_data_loss_threshold已改为异步函数，直接调用
    """
    return await check_data_loss_threshold(db, file_id, task_id, data_domain, threshold)

