#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查规范文档完整性

⭐ v4.12.0新增：审查spec.md是否覆盖所有关键设计决策
"""

import sys
from pathlib import Path
import re

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def review_spec_completeness():
    """审查规范文档完整性"""
    safe_print("=" * 70)
    safe_print("审查规范文档完整性")
    safe_print("=" * 70)
    
    spec_file = project_root / "openspec" / "changes" / "establish-database-design-rules" / "specs" / "database-design" / "spec.md"
    
    if not spec_file.exists():
        safe_print("[ERROR] 规范文档不存在")
        return False
    
    with open(spec_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    missing_rules = []
    
    # 检查关键规则是否在文档中
    key_rules = {
        'shop_id获取规则': ['shop_id', 'file_record', '获取'],
        'platform_code获取规则': ['platform_code', 'file_record', '获取'],
        'AccountAlias映射规则': ['AccountAlias', 'account_alignment', '店铺别名', '账号对齐'],
        '字段映射规则': ['字段映射', 'field_mapping', '映射规则'],
        '数据验证规则': ['数据验证', 'validate', '验证规则'],
        '数据隔离规则': ['数据隔离', 'quarantine', '隔离规则'],
        '产品ID冗余字段规则': ['product_id', '冗余字段', 'BridgeProductKeys'],
        '物化视图主视图规则': ['主视图', 'main_view', '主视图和辅助视图'],
        '物化视图刷新顺序规则': ['刷新顺序', 'refresh_order', '依赖关系'],
    }
    
    safe_print("\n[1] 检查关键规则是否在文档中...")
    for rule_name, keywords in key_rules.items():
        found = False
        for keyword in keywords:
            if keyword in content:
                found = True
                break
        
        if found:
            safe_print(f"    [OK] {rule_name}")
        else:
            missing_rules.append(rule_name)
            safe_print(f"    [WARN] {rule_name} - 未找到")
    
    # 检查关键场景是否在文档中
    key_scenarios = {
        'shop_id获取场景': ['shop_id获取规则', 'shop_id', '文件元数据'],
        'platform_code获取场景': ['platform_code获取规则', 'platform_code', '文件元数据'],
        'AccountAlias映射场景': ['AccountAlias', '店铺别名', '账号对齐'],
        '字段映射场景': ['字段映射规则', '字段映射', '标准字段'],
        '数据验证场景': ['数据验证规则', '数据验证', '主键字段'],
        '数据隔离场景': ['数据隔离规则', '数据隔离', 'quarantine'],
        '产品ID关联场景': ['product_id', 'BridgeProductKeys', '自动关联'],
        '物化视图主视图场景': ['主视图', '数据域', '核心字段'],
        '物化视图刷新顺序场景': ['刷新顺序', '依赖关系', '主视图'],
    }
    
    safe_print("\n[2] 检查关键场景是否在文档中...")
    for scenario_name, keywords in key_scenarios.items():
        found = False
        for keyword in keywords:
            if keyword in content:
                found = True
                break
        
        if found:
            safe_print(f"    [OK] {scenario_name}")
        else:
            missing_rules.append(scenario_name)
            safe_print(f"    [WARN] {scenario_name} - 未找到")
    
    # 检查关键表设计规则
    key_tables = {
        'FactOrder': ['FactOrder', 'fact_orders', '订单表'],
        'FactOrderItem': ['FactOrderItem', 'fact_order_items', '订单明细表'],
        'FactProductMetric': ['FactProductMetric', 'fact_product_metrics', '商品指标表'],
        'AccountAlias': ['AccountAlias', 'account_aliases', '店铺别名表'],
        'BridgeProductKeys': ['BridgeProductKeys', 'bridge_product_keys', '产品键桥接表'],
    }
    
    safe_print("\n[3] 检查关键表设计规则是否在文档中...")
    for table_name, keywords in key_tables.items():
        found = False
        for keyword in keywords:
            if keyword in content:
                found = True
                break
        
        if found:
            safe_print(f"    [OK] {table_name}")
        else:
            missing_rules.append(f"{table_name}设计规则")
            safe_print(f"    [WARN] {table_name} - 未找到")
    
    # 显示结果
    safe_print("\n" + "=" * 70)
    safe_print("审查结果摘要")
    safe_print("=" * 70)
    
    if missing_rules:
        safe_print(f"\n发现 {len(missing_rules)} 个缺失的规则/场景:")
        for i, rule in enumerate(missing_rules, 1):
            safe_print(f"  {i}. {rule}")
        
        safe_print("\n[建议]")
        safe_print("建议补充以下规则/场景到规范文档中:")
        for rule in missing_rules:
            safe_print(f"  - {rule}")
    else:
        safe_print("\n[OK] 规范文档覆盖了所有关键设计决策")
    
    return len(missing_rules) == 0


if __name__ == "__main__":
    success = review_spec_completeness()
    sys.exit(0 if success else 1)

