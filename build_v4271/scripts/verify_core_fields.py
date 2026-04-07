#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证字段映射系统核心字段完整性

检查field_mapping_dictionary表中订单、产品、库存数据域的核心字段是否存在
验证字段映射模板识别准确性

用于后端优化和C类数据计算支撑计划
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
from sqlalchemy import select, text

logger = get_logger(__name__)

# 核心字段清单（根据计划定义）
CORE_FIELDS = {
    "orders": [
        "order_id",
        "order_date_local",
        "order_time_utc",
        "total_amount_rmb",
        "order_status",
        "platform_code",
        "shop_id",
    ],
    "products": [
        "platform_sku",
        "product_name",
        "metric_date",
        "sales_volume",
        "sales_amount_rmb",
        "page_views",
        "unique_visitors",
        "add_to_cart_count",
        "order_count",
        "conversion_rate",
        "rating",
        "review_count",
        "platform_code",
        "shop_id",
        "data_domain",
    ],
    "inventory": [
        "available_stock",
        "total_stock",
        "price_rmb",
    ],
}

# 字段别名映射（处理字段名差异）
FIELD_ALIASES = {
    "total_amount_rmb": ["total_amount", "total_amount_rmb"],
    "order_time_utc": ["order_time_utc", "order_time"],
    "product_name": ["product_name", "product_title"],
    "sales_amount_rmb": ["sales_amount_rmb", "sales_amount", "sales_revenue"],
    "unique_visitors": ["unique_visitors", "visitors", "uv"],
    "add_to_cart_count": ["add_to_cart_count", "add_to_cart"],
    "price_rmb": ["price_rmb", "price"],
}


def verify_core_fields(db):
    """验证核心字段是否存在"""
    logger.info("=" * 70)
    logger.info("验证字段映射系统核心字段完整性")
    logger.info("=" * 70)
    
    results = {
        "orders": {"found": [], "missing": [], "aliases": []},
        "products": {"found": [], "missing": [], "aliases": []},
        "inventory": {"found": [], "missing": [], "aliases": []},
    }
    
    # 查询所有字段
    all_fields_query = select(FieldMappingDictionary.field_code, FieldMappingDictionary.data_domain)
    all_fields_result = db.execute(all_fields_query).all()
    existing_fields = {row.field_code: row.data_domain for row in all_fields_result}
    
    # 验证每个数据域的核心字段
    for domain, fields in CORE_FIELDS.items():
        logger.info(f"\n验证 {domain} 数据域:")
        logger.info("-" * 70)
        
        for field_code in fields:
            # 检查直接匹配
            if field_code in existing_fields:
                # 检查数据域是否匹配
                field_domain = existing_fields[field_code]
                if field_domain == domain or field_domain == "general":
                    results[domain]["found"].append(field_code)
                    logger.info(f"  [OK] {field_code} - 已找到（数据域: {field_domain}）")
                else:
                    results[domain]["aliases"].append({
                        "field": field_code,
                        "found_as": field_code,
                        "domain": field_domain
                    })
                    logger.warning(f"  [WARN] {field_code} - 存在但数据域不匹配（期望: {domain}, 实际: {field_domain}）")
            else:
                # 检查别名
                aliases = FIELD_ALIASES.get(field_code, [])
                found_alias = None
                
                for alias in aliases:
                    if alias in existing_fields:
                        field_domain = existing_fields[alias]
                        if field_domain == domain or field_domain == "general":
                            found_alias = alias
                            break
                
                if found_alias:
                    results[domain]["aliases"].append({
                        "field": field_code,
                        "found_as": found_alias,
                        "domain": existing_fields[found_alias]
                    })
                    logger.info(f"  [OK] {field_code} - 通过别名找到: {found_alias}")
                else:
                    results[domain]["missing"].append(field_code)
                    logger.error(f"  [FAIL] {field_code} - 未找到")
    
    # 输出汇总
    logger.info("\n" + "=" * 70)
    logger.info("验证结果汇总")
    logger.info("=" * 70)
    
    total_found = 0
    total_missing = 0
    total_aliases = 0
    
    for domain, result in results.items():
        found_count = len(result["found"])
        missing_count = len(result["missing"])
        aliases_count = len(result["aliases"])
        
        total_found += found_count
        total_missing += missing_count
        total_aliases += aliases_count
        
        logger.info(f"\n{domain} 数据域:")
        logger.info(f"  找到: {found_count} 个")
        logger.info(f"  缺失: {missing_count} 个")
        logger.info(f"  别名: {aliases_count} 个")
        
        if result["missing"]:
            logger.error(f"  缺失字段: {', '.join(result['missing'])}")
        
        if result["aliases"]:
            logger.info(f"  别名映射:")
            for alias_info in result["aliases"]:
                logger.info(f"    {alias_info['field']} -> {alias_info['found_as']} (数据域: {alias_info['domain']})")
    
    logger.info("\n" + "=" * 70)
    logger.info(f"总计: 找到 {total_found} 个, 缺失 {total_missing} 个, 别名 {total_aliases} 个")
    logger.info("=" * 70)
    
    # 验证关键字段（P0优先级）
    logger.info("\n关键字段验证（P0优先级）:")
    logger.info("-" * 70)
    
    critical_fields = {
        "total_amount_rmb": "达成率计算核心",
        "conversion_rate": "健康度评分核心",
        "unique_visitors": "转化率计算分母",
        "order_count": "转化率计算分子",
        "sales_volume": "排名计算核心",
    }
    
    critical_status = {}
    for field_code, description in critical_fields.items():
        # 检查直接匹配或别名
        found = False
        found_as = None
        
        if field_code in existing_fields:
            found = True
            found_as = field_code
        else:
            aliases = FIELD_ALIASES.get(field_code, [])
            for alias in aliases:
                if alias in existing_fields:
                    found = True
                    found_as = alias
                    break
        
        critical_status[field_code] = {
            "found": found,
            "found_as": found_as,
            "description": description
        }
        
        if found:
            logger.info(f"  [OK] {field_code} ({description}) - 已找到: {found_as}")
        else:
            logger.error(f"  [FAIL] {field_code} ({description}) - 未找到")
    
    # 返回验证结果
    return {
        "results": results,
        "critical_status": critical_status,
        "total_found": total_found,
        "total_missing": total_missing,
        "total_aliases": total_aliases,
        "all_passed": total_missing == 0
    }


def verify_field_mapping_templates(db):
    """验证字段映射模板识别准确性"""
    logger.info("\n" + "=" * 70)
    logger.info("验证字段映射模板识别准确性")
    logger.info("=" * 70)
    
    # 查询模板数量
    template_count_query = text("""
        SELECT COUNT(*) as count
        FROM field_mapping_templates
        WHERE status = 'published'
    """)
    template_count_result = db.execute(template_count_query).scalar()
    
    logger.info(f"已发布的模板数量: {template_count_result}")
    
    # 查询各数据域的模板数量
    template_by_domain_query = text("""
        SELECT data_domain, COUNT(*) as count
        FROM field_mapping_templates
        WHERE status = 'published'
        GROUP BY data_domain
    """)
    template_by_domain_result = db.execute(template_by_domain_query).all()
    
    logger.info("\n各数据域模板数量:")
    for row in template_by_domain_result:
        logger.info(f"  {row.data_domain}: {row.count} 个")
    
    return {
        "total_templates": template_count_result,
        "templates_by_domain": {row.data_domain: row.count for row in template_by_domain_result}
    }


if __name__ == '__main__':
    db = next(get_db())
    try:
        # 验证核心字段
        field_results = verify_core_fields(db)
        
        # 验证模板
        template_results = verify_field_mapping_templates(db)
        
        # 最终结论
        logger.info("\n" + "=" * 70)
        logger.info("最终结论")
        logger.info("=" * 70)
        
        if field_results["all_passed"]:
            logger.info("[OK] 所有核心字段验证通过")
        else:
            logger.error(f"[FAIL] 有 {field_results['total_missing']} 个核心字段缺失")
            logger.error("请检查并补充缺失字段到 field_mapping_dictionary 表")
        
        logger.info(f"[INFO] 已发布模板数量: {template_results['total_templates']}")
        
    finally:
        db.close()

