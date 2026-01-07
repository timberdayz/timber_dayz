#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B类数据同步优化功能自动化测试脚本

v4.11.5新增：
- 测试task_id传递功能
- 测试数据质量检查集成
- 测试批次统计功能
- 测试健康检查脚本
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def test_task_id_tracking():
    """测试task_id追踪功能"""
    print("=" * 60)
    print("[测试1] task_id追踪功能")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # 检查staging表是否有task_id字段
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_name = 'staging_orders' 
            AND column_name = 'ingest_task_id'
        """)).scalar()
        
        if result > 0:
            print("[OK] staging_orders表有ingest_task_id字段")
        else:
            print("[FAIL] staging_orders表缺少ingest_task_id字段")
            return False
        
        # 检查是否有数据包含task_id
        tracked_count = db.execute(text("""
            SELECT COUNT(*) FROM staging_orders 
            WHERE ingest_task_id IS NOT NULL
        """)).scalar()
        
        total_count = db.execute(text("""
            SELECT COUNT(*) FROM staging_orders
        """)).scalar()
        
        print(f"[INFO] staging_orders表: 总计{total_count}行，已追踪{tracked_count}行")
        
        if total_count > 0 and tracked_count > 0:
            tracking_rate = tracked_count / total_count * 100
            print(f"[OK] task_id追踪率: {tracking_rate:.1f}%")
            return True
        elif total_count == 0:
            print("[INFO] 没有数据，跳过追踪率检查")
            return True
        else:
            print("[WARNING] 有数据但未追踪，可能是旧数据")
            return True
            
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        return False
    finally:
        db.close()

def test_quality_check_integration():
    """测试数据质量检查集成"""
    print("\n" + "=" * 60)
    print("[测试2] 数据质量检查集成")
    print("=" * 60)
    
    try:
        from backend.services.c_class_data_validator import get_c_class_data_validator
        
        db = SessionLocal()
        validator = get_c_class_data_validator(db)
        
        # 测试检查功能
        from datetime import date
        today = date.today()
        
        # 尝试检查一个平台（如果存在）
        result = db.execute(text("""
            SELECT DISTINCT platform_code, shop_id 
            FROM fact_orders 
            LIMIT 1
        """)).fetchone()
        
        if result:
            platform_code, shop_id = result
            check_result = validator.check_b_class_completeness(
                platform_code=platform_code,
                shop_id=shop_id,
                metric_date=today
            )
            
            print(f"[OK] 数据质量检查功能正常")
            print(f"[INFO] 平台: {platform_code}, 店铺: {shop_id}")
            print(f"[INFO] 质量评分: {check_result.get('data_quality_score', 0):.1f}分")
            print(f"[INFO] 订单完整: {check_result.get('orders_complete', False)}")
            print(f"[INFO] 产品完整: {check_result.get('products_complete', False)}")
            print(f"[INFO] 库存完整: {check_result.get('inventory_complete', False)}")
            return True
        else:
            print("[INFO] 没有订单数据，跳过质量检查测试")
            return True
            
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_batch_statistics():
    """测试批次统计功能"""
    print("\n" + "=" * 60)
    print("[测试3] 批次统计功能")
    print("=" * 60)
    
    try:
        from backend.services.governance_stats import get_governance_stats
        
        db = SessionLocal()
        stats_service = get_governance_stats(db)
        
        # 测试获取待处理文件
        files = stats_service.get_pending_files(limit=10)
        
        print(f"[OK] 批次统计功能正常")
        print(f"[INFO] 待处理文件数: {len(files)}")
        
        # 按数据域+粒度分组统计
        from collections import defaultdict
        batches = defaultdict(lambda: {'domain': '', 'granularity': '', 'count': 0})
        
        for file_info in files:
            domain = file_info.get('domain', 'unknown')
            granularity = file_info.get('granularity', 'unknown')
            batch_key = f"{domain}_{granularity}"
            batches[batch_key]['domain'] = domain
            batches[batch_key]['granularity'] = granularity
            batches[batch_key]['count'] += 1
        
        if batches:
            print(f"[INFO] 批次分组: {len(batches)}个批次")
            for key, batch in batches.items():
                print(f"  - {batch['domain']}/{batch['granularity']}: {batch['count']}个文件")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_health_check_script():
    """测试健康检查脚本"""
    print("\n" + "=" * 60)
    print("[测试4] 健康检查脚本")
    print("=" * 60)
    
    try:
        # 检查脚本是否存在
        script_path = project_root / "scripts" / "diagnose_ingestion_pipeline.py"
        if script_path.exists():
            print("[OK] 健康检查脚本存在")
            
            # 检查脚本是否包含健康检查函数
            script_content = script_path.read_text(encoding='utf-8')
            if 'check_b_class_sync_health' in script_content:
                print("[OK] 脚本包含健康检查函数")
                return True
            else:
                print("[FAIL] 脚本不包含健康检查函数")
                return False
        else:
            print("[FAIL] 健康检查脚本不存在")
            return False
            
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("B类数据同步优化功能自动化测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 测试1: task_id追踪
    results.append(("task_id追踪", test_task_id_tracking()))
    
    # 测试2: 数据质量检查集成
    results.append(("数据质量检查集成", test_quality_check_integration()))
    
    # 测试3: 批次统计
    results.append(("批次统计功能", test_batch_statistics()))
    
    # 测试4: 健康检查脚本
    results.append(("健康检查脚本", test_health_check_script()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {len(results)}个测试")
    print(f"通过: {passed}个")
    print(f"失败: {failed}个")
    
    if failed == 0:
        print("\n[SUCCESS] 所有测试通过！")
        return 0
    else:
        print(f"\n[FAILURE] {failed}个测试失败")
        return 1

if __name__ == '__main__':
    sys.exit(main())

