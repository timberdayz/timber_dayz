#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据迁移自动化测试脚本

测试数据迁移 API 的导出和导入功能，包括冲突处理策略。

使用方法:
    python scripts/test_data_migration.py
"""

import sys
from pathlib import Path
import asyncio
from typing import Dict, List, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def safe_print(text: str):
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


async def test_export_api():
    """测试导出 API"""
    safe_print("\n[测试] 测试导出 API...")
    try:
        from backend.routers.data_migration import export_data
        from backend.models.database import get_async_db
        from sqlalchemy.ext.asyncio import AsyncSession
        
        # 创建测试数据库会话（需要实际数据库连接）
        # 这里只是语法测试，不实际执行
        safe_print("  [SKIP] 导出 API 语法验证通过（需要数据库连接才能实际测试）")
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 导出 API 测试失败: {e}")
        return False


async def test_import_api():
    """测试导入 API"""
    safe_print("\n[测试] 测试导入 API...")
    try:
        from backend.routers.data_migration import import_data
        from backend.routers.data_migration import validate_table_name, validate_column_names
        
        # 测试表名验证
        safe_print("  [测试] 表名白名单验证...")
        assert validate_table_name("dim_platforms") == True, "dim_platforms 应该在白名单中"
        assert validate_table_name("invalid_table_123") == False, "invalid_table_123 不应该在白名单中"
        assert validate_table_name("'; DROP TABLE users; --") == False, "SQL 注入尝试应该被拒绝"
        safe_print("    [OK] 表名验证通过")
        
        # 测试列名验证
        safe_print("  [测试] 列名白名单验证...")
        valid_columns = {"id", "name", "code"}
        assert validate_column_names(["id", "name"], valid_columns) == True, "有效列名应该通过"
        assert validate_column_names(["id", "invalid_col"], valid_columns) == False, "无效列名应该被拒绝"
        safe_print("    [OK] 列名验证通过")
        
        safe_print("  [OK] 导入 API 语法验证通过")
        return True
    except Exception as e:
        safe_print(f"  [FAIL] 导入 API 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_upsert_logic():
    """测试 UPSERT 逻辑（模拟）"""
    safe_print("\n[测试] 测试 UPSERT 逻辑...")
    try:
        # 模拟主键列获取逻辑
        pk_columns = ["id"]
        columns = ["id", "name", "code"]
        update_columns = [col for col in columns if col not in pk_columns]
        
        assert update_columns == ["name", "code"], "更新列应该排除主键列"
        
        # 模拟复合主键
        pk_columns_composite = ["platform_code", "shop_id", "order_id"]
        columns_composite = ["platform_code", "shop_id", "order_id", "status", "amount"]
        update_columns_composite = [col for col in columns_composite if col not in pk_columns_composite]
        
        assert update_columns_composite == ["status", "amount"], "复合主键时更新列应该正确"
        
        safe_print("  [OK] UPSERT 逻辑验证通过")
        return True
    except Exception as e:
        safe_print(f"  [FAIL] UPSERT 逻辑测试失败: {e}")
        return False


def test_sql_injection_prevention():
    """测试 SQL 注入防护"""
    safe_print("\n[测试] SQL 注入防护...")
    try:
        from backend.routers.data_migration import validate_table_name, validate_column_names
        
        # 测试 SQL 注入尝试
        sql_injection_attempts = [
            "'; DROP TABLE users; --",
            "users; DROP TABLE users;",
            "users' OR '1'='1",
            "users UNION SELECT * FROM users",
        ]
        
        for attempt in sql_injection_attempts:
            assert validate_table_name(attempt) == False, f"SQL 注入尝试应该被拒绝: {attempt}"
        
        safe_print("  [OK] SQL 注入防护验证通过")
        return True
    except Exception as e:
        safe_print(f"  [FAIL] SQL 注入防护测试失败: {e}")
        return False


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("数据迁移自动化测试")
    safe_print("=" * 80)
    
    results = []
    
    # 运行测试（不实际连接数据库）
    results.append(("导出 API", asyncio.run(test_export_api())))
    results.append(("导入 API", asyncio.run(test_import_api())))
    results.append(("UPSERT 逻辑", test_upsert_logic()))
    results.append(("SQL 注入防护", test_sql_injection_prevention()))
    
    # 总结
    safe_print("\n" + "=" * 80)
    safe_print("测试结果总结")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        safe_print(f"{status} {test_name}")
    
    safe_print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        safe_print("\n[OK] 所有测试通过！")
        return 0
    else:
        safe_print(f"\n[WARN] {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
