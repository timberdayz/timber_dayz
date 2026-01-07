#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证C类数据计算核心字段完整性

检查field_mapping_dictionary表中C类数据计算所需的17个核心字段是否存在
验证字段的数据域匹配性和字段映射模板覆盖率
生成验证报告（JSON格式，便于CI/CD集成）

用于C类数据核心字段优化计划（Phase 1）
"""

import sys
import json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from modules.core.db import FieldMappingDictionary, FieldMappingTemplate
from modules.core.logger import get_logger
from sqlalchemy import select, text, func

logger = get_logger(__name__)

# C类数据核心字段定义（17个字段）
C_CLASS_CORE_FIELDS = {
    "orders": [
        "order_id",           # 订单号（统计订单数）
        "order_date_local",   # 订单日期（时间筛选）
        "total_amount_rmb",   # 订单总金额CNY（销售额计算）
        "order_status",      # 订单状态（筛选有效订单）
        "platform_code",     # 平台代码（维度聚合）
        "shop_id",           # 店铺ID（维度聚合）
    ],
    "products": [
        "unique_visitors",    # 转化率计算分母（25分）
        "order_count",        # 转化率计算分子（25分）
        "rating",             # 客户满意度（20分）
        "metric_date",        # 时间维度聚合
        "data_domain",        # 区分products/inventory域
        "sales_volume",        # 销量排名
        "sales_amount_rmb",   # 销售额排名
        "conversion_rate",    # 转化排名/预警
    ],
    "inventory": [
        "available_stock",    # 库存周转率计算（25分）/库存预警
        "sales_volume_30d",   # 库存周转率计算（25分）
    ],
}

# 字段别名映射（处理字段名差异）
FIELD_ALIASES = {
    "total_amount_rmb": ["total_amount", "total_amount_rmb"],
    "order_date_local": ["order_date_local", "order_date"],
    "sales_amount_rmb": ["sales_amount_rmb", "sales_amount", "sales_revenue"],
    "unique_visitors": ["unique_visitors", "visitors", "uv"],
    "order_count": ["order_count", "orders_count"],
    "sales_volume_30d": ["sales_volume_30d", "sales_volume_30days"],
    "available_stock": ["available_stock", "stock", "inventory"],
    "conversion_rate": ["conversion_rate", "conversion"],
}


def verify_c_class_core_fields(db):
    """验证C类数据计算核心字段是否存在"""
    logger.info("=" * 70)
    logger.info("验证C类数据计算核心字段完整性（17个核心字段）")
    logger.info("=" * 70)
    
    results = {
        "orders": {"found": [], "missing": [], "aliases": [], "domain_mismatch": []},
        "products": {"found": [], "missing": [], "aliases": [], "domain_mismatch": []},
        "inventory": {"found": [], "missing": [], "aliases": [], "domain_mismatch": []},
    }
    
    # 查询所有字段
    all_fields_query = select(
        FieldMappingDictionary.field_code,
        FieldMappingDictionary.data_domain,
        FieldMappingDictionary.cn_name,
        FieldMappingDictionary.is_required
    )
    all_fields_result = db.execute(all_fields_query).all()
    existing_fields = {
        row.field_code: {
            "data_domain": row.data_domain,
            "cn_name": row.cn_name,
            "is_required": row.is_required
        }
        for row in all_fields_result
    }
    
    # 验证每个数据域的核心字段
    for domain, fields in C_CLASS_CORE_FIELDS.items():
        logger.info(f"\n验证 {domain} 数据域:")
        logger.info("-" * 70)
        
        for field_code in fields:
            # 检查直接匹配
            if field_code in existing_fields:
                field_info = existing_fields[field_code]
                field_domain = field_info["data_domain"]
                
                # 检查数据域是否匹配
                if field_domain == domain or field_domain == "general":
                    results[domain]["found"].append({
                        "field_code": field_code,
                        "cn_name": field_info["cn_name"],
                        "data_domain": field_domain,
                        "is_required": field_info["is_required"]
                    })
                    logger.info(f"  [OK] {field_code} ({field_info['cn_name']}) - 已找到（数据域: {field_domain}）")
                else:
                    results[domain]["domain_mismatch"].append({
                        "field_code": field_code,
                        "expected_domain": domain,
                        "actual_domain": field_domain,
                        "cn_name": field_info["cn_name"]
                    })
                    logger.warning(
                        f"  [WARN] {field_code} ({field_info['cn_name']}) - "
                        f"数据域不匹配（期望: {domain}, 实际: {field_domain}）"
                    )
            else:
                # 检查别名
                aliases = FIELD_ALIASES.get(field_code, [])
                found_alias = None
                found_alias_info = None
                
                for alias in aliases:
                    if alias in existing_fields:
                        field_info = existing_fields[alias]
                        field_domain = field_info["data_domain"]
                        if field_domain == domain or field_domain == "general":
                            found_alias = alias
                            found_alias_info = field_info
                            break
                
                if found_alias:
                    results[domain]["aliases"].append({
                        "field_code": field_code,
                        "found_as": found_alias,
                        "cn_name": found_alias_info["cn_name"],
                        "data_domain": found_alias_info["data_domain"]
                    })
                    logger.info(
                        f"  [OK] {field_code} - 通过别名找到: {found_alias} "
                        f"({found_alias_info['cn_name']})"
                    )
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
    total_domain_mismatch = 0
    
    for domain, result in results.items():
        found_count = len(result["found"])
        missing_count = len(result["missing"])
        aliases_count = len(result["aliases"])
        domain_mismatch_count = len(result["domain_mismatch"])
        
        total_found += found_count
        total_missing += missing_count
        total_aliases += aliases_count
        total_domain_mismatch += domain_mismatch_count
        
        logger.info(f"\n{domain} 数据域:")
        logger.info(f"  找到: {found_count} 个")
        logger.info(f"  缺失: {missing_count} 个")
        logger.info(f"  别名: {aliases_count} 个")
        logger.info(f"  数据域不匹配: {domain_mismatch_count} 个")
        
        if result["missing"]:
            logger.error(f"  缺失字段: {', '.join(result['missing'])}")
        
        if result["aliases"]:
            logger.info(f"  别名映射:")
            for alias_info in result["aliases"]:
                logger.info(
                    f"    {alias_info['field_code']} -> {alias_info['found_as']} "
                    f"({alias_info['cn_name']}, 数据域: {alias_info['data_domain']})"
                )
        
        if result["domain_mismatch"]:
            logger.warning(f"  数据域不匹配:")
            for mismatch_info in result["domain_mismatch"]:
                logger.warning(
                    f"    {mismatch_info['field_code']} ({mismatch_info['cn_name']}) - "
                    f"期望: {mismatch_info['expected_domain']}, 实际: {mismatch_info['actual_domain']}"
                )
    
    logger.info("\n" + "=" * 70)
    logger.info(
        f"总计: 找到 {total_found} 个, 缺失 {total_missing} 个, "
        f"别名 {total_aliases} 个, 数据域不匹配 {total_domain_mismatch} 个"
    )
    logger.info("=" * 70)
    
    # 返回验证结果
    return {
        "results": results,
        "total_found": total_found,
        "total_missing": total_missing,
        "total_aliases": total_aliases,
        "total_domain_mismatch": total_domain_mismatch,
        "all_passed": total_missing == 0 and total_domain_mismatch == 0,
        "timestamp": datetime.now().isoformat()
    }


def verify_template_coverage(db):
    """验证字段映射模板覆盖率"""
    logger.info("\n" + "=" * 70)
    logger.info("验证字段映射模板覆盖率")
    logger.info("=" * 70)
    
    # 查询已发布的模板
    template_query = select(
        FieldMappingTemplate.platform,
        FieldMappingTemplate.data_domain,
        FieldMappingTemplate.status
    ).where(FieldMappingTemplate.status == 'published')
    
    templates = db.execute(template_query).all()
    
    # 统计各数据域的模板数量
    template_stats = {}
    for template in templates:
        domain = template.data_domain
        platform = template.platform or "unknown"
        
        if domain not in template_stats:
            template_stats[domain] = {}
        if platform not in template_stats[domain]:
            template_stats[domain][platform] = 0
        
        template_stats[domain][platform] += 1
    
    logger.info("\n各数据域模板统计:")
    for domain, platforms in template_stats.items():
        logger.info(f"  {domain}:")
        total = sum(platforms.values())
        logger.info(f"    总计: {total} 个模板")
        for platform, count in platforms.items():
            logger.info(f"      {platform}: {count} 个")
    
    # 检查C类数据核心字段的模板覆盖率
    core_domains = list(C_CLASS_CORE_FIELDS.keys())
    coverage_info = {}
    
    for domain in core_domains:
        domain_templates = [
            t for t in templates
            if t.data_domain == domain or t.data_domain == "general"
        ]
        coverage_info[domain] = {
            "template_count": len(domain_templates),
            "has_template": len(domain_templates) > 0
        }
        logger.info(
            f"\n{domain} 数据域模板覆盖率: "
            f"{len(domain_templates)} 个模板"
        )
    
    return {
        "template_stats": {
            domain: {
                "total": sum(platforms.values()),
                "platforms": platforms
            }
            for domain, platforms in template_stats.items()
        },
        "coverage_info": coverage_info,
        "timestamp": datetime.now().isoformat()
    }


def generate_json_report(verification_result, template_result):
    """生成JSON格式的验证报告"""
    report = {
        "verification": {
            "summary": {
                "total_found": verification_result["total_found"],
                "total_missing": verification_result["total_missing"],
                "total_aliases": verification_result["total_aliases"],
                "total_domain_mismatch": verification_result["total_domain_mismatch"],
                "all_passed": verification_result["all_passed"]
            },
            "details": verification_result["results"],
            "timestamp": verification_result["timestamp"]
        },
        "template_coverage": template_result,
        "recommendations": []
    }
    
    # 生成建议
    if verification_result["total_missing"] > 0:
        report["recommendations"].append({
            "type": "missing_fields",
            "priority": "P0",
            "action": "运行 scripts/add_c_class_missing_fields.py 补充缺失字段"
        })
    
    if verification_result["total_domain_mismatch"] > 0:
        report["recommendations"].append({
            "type": "domain_mismatch",
            "priority": "P1",
            "action": "检查并修正字段的数据域配置"
        })
    
    return report


if __name__ == '__main__':
    db = next(get_db())
    try:
        # 验证核心字段
        field_results = verify_c_class_core_fields(db)
        
        # 验证模板覆盖率
        template_results = verify_template_coverage(db)
        
        # 生成JSON报告
        json_report = generate_json_report(field_results, template_results)
        
        # 保存JSON报告
        report_file = Path(__file__).parent.parent / "temp" / "outputs" / f"c_class_core_fields_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n验证报告已保存到: {report_file}")
        
        # 最终结论
        logger.info("\n" + "=" * 70)
        logger.info("最终结论")
        logger.info("=" * 70)
        
        if field_results["all_passed"]:
            logger.info("[OK] 所有C类数据核心字段验证通过")
        else:
            logger.error(
                f"[FAIL] 有 {field_results['total_missing']} 个核心字段缺失, "
                f"{field_results['total_domain_mismatch']} 个字段数据域不匹配"
            )
            logger.error("请运行 scripts/add_c_class_missing_fields.py 补充缺失字段")
        
        # 返回退出码（用于CI/CD）
        exit_code = 0 if field_results["all_passed"] else 1
        sys.exit(exit_code)
        
    finally:
        db.close()

