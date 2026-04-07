#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证脚本：验证v4.14.0迁移是否成功

验证内容：
1. deduplication_fields字段是否存在
2. 唯一约束是否已更新
3. 动态列管理功能是否正常
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 所有fact_raw_data_*表
FACT_RAW_DATA_TABLES = [
    'fact_raw_data_orders_daily',
    'fact_raw_data_orders_weekly',
    'fact_raw_data_orders_monthly',
    'fact_raw_data_products_daily',
    'fact_raw_data_products_weekly',
    'fact_raw_data_products_monthly',
    'fact_raw_data_traffic_daily',
    'fact_raw_data_traffic_weekly',
    'fact_raw_data_traffic_monthly',
    'fact_raw_data_services_daily',
    'fact_raw_data_services_weekly',
    'fact_raw_data_services_monthly',
    'fact_raw_data_inventory_snapshot',
]


def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def verify_deduplication_fields():
    """验证deduplication_fields字段是否存在"""
    safe_print("=" * 70)
    safe_print("验证1: deduplication_fields字段")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'field_mapping_templates'
            AND column_name = 'deduplication_fields'
        """))
        
        row = result.fetchone()
        if row:
            safe_print(f"  [OK] deduplication_fields字段存在")
            safe_print(f"  类型: {row[1]}")
            safe_print(f"  可空: {row[2]}")
            return True
        else:
            safe_print("  [ERROR] deduplication_fields字段不存在")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        logger.error("验证失败", exc_info=True)
        return False
    finally:
        db.close()


def verify_unique_constraints():
    """验证唯一约束是否已更新"""
    safe_print("\n" + "=" * 70)
    safe_print("验证2: 唯一约束更新")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        all_passed = True
        
        for table_name in FACT_RAW_DATA_TABLES:
            # 检查新唯一索引是否存在
            new_index_name = f"uq_{table_name}_hash_v2"
            result = db.execute(text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = :table_name
                AND indexname = :index_name
            """), {"table_name": table_name, "index_name": new_index_name})
            
            row = result.fetchone()
            if row:
                safe_print(f"  [OK] {table_name}: 新唯一索引存在")
                safe_print(f"    索引名: {new_index_name}")
                # 检查索引定义是否包含COALESCE
                index_def = row[1]
                if 'COALESCE' in index_def or 'coalesce' in index_def:
                    safe_print(f"    [OK] 索引定义包含COALESCE")
                else:
                    safe_print(f"    [WARN] 索引定义可能不包含COALESCE")
            else:
                safe_print(f"  [WARN] {table_name}: 新唯一索引不存在（可能需要执行迁移脚本）")
                all_passed = False
            
            # 检查旧唯一约束是否已删除
            old_constraint_name = f"uq_{table_name}_hash"
            result = db.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = :table_name
                AND constraint_name = :constraint_name
            """), {"table_name": table_name, "constraint_name": old_constraint_name})
            
            row = result.fetchone()
            if row:
                safe_print(f"  [WARN] {table_name}: 旧唯一约束仍存在（可能需要删除）")
            else:
                safe_print(f"  [OK] {table_name}: 旧唯一约束已删除")
        
        return all_passed
        
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        logger.error("验证失败", exc_info=True)
        return False
    finally:
        db.close()


def verify_dynamic_columns():
    """验证动态列管理功能"""
    safe_print("\n" + "=" * 70)
    safe_print("验证3: 动态列管理功能")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        from backend.services.dynamic_column_manager import get_dynamic_column_manager
        
        manager = get_dynamic_column_manager(db)
        table_name = "fact_raw_data_orders_daily"
        
        # 查询现有列
        existing_columns = manager.get_existing_columns(table_name)
        safe_print(f"  [OK] 动态列管理服务正常")
        safe_print(f"  表 {table_name} 现有列数: {len(existing_columns)}")
        
        # 检查是否有动态添加的列（测试列）
        test_columns = ['测试列1', '测试列2', 'order_id']
        normalized_test_columns = [manager.normalize_column_name(col) for col in test_columns]
        found_test_columns = [col for col in normalized_test_columns if col in existing_columns]
        
        if found_test_columns:
            safe_print(f"  [OK] 发现测试列: {', '.join(found_test_columns)}")
        else:
            safe_print(f"  [INFO] 未发现测试列（可能需要重新同步数据）")
        
        return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        logger.error("验证失败", exc_info=True)
        return False
    finally:
        db.close()


def verify_table_structure():
    """验证表结构"""
    safe_print("\n" + "=" * 70)
    safe_print("验证4: 表结构")
    safe_print("=" * 70)
    
    db = SessionLocal()
    try:
        table_name = "fact_raw_data_orders_daily"
        
        # 检查必需字段
        required_columns = [
            'id', 'platform_code', 'shop_id', 'data_domain', 'granularity',
            'metric_date', 'file_id', 'raw_data', 'header_columns', 'data_hash',
            'ingest_timestamp'
        ]
        
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
        """), {"table_name": table_name})
        
        existing_columns = {row[0] for row in result}
        
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        if missing_columns:
            safe_print(f"  [ERROR] 缺少必需字段: {', '.join(missing_columns)}")
            return False
        else:
            safe_print(f"  [OK] 所有必需字段存在")
            safe_print(f"  表 {table_name} 总列数: {len(existing_columns)}")
            return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        logger.error("验证失败", exc_info=True)
        return False
    finally:
        db.close()


def main():
    """运行所有验证"""
    safe_print("=" * 70)
    safe_print("v4.14.0 迁移验证")
    safe_print("=" * 70)
    
    results = []
    
    # 验证1: deduplication_fields字段
    results.append(("deduplication_fields字段", verify_deduplication_fields()))
    
    # 验证2: 唯一约束
    results.append(("唯一约束更新", verify_unique_constraints()))
    
    # 验证3: 动态列管理
    results.append(("动态列管理功能", verify_dynamic_columns()))
    
    # 验证4: 表结构
    results.append(("表结构", verify_table_structure()))
    
    # 汇总结果
    safe_print("\n" + "=" * 70)
    safe_print("验证结果汇总")
    safe_print("=" * 70)
    
    all_passed = True
    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        safe_print(f"  {status} {name}")
        if not passed:
            all_passed = False
    
    safe_print("\n" + "=" * 70)
    if all_passed:
        safe_print("[OK] 所有验证通过！")
    else:
        safe_print("[WARN] 部分验证未通过，请检查上述结果")
    safe_print("=" * 70)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

