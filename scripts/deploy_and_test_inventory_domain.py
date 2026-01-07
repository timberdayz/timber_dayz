#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合部署脚本：执行数据库迁移并运行测试
时间: 2025-11-05
版本: v4.10.0
说明: 按顺序执行SQL迁移脚本，然后运行完整测试
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def execute_sql_file(db, file_path: Path):
    """执行SQL文件"""
    if not file_path.exists():
        safe_print(f"[SKIP] SQL文件不存在: {file_path}")
        return False
    
    try:
        sql_content = file_path.read_text(encoding='utf-8')
        # 分割SQL语句（按分号）
        statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]
        
        for stmt in statements:
            if stmt:
                try:
                    db.execute(text(stmt))
                except Exception as e:
                    # 忽略已存在的错误（如IF NOT EXISTS）
                    if 'already exists' not in str(e).lower() and 'duplicate' not in str(e).lower():
                        safe_print(f"[WARN] SQL执行警告: {e}")
        
        db.commit()
        safe_print(f"[OK] 执行SQL文件: {file_path.name}")
        return True
        
    except Exception as e:
        db.rollback()
        safe_print(f"[FAIL] 执行SQL文件失败 {file_path.name}: {e}")
        return False


def main():
    """主函数：执行迁移和测试"""
    safe_print("\n" + "="*70)
    safe_print("开始执行数据库迁移和测试")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # Step 1: 执行数据库迁移脚本
        safe_print("\n[Step 1] 执行数据库迁移脚本...")
        
        migration_files = [
            Path("sql/migrations/add_data_domain_to_fact_product_metrics.sql"),
            Path("sql/migrations/add_data_domain_to_unique_index.sql"),
            Path("sql/migrations/init_inventory_domain_fields.sql"),
        ]
        
        for sql_file in migration_files:
            execute_sql_file(db, sql_file)
        
        # Step 2: 运行测试
        safe_print("\n[Step 2] 运行完整测试...")
        from scripts.test_inventory_domain_complete import main as test_main
        test_result = test_main()
        
        safe_print("\n" + "="*70)
        if test_result == 0:
            safe_print("[SUCCESS] 所有迁移和测试完成！")
        else:
            safe_print("[WARN] 部分测试失败，请检查")
        safe_print("="*70)
        
        return test_result
        
    except Exception as e:
        db.rollback()
        safe_print(f"[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

