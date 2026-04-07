#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证数据库表结构完整性脚本

用于部署后验证所有表是否都已创建，以及 Alembic 迁移状态是否正确。
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import verify_schema_completeness, engine
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("数据库表结构完整性验证")
    safe_print("=" * 80)
    
    try:
        result = verify_schema_completeness()
        
        safe_print("\n验证结果:")
        safe_print(f"  预期表数量: {result['expected_table_count']}")
        safe_print(f"  实际表数量: {result['actual_table_count']}")
        safe_print(f"  Alembic 当前版本: {result.get('current_revision', 'N/A')}")
        safe_print(f"  Alembic 最新版本: {result.get('head_revision', 'N/A')}")
        safe_print(f"  迁移状态: {result['migration_status']}")
        
        if result['missing_tables']:
            safe_print(f"\n[ERROR] 缺失表 ({len(result['missing_tables'])} 张):")
            for table in result['missing_tables'][:20]:  # 只显示前20个
                safe_print(f"  - {table}")
            if len(result['missing_tables']) > 20:
                safe_print(f"  ... 还有 {len(result['missing_tables']) - 20} 张表缺失")
            return 1
        else:
            safe_print("\n[OK] 所有表都存在")
        
        if result['migration_status'] != 'up_to_date':
            safe_print(f"\n[WARN] 迁移状态异常: {result['migration_status']}")
            if result['migration_status'] == 'not_initialized':
                safe_print("  提示: 请运行: alembic upgrade head")
                return 1
            elif result['migration_status'] == 'outdated':
                safe_print(f"  当前版本: {result.get('current_revision', 'N/A')}")
                safe_print(f"  最新版本: {result.get('head_revision', 'N/A')}")
                safe_print("  提示: 请运行: alembic upgrade head")
                return 1
        
        safe_print("\n[OK] 数据库表结构验证通过")
        
        # 输出 JSON 格式（用于 CI/CD）
        if '--json' in sys.argv:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return 0
        
    except Exception as e:
        safe_print(f"\n[ERROR] 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
