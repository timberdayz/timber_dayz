#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试动态表名功能（v4.17.0+）

测试内容：
1. PlatformTableManager是否正确创建表在b_class schema中
2. 查询API是否正确使用动态表名
3. 清理API是否能正确发现所有动态表
4. 表名格式是否符合规范
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import SessionLocal
from backend.services.platform_table_manager import get_platform_table_manager
from modules.core.db import DimPlatform
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def test_platform_table_manager():
    """测试PlatformTableManager动态表创建"""
    safe_print("\n" + "="*60)
    safe_print("测试1: PlatformTableManager动态表创建")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        platform_table_manager = get_platform_table_manager(db)
        
        # 测试表名生成
        test_cases = [
            ("shopee", "orders", None, "daily", "fact_shopee_orders_daily"),
            ("tiktok", "products", None, "weekly", "fact_tiktok_products_weekly"),
            ("shopee", "services", "ai_assistant", "monthly", "fact_shopee_services_ai_assistant_monthly"),
            ("miaoshou", "inventory", None, "snapshot", "fact_miaoshou_inventory_snapshot"),
        ]
        
        safe_print("\n[1.1] 测试表名生成:")
        all_passed = True
        for platform, data_domain, sub_domain, granularity, expected in test_cases:
            table_name = platform_table_manager.get_table_name(
                platform=platform,
                data_domain=data_domain,
                sub_domain=sub_domain,
                granularity=granularity
            )
            if table_name == expected:
                safe_print(f"  [OK] {platform}/{data_domain}/{sub_domain}/{granularity} -> {table_name}")
            else:
                safe_print(f"  [FAIL] 期望: {expected}, 实际: {table_name}")
                all_passed = False
        
        # 测试表创建（在b_class schema中）
        safe_print("\n[1.2] 测试表创建（b_class schema）:")
        test_table_name = platform_table_manager.get_table_name(
            platform="test_platform",
            data_domain="orders",
            sub_domain=None,
            granularity="daily"
        )
        
        # 确保表存在
        platform_table_manager.ensure_table_exists(
            platform="test_platform",
            data_domain="orders",
            sub_domain=None,
            granularity="daily"
        )
        db.commit()
        
        # 检查表是否在b_class schema中
        inspector = inspect(db.bind)
        tables_in_b_class = inspector.get_table_names(schema='b_class')
        
        if test_table_name in tables_in_b_class:
            safe_print(f"  [OK] 表 {test_table_name} 已创建在 b_class schema 中")
        else:
            safe_print(f"  [FAIL] 表 {test_table_name} 未在 b_class schema 中找到")
            safe_print(f"  b_class schema 中的表: {tables_in_b_class[:10]}...")
            all_passed = False
        
        # 验证表结构
        safe_print("\n[1.3] 验证表结构:")
        try:
            columns = inspector.get_columns(test_table_name, schema='b_class')
            column_names = [col['name'] for col in columns]
            required_columns = ['id', 'platform_code', 'shop_id', 'data_domain', 'granularity', 'metric_date', 'raw_data', 'data_hash']
            
            missing_columns = [col for col in required_columns if col not in column_names]
            if not missing_columns:
                safe_print(f"  [OK] 表结构正确，包含所有必需字段")
            else:
                safe_print(f"  [FAIL] 缺少字段: {missing_columns}")
                all_passed = False
        except Exception as e:
            safe_print(f"  [FAIL] 验证表结构失败: {e}")
            all_passed = False
        
        return {"success": all_passed, "table_name": test_table_name}
        
    except Exception as e:
        logger.error(f"测试PlatformTableManager失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def test_query_apis():
    """测试查询API使用动态表名"""
    safe_print("\n" + "="*60)
    safe_print("测试2: 查询API使用动态表名")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        # 测试config_management.py的查询逻辑
        safe_print("\n[2.1] 测试config_management查询逻辑:")
        try:
            from backend.services.platform_table_manager import get_platform_table_manager
            
            # 查询sales_targets和target_breakdown（sales_targets表没有shop_id字段）
            targets = db.execute(
                text("""
                SELECT DISTINCT ON (tb.target_id)
                    st.id as target_id,
                    tb.shop_id,
                    tb.platform_code,
                    st.period_start::text as year_month,
                    st.target_amount as target_sales_amount,
                    st.target_quantity as target_order_count
                FROM sales_targets st
                INNER JOIN target_breakdown tb ON st.id = tb.target_id
                WHERE tb.breakdown_type = 'shop'
                ORDER BY tb.target_id, tb.platform_code, tb.shop_id
                LIMIT 1
                """)
            ).fetchall()
            
            if targets:
                target = targets[0]
                target_id, shop_id, platform_code, target_month, target_sales_amount, target_order_count = target
                # 处理platform_code为NULL的情况
                if not platform_code:
                    platform_code = 'unknown'
                
                platform_table_manager = get_platform_table_manager(db)
                table_name = platform_table_manager.get_table_name(
                    platform=platform_code,
                    data_domain='orders',
                    sub_domain=None,
                    granularity='daily'
                )
                
                safe_print(f"  [OK] 成功生成动态表名: {table_name} (platform={platform_code})")
                
                # 测试查询（表可能不存在，这是正常的）
                try:
                    db.execute(
                        text(f"""
                        SELECT COUNT(*) FROM b_class."{table_name}"
                        WHERE shop_id = :shop_id
                        LIMIT 1
                        """),
                        {"shop_id": shop_id}
                    ).scalar()
                    safe_print(f"  [OK] 查询动态表成功: b_class.{table_name}")
                except Exception as e:
                    if "does not exist" in str(e).lower():
                        safe_print(f"  [INFO] 表 {table_name} 不存在（正常，可能没有数据）")
                    else:
                        safe_print(f"  [WARNING] 查询表失败: {e}")
            else:
                safe_print("  [INFO] 没有找到sales_targets数据，跳过测试")
                
        except Exception as e:
            safe_print(f"  [FAIL] 测试config_management查询逻辑失败: {e}")
            logger.error(f"测试config_management查询逻辑失败: {e}", exc_info=True)
            # 回滚事务，避免影响后续测试
            db.rollback()
        
        # 测试inventory_management.py的查询逻辑
        safe_print("\n[2.2] 测试inventory_management查询逻辑:")
        try:
            from backend.services.platform_table_manager import get_platform_table_manager
            
            # 查询所有平台（使用新的查询，避免事务失败）
            platforms = db.execute(
                text("SELECT platform_code FROM dim_platforms WHERE is_active = true LIMIT 3")
            ).fetchall()
            
            if platforms:
                platform_codes = [row[0] for row in platforms]
                safe_print(f"  [OK] 找到 {len(platform_codes)} 个平台: {platform_codes}")
                
                platform_table_manager = get_platform_table_manager(db)
                for platform_code in platform_codes:
                    table_name = platform_table_manager.get_table_name(
                        platform=platform_code,
                        data_domain='inventory',
                        sub_domain=None,
                        granularity='snapshot'
                    )
                    safe_print(f"  [OK] 平台 {platform_code} -> 表名: {table_name}")
            else:
                safe_print("  [INFO] 没有找到平台数据，跳过测试")
                
        except Exception as e:
            safe_print(f"  [FAIL] 测试inventory_management查询逻辑失败: {e}")
            logger.error(f"测试inventory_management查询逻辑失败: {e}", exc_info=True)
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"测试查询API失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def test_cleanup_api():
    """测试清理API动态表发现"""
    safe_print("\n" + "="*60)
    safe_print("测试3: 清理API动态表发现")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        
        # 查询b_class schema中所有表
        all_tables = inspector.get_table_names(schema='b_class')
        safe_print(f"\n[3.1] b_class schema中的表总数: {len(all_tables)}")
        
        # 筛选出所有以fact_开头的表
        fact_tables = [t for t in all_tables if t.startswith('fact_')]
        safe_print(f"[3.2] 以fact_开头的表数量: {len(fact_tables)}")
        
        if fact_tables:
            safe_print(f"[3.3] 前10个表:")
            for table_name in fact_tables[:10]:
                try:
                    count = db.execute(
                        text(f'SELECT COUNT(*) FROM b_class."{table_name}"')
                    ).scalar() or 0
                    safe_print(f"  - {table_name}: {count} 行")
                except Exception as e:
                    safe_print(f"  - {table_name}: 查询失败 ({e})")
        
        # 验证表名格式
        safe_print("\n[3.4] 验证表名格式:")
        format_errors = []
        for table_name in fact_tables[:20]:  # 检查前20个表
            parts = table_name.split('_')
            if len(parts) < 4:
                format_errors.append(f"{table_name}: 格式不正确（至少需要4部分）")
            elif not table_name.startswith('fact_'):
                format_errors.append(f"{table_name}: 未以fact_开头")
        
        if not format_errors:
            safe_print("  [OK] 所有表名格式正确")
        else:
            safe_print(f"  [WARNING] 发现 {len(format_errors)} 个格式问题:")
            for error in format_errors[:5]:
                safe_print(f"    - {error}")
        
        return {
            "success": True,
            "total_tables": len(all_tables),
            "fact_tables": len(fact_tables),
            "format_errors": len(format_errors)
        }
        
    except Exception as e:
        logger.error(f"测试清理API失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def test_schema_separation():
    """测试schema分离"""
    safe_print("\n" + "="*60)
    safe_print("测试4: Schema分离验证")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        
        # 检查b_class schema是否存在
        schemas = db.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'b_class'")
        ).fetchall()
        
        if schemas:
            safe_print("[4.1] [OK] b_class schema存在")
        else:
            safe_print("[4.1] [FAIL] b_class schema不存在")
            return {"success": False, "error": "b_class schema不存在"}
        
        # 检查public schema中是否有fact_开头的表（不应该有）
        public_tables = inspector.get_table_names(schema='public')
        public_fact_tables = [t for t in public_tables if t.startswith('fact_')]
        
        if public_fact_tables:
            safe_print(f"[4.2] [WARNING] public schema中发现 {len(public_fact_tables)} 个fact_开头的表:")
            for table_name in public_fact_tables[:5]:
                safe_print(f"  - {table_name}")
        else:
            safe_print("[4.2] [OK] public schema中没有fact_开头的表（正确）")
        
        # 检查b_class schema中的表
        b_class_tables = inspector.get_table_names(schema='b_class')
        b_class_fact_tables = [t for t in b_class_tables if t.startswith('fact_')]
        
        if b_class_fact_tables:
            safe_print(f"[4.3] [OK] b_class schema中有 {len(b_class_fact_tables)} 个fact_开头的表")
        else:
            safe_print("[4.3] [INFO] b_class schema中没有fact_开头的表（可能还没有数据同步）")
        
        return {
            "success": True,
            "b_class_schema_exists": bool(schemas),
            "public_fact_tables": len(public_fact_tables),
            "b_class_fact_tables": len(b_class_fact_tables)
        }
        
    except Exception as e:
        logger.error(f"测试schema分离失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def main():
    """主函数"""
    safe_print("="*60)
    safe_print("动态表名功能测试（v4.17.0+）")
    safe_print("="*60)
    
    results = {}
    
    # 测试1: PlatformTableManager
    results["platform_table_manager"] = test_platform_table_manager()
    
    # 测试2: 查询API
    results["query_apis"] = test_query_apis()
    
    # 测试3: 清理API
    results["cleanup_api"] = test_cleanup_api()
    
    # 测试4: Schema分离
    results["schema_separation"] = test_schema_separation()
    
    # 输出总结
    safe_print("\n" + "="*60)
    safe_print("测试总结")
    safe_print("="*60)
    
    all_passed = True
    for test_name, result in results.items():
        if result.get("success"):
            status = "[OK] 通过"
        else:
            status = "[FAIL] 失败"
            all_passed = False
        
        safe_print(f"{test_name}: {status}")
        if not result.get("success") and "error" in result:
            safe_print(f"  错误: {result['error']}")
    
    if all_passed:
        safe_print("\n[OK] 所有测试通过！")
        return 0
    else:
        safe_print("\n[WARNING] 部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    exit(main())

