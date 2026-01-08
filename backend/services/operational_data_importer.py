#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运营数据导入服务（v4.12.0新增）

支持运营数据（traffic、services、analytics）的导入和入库
符合运营数据主键设计规则（自增ID主键 + shop_id为核心的唯一索引）
"""

from datetime import date, datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from modules.core.db import FactTraffic, FactService, FactAnalytics
from backend.models.database import CatalogFile
from modules.core.logger import get_logger

logger = get_logger(__name__)


def upsert_traffic(
    db: Session,
    rows: List[Dict[str, Any]],
    file_record: Optional[CatalogFile] = None,
    ingest_task_id: Optional[str] = None
) -> int:
    """
    导入流量数据到fact_traffic表
    
    设计规则：
    - shop_id获取优先级：源数据 -> file_record -> account映射 -> NULL（平台级数据）
    - platform_code获取优先级：源数据 -> file_record -> "unknown"
    - 业务唯一索引：platform_code + shop_id + traffic_date + granularity + metric_type + data_domain
    
    Args:
        db: 数据库会话
        rows: 数据行列表（每行包含platform_code、shop_id、traffic_date、granularity、metric_type、metric_value等）
        file_record: 文件元数据记录（可选）
        ingest_task_id: 导入任务ID（可选）
    
    Returns:
        成功导入的行数
    """
    count = 0
    
    for idx, row in enumerate(rows):
        try:
            # 构建核心字段
            core = {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id"),
                "account": row.get("account"),
                "traffic_date": row.get("traffic_date"),
                "granularity": row.get("granularity", "daily"),
                "metric_type": row.get("metric_type"),
                "metric_value": row.get("metric_value", 0.0),
                "data_domain": row.get("data_domain", "traffic"),
                "attributes": row.get("attributes"),
                "file_id": file_record.id if file_record else None,
            }
            
            # [*] 获取platform_code（优先级：源数据 -> file_record -> "unknown"）
            if not core["platform_code"]:
                if file_record and file_record.platform_code:
                    core["platform_code"] = file_record.platform_code
                else:
                    core["platform_code"] = "unknown"
                    logger.warning(f"[UpsertTraffic] platform_code为空，使用默认值: unknown")
            
            # [*] 获取shop_id（优先级：源数据 -> file_record -> account映射 -> NULL）
            if not core["shop_id"]:
                if file_record and file_record.shop_id:
                    core["shop_id"] = file_record.shop_id
                elif core.get("account"):
                    # TODO: 通过AccountAlias映射account到shop_id
                    # 暂时允许shop_id为NULL（平台级数据）
                    core["shop_id"] = None
                    logger.info(f"[UpsertTraffic] shop_id为空，使用account: {core.get('account')}")
                else:
                    core["shop_id"] = None
                    logger.warning(f"[UpsertTraffic] shop_id为空，允许NULL（平台级数据）")
            
            # [*] 验证必填字段
            if not core["traffic_date"]:
                logger.error(f"[UpsertTraffic] 行{idx+1}: traffic_date为空，跳过")
                continue
            
            if not core["metric_type"]:
                logger.error(f"[UpsertTraffic] 行{idx+1}: metric_type为空，跳过")
                continue
            
            # 转换日期格式
            if isinstance(core["traffic_date"], str):
                try:
                    core["traffic_date"] = datetime.strptime(core["traffic_date"], "%Y-%m-%d").date()
                except ValueError:
                    logger.error(f"[UpsertTraffic] 行{idx+1}: traffic_date格式错误: {core['traffic_date']}")
                    continue
            
            # 确保metric_value为数字
            if core["metric_value"] is None:
                core["metric_value"] = 0.0
            else:
                try:
                    core["metric_value"] = float(core["metric_value"])
                except (ValueError, TypeError):
                    core["metric_value"] = 0.0
                    logger.warning(f"[UpsertTraffic] 行{idx+1}: metric_value转换失败，使用默认值0.0")
            
            # 查询现有记录（业务唯一索引）
            existing = db.query(FactTraffic).filter(
                and_(
                    FactTraffic.platform_code == core["platform_code"],
                    FactTraffic.shop_id == core["shop_id"],
                    FactTraffic.traffic_date == core["traffic_date"],
                    FactTraffic.granularity == core["granularity"],
                    FactTraffic.metric_type == core["metric_type"],
                    FactTraffic.data_domain == core["data_domain"]
                )
            ).first()
            
            if existing:
                # 更新现有记录
                for key, value in core.items():
                    if key != "id" and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
            else:
                # 创建新记录
                traffic = FactTraffic(**core)
                db.add(traffic)
            
            count += 1
            
        except Exception as e:
            logger.error(f"[UpsertTraffic] 行{idx+1}导入失败: {e}", exc_info=True)
            continue
    
    try:
        db.commit()
        logger.info(f"[UpsertTraffic] 成功导入{count}条流量数据")
    except Exception as e:
        db.rollback()
        logger.error(f"[UpsertTraffic] 提交失败: {e}", exc_info=True)
        raise
    
    return count


def upsert_service(
    db: Session,
    rows: List[Dict[str, Any]],
    file_record: Optional[CatalogFile] = None,
    ingest_task_id: Optional[str] = None
) -> int:
    """
    导入服务数据到fact_service表
    
    设计规则同upsert_traffic，但使用service_date字段
    """
    count = 0
    
    for idx, row in enumerate(rows):
        try:
            # 构建核心字段
            core = {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id"),
                "account": row.get("account"),
                "service_date": row.get("service_date") or row.get("metric_date"),  # 兼容metric_date
                "granularity": row.get("granularity", "daily"),
                "metric_type": row.get("metric_type"),
                "metric_value": row.get("metric_value", 0.0),
                "data_domain": row.get("data_domain", "services"),
                "attributes": row.get("attributes"),
                "file_id": file_record.id if file_record else None,
            }
            
            # [*] 获取platform_code
            if not core["platform_code"]:
                if file_record and file_record.platform_code:
                    core["platform_code"] = file_record.platform_code
                else:
                    core["platform_code"] = "unknown"
                    logger.warning(f"[UpsertService] platform_code为空，使用默认值: unknown")
            
            # [*] 获取shop_id
            if not core["shop_id"]:
                if file_record and file_record.shop_id:
                    core["shop_id"] = file_record.shop_id
                elif core.get("account"):
                    core["shop_id"] = None
                    logger.info(f"[UpsertService] shop_id为空，使用account: {core.get('account')}")
                else:
                    core["shop_id"] = None
                    logger.warning(f"[UpsertService] shop_id为空，允许NULL（平台级数据）")
            
            # [*] 验证必填字段
            if not core["service_date"]:
                logger.error(f"[UpsertService] 行{idx+1}: service_date为空，跳过")
                continue
            
            if not core["metric_type"]:
                logger.error(f"[UpsertService] 行{idx+1}: metric_type为空，跳过")
                continue
            
            # 转换日期格式
            if isinstance(core["service_date"], str):
                try:
                    core["service_date"] = datetime.strptime(core["service_date"], "%Y-%m-%d").date()
                except ValueError:
                    logger.error(f"[UpsertService] 行{idx+1}: service_date格式错误: {core['service_date']}")
                    continue
            
            # 确保metric_value为数字
            if core["metric_value"] is None:
                core["metric_value"] = 0.0
            else:
                try:
                    core["metric_value"] = float(core["metric_value"])
                except (ValueError, TypeError):
                    core["metric_value"] = 0.0
                    logger.warning(f"[UpsertService] 行{idx+1}: metric_value转换失败，使用默认值0.0")
            
            # 查询现有记录
            existing = db.query(FactService).filter(
                and_(
                    FactService.platform_code == core["platform_code"],
                    FactService.shop_id == core["shop_id"],
                    FactService.service_date == core["service_date"],
                    FactService.granularity == core["granularity"],
                    FactService.metric_type == core["metric_type"],
                    FactService.data_domain == core["data_domain"]
                )
            ).first()
            
            if existing:
                # 更新现有记录
                for key, value in core.items():
                    if key != "id" and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
            else:
                # 创建新记录
                service = FactService(**core)
                db.add(service)
            
            count += 1
            
        except Exception as e:
            logger.error(f"[UpsertService] 行{idx+1}导入失败: {e}", exc_info=True)
            continue
    
    try:
        db.commit()
        logger.info(f"[UpsertService] 成功导入{count}条服务数据")
    except Exception as e:
        db.rollback()
        logger.error(f"[UpsertService] 提交失败: {e}", exc_info=True)
        raise
    
    return count


def upsert_analytics(
    db: Session,
    rows: List[Dict[str, Any]],
    file_record: Optional[CatalogFile] = None,
    ingest_task_id: Optional[str] = None
) -> int:
    """
    导入分析数据到fact_analytics表
    
    设计规则同upsert_traffic，但使用analytics_date字段
    """
    count = 0
    
    for idx, row in enumerate(rows):
        try:
            # 构建核心字段
            core = {
                "platform_code": row.get("platform_code"),
                "shop_id": row.get("shop_id"),
                "account": row.get("account"),
                "analytics_date": row.get("analytics_date") or row.get("metric_date"),  # 兼容metric_date
                "granularity": row.get("granularity", "daily"),
                "metric_type": row.get("metric_type"),
                "metric_value": row.get("metric_value", 0.0),
                "data_domain": row.get("data_domain", "analytics"),
                "attributes": row.get("attributes"),
                "file_id": file_record.id if file_record else None,
            }
            
            # [*] 获取platform_code
            if not core["platform_code"]:
                if file_record and file_record.platform_code:
                    core["platform_code"] = file_record.platform_code
                else:
                    core["platform_code"] = "unknown"
                    logger.warning(f"[UpsertAnalytics] platform_code为空，使用默认值: unknown")
            
            # [*] 获取shop_id
            if not core["shop_id"]:
                if file_record and file_record.shop_id:
                    core["shop_id"] = file_record.shop_id
                elif core.get("account"):
                    core["shop_id"] = None
                    logger.info(f"[UpsertAnalytics] shop_id为空，使用account: {core.get('account')}")
                else:
                    core["shop_id"] = None
                    logger.warning(f"[UpsertAnalytics] shop_id为空，允许NULL（平台级数据）")
            
            # [*] 验证必填字段
            if not core["analytics_date"]:
                logger.error(f"[UpsertAnalytics] 行{idx+1}: analytics_date为空，跳过")
                continue
            
            if not core["metric_type"]:
                logger.error(f"[UpsertAnalytics] 行{idx+1}: metric_type为空，跳过")
                continue
            
            # 转换日期格式
            if isinstance(core["analytics_date"], str):
                try:
                    core["analytics_date"] = datetime.strptime(core["analytics_date"], "%Y-%m-%d").date()
                except ValueError:
                    logger.error(f"[UpsertAnalytics] 行{idx+1}: analytics_date格式错误: {core['analytics_date']}")
                    continue
            
            # 确保metric_value为数字
            if core["metric_value"] is None:
                core["metric_value"] = 0.0
            else:
                try:
                    core["metric_value"] = float(core["metric_value"])
                except (ValueError, TypeError):
                    core["metric_value"] = 0.0
                    logger.warning(f"[UpsertAnalytics] 行{idx+1}: metric_value转换失败，使用默认值0.0")
            
            # 查询现有记录
            existing = db.query(FactAnalytics).filter(
                and_(
                    FactAnalytics.platform_code == core["platform_code"],
                    FactAnalytics.shop_id == core["shop_id"],
                    FactAnalytics.analytics_date == core["analytics_date"],
                    FactAnalytics.granularity == core["granularity"],
                    FactAnalytics.metric_type == core["metric_type"],
                    FactAnalytics.data_domain == core["data_domain"]
                )
            ).first()
            
            if existing:
                # 更新现有记录
                for key, value in core.items():
                    if key != "id" and hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
            else:
                # 创建新记录
                analytics = FactAnalytics(**core)
                db.add(analytics)
            
            count += 1
            
        except Exception as e:
            logger.error(f"[UpsertAnalytics] 行{idx+1}导入失败: {e}", exc_info=True)
            continue
    
    try:
        db.commit()
        logger.info(f"[UpsertAnalytics] 成功导入{count}条分析数据")
    except Exception as e:
        db.rollback()
        logger.error(f"[UpsertAnalytics] 提交失败: {e}", exc_info=True)
        raise
    
    return count

