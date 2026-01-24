#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Metabase Question ID 验证脚本

用于验证所有 Metabase Question ID 是否已配置
在应用启动前运行，确保所有必要的 Question ID 都已配置

使用方法:
    python scripts/verify_metabase_question_ids.py
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


def verify_metabase_question_ids():
    """验证所有Metabase Question ID是否已配置"""
    # Question ID映射（与 MetabaseQuestionService 保持一致）
    question_ids = {
        "business_overview_kpi": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_KPI", "0")),
        "business_overview_comparison": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON", "0")),
        "business_overview_shop_racing": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_SHOP_RACING", "0")),
        "business_overview_traffic_ranking": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_TRAFFIC_RANKING", "0")),
        "business_overview_inventory_backlog": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_INVENTORY_BACKLOG", "0")),
        "business_overview_operational_metrics": int(os.getenv("METABASE_QUESTION_BUSINESS_OVERVIEW_OPERATIONAL_METRICS", "0")),
        "clearance_ranking": int(os.getenv("METABASE_QUESTION_CLEARANCE_RANKING", "0")),
    }
    
    missing_ids = []
    configured_ids = []
    
    for question_key, question_id in question_ids.items():
        env_var_name = f"METABASE_QUESTION_{question_key.upper()}"
        if not question_id or question_id == 0:
            missing_ids.append((question_key, env_var_name))
        else:
            configured_ids.append((question_key, question_id, env_var_name))
    
    # 输出验证结果
    print("\n" + "="*80)
    print("Metabase Question ID 配置验证")
    print("="*80)
    
    if configured_ids:
        print(f"\n[OK] 已配置的 Question ID ({len(configured_ids)}个):")
        for question_key, question_id, env_var_name in configured_ids:
            print(f"  {question_key:40s} ID: {question_id:5d}  ({env_var_name})")
    
    if missing_ids:
        print(f"\n[WARNING] 未配置的 Question ID ({len(missing_ids)}个):")
        for question_key, env_var_name in missing_ids:
            print(f"  {question_key:40s} ({env_var_name})")
        
        print("\n配置方式:")
        print("  1. 在Metabase UI中创建Question")
        print("  2. 记录Question ID（在Question URL或详情中）")
        print("  3. 配置到.env文件:")
        for question_key, env_var_name in missing_ids:
            print(f"     {env_var_name}=<question_id>")
        
        print("\n提示:")
        print("  - 未配置的Question ID会导致相关API返回配置错误")
        print("  - 系统将正常运行，但相关功能无法使用")
        print("  - 生产环境建议配置所有Question ID")
        
        return False
    else:
        print("\n[SUCCESS] 所有Question ID已配置！")
        return True


if __name__ == "__main__":
    try:
        success = verify_metabase_question_ids()
        print("\n" + "="*80)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        print(f"\n[ERROR] 验证失败: {e}")
        sys.exit(1)
