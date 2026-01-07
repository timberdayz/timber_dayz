#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
订单金额维度入库服务（v4.6.0）

⚠️ v4.18.2 已废弃：此功能已移除，不再被调用
原因：
- DSS架构下，数据已完整存储在 b_class.fact_raw_data_orders_* 表的 JSONB 字段中
- 货币代码已提取到 currency_code 系统字段，字段名已归一化
- 数据标准化应在 Metabase 中完成，该表属于"只写不读"的冗余数据
- 如需订单金额统计，请通过 Metabase 查询 b_class.fact_raw_data_orders_* 表

原用途（已废弃）：
- 识别多货币、多状态的销售额和退款字段
- 提取维度（metric_type, metric_subtype, currency）
- 批量转换货币
- 写入FactOrderAmount表

保留此文件仅用于兼容性，不推荐使用。
"""

from typing import List, Dict, Optional
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from modules.core.db import FactOrderAmount
from modules.core.logger import get_logger
from backend.services.pattern_matcher import PatternMatcher
from backend.services.currency_converter import CurrencyConverter

logger = get_logger(__name__)


async def ingest_order_amounts(
    db: Session,
    rows: List[Dict],
    original_columns: List[str],
    field_mappings: Dict,
    order_date: Optional[date] = None
) -> int:
    """
    入库订单金额维度数据
    
    参数：
        db: 数据库会话
        rows: 数据行列表（已映射到标准字段）
        original_columns: 原始列名列表
        field_mappings: 字段映射字典
        order_date: 订单日期（可选，默认使用今天）
    
    返回：
        插入的记录数
    
    流程：
    1. 使用PatternMatcher识别pattern-based字段
    2. 提取维度（metric_type, metric_subtype, currency）
    3. 准备转换数据
    4. 批量货币转换
    5. 批量插入FactOrderAmount表
    """
    
    if not rows or not original_columns:
        logger.info("No data to ingest for FactOrderAmount")
        return 0
    
    if order_date is None:
        order_date = date.today()
    
    # 1. 初始化服务
    matcher = PatternMatcher(db)
    converter = CurrencyConverter(db)
    
    # 2. 识别pattern-based字段
    # ⭐ v4.12.1修复：跳过已经映射的字段，避免Pattern Matcher警告
    # 只处理未映射的字段或明确标记为pattern-based的字段
    pattern_fields = {}
    mapped_standard_fields = set()
    
    # 收集已映射的标准字段（避免重复匹配）
    if field_mappings:
        for orig_col, mapping_info in field_mappings.items():
            if isinstance(mapping_info, dict):
                standard_field = mapping_info.get("standard_field")
                if standard_field and standard_field != "未映射":
                    mapped_standard_fields.add(standard_field)
    
    for orig_col in original_columns:
        # ⭐ v4.12.1修复：跳过已经映射的字段
        mapping_info = field_mappings.get(orig_col) if field_mappings else None
        if mapping_info and isinstance(mapping_info, dict):
            standard_field = mapping_info.get("standard_field")
            # 如果字段已经映射到标准字段，跳过Pattern匹配（避免警告）
            if standard_field and standard_field != "未映射":
                continue
        
        # 只对未映射的字段进行Pattern匹配
        match_result = matcher.match_field(orig_col, data_domain="orders")
        
        if match_result["matched"] and match_result.get("target_table") == "fact_order_amounts":
            pattern_fields[orig_col] = match_result
            logger.debug(f"Identified pattern field: '{orig_col}' -> {match_result['standard_field']}")
    
    if not pattern_fields:
        logger.info("No pattern-based fields found for FactOrderAmount, skipping dimension table ingestion")
        return 0
    
    logger.info(f"Found {len(pattern_fields)} pattern-based fields for dimension table ingestion")
    
    # 3. 准备数据（收集所有需要转换的金额）
    records_to_convert = []
    records_metadata = []
    
    for row_idx, row in enumerate(rows):
        # 提取order_id（优先使用标准字段，降级使用中文字段）
        order_id = (
            row.get("order_id") or 
            row.get("订单号") or 
            row.get("订单编号") or 
            f"unknown_{row_idx}"
        )
        
        for orig_col, match_result in pattern_fields.items():
            # 从原始行数据中获取值（使用原始列名）
            value = row.get(orig_col)
            
            if value is None or value == "" or value == 0:
                continue
            
            try:
                amount = float(value)
                if amount == 0:
                    continue  # 跳过0值
            except (ValueError, TypeError):
                logger.warning(f"Invalid amount value: {value} for column '{orig_col}' in row {row_idx}")
                continue
            
            # 提取维度
            dimensions = match_result.get("dimensions", {})
            target_columns = match_result.get("target_columns", {})
            
            currency = dimensions.get("currency", "CNY")
            metric_type = target_columns.get("metric_type", "unknown")
            metric_subtype = target_columns.get("metric_subtype", "unknown")
            
            # 准备转换记录
            records_to_convert.append({
                "amount": amount,
                "currency": currency,
                "date": order_date
            })
            
            # 保存元数据
            records_metadata.append({
                "order_id": order_id,
                "metric_type": metric_type,
                "metric_subtype": metric_subtype,
                "currency": currency,
                "amount_original": amount,
                "row_idx": row_idx,
                "original_column": orig_col
            })
    
    if not records_to_convert:
        logger.info("No valid amount data to convert (all values are 0 or None)")
        return 0
    
    logger.info(f"Prepared {len(records_to_convert)} amount records for conversion")
    
    # 4. 批量货币转换
    try:
        logger.info(f"Converting {len(records_to_convert)} amount records to CNY...")
        cny_amounts = await converter.batch_convert(records_to_convert, target_currency="CNY")
        logger.info(f"Currency conversion completed: {len(cny_amounts)} amounts converted")
    except Exception as e:
        logger.error(f"Batch currency conversion failed: {e}")
        # 降级：使用原币金额
        cny_amounts = [Decimal(str(rec["amount"])) for rec in records_to_convert]
        logger.warning("Using original amounts as CNY (conversion failed)")
    
    # 5. 批量插入FactOrderAmount表
    inserted = 0
    failed = 0
    
    for idx, metadata in enumerate(records_metadata):
        try:
            # 计算汇率（用于审计）
            amount_original = Decimal(str(metadata["amount_original"]))
            amount_cny = cny_amounts[idx]
            
            if amount_original != 0:
                exchange_rate = float(amount_cny / amount_original)
            else:
                exchange_rate = 1.0
            
            # 创建记录
            order_amount = FactOrderAmount(
                order_id=metadata["order_id"],
                metric_type=metadata["metric_type"],
                metric_subtype=metadata["metric_subtype"],
                currency=metadata["currency"],
                amount_original=float(amount_original),
                amount_cny=float(amount_cny),
                exchange_rate=exchange_rate,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(order_amount)
            inserted += 1
            
            if inserted % 100 == 0:
                logger.debug(f"Progress: {inserted} records inserted")
        
        except Exception as e:
            logger.error(f"Failed to insert order amount for row {metadata['row_idx']}: {e}")
            failed += 1
    
    # 提交事务
    try:
        db.commit()
        logger.info(f"Successfully inserted {inserted} records to FactOrderAmount table (failed: {failed})")
    except Exception as e:
        logger.error(f"Failed to commit FactOrderAmount records: {e}")
        db.rollback()
        raise
    
    return inserted


def extract_order_date_from_row(row: Dict) -> Optional[date]:
    """
    从行数据中提取订单日期
    
    参数：
        row: 数据行字典
    
    返回：
        订单日期或None
    """
    # 尝试从多个可能的字段中提取日期
    date_fields = [
        "order_date", "订单日期", "日期", "下单日期",
        "order_time", "订单时间", "时间"
    ]
    
    for field in date_fields:
        value = row.get(field)
        if value:
            try:
                # 如果是date或datetime对象，直接返回
                if isinstance(value, date):
                    return value
                elif isinstance(value, datetime):
                    return value.date()
                
                # 如果是字符串，尝试解析
                # TODO: 添加更智能的日期解析逻辑
                return date.today()
            except Exception as e:
                logger.debug(f"Failed to parse date from field '{field}': {e}")
                continue
    
    return None



