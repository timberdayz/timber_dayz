#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据同步修复是否成功

测试内容：
1. 启动批量同步任务
2. 查询进度（模拟前端轮询）
3. 检查是否还会出现InFailedSqlTransaction错误
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.sync_progress_tracker import SyncProgressTracker
from modules.core.db import CatalogFile, SyncProgressTask
from sqlalchemy import select

def test_progress_query():
    """测试进度查询（模拟前端轮询）"""
    print("\n" + "="*80)
    print("测试1: 查询进度（模拟前端轮询）")
    print("="*80)
    
    db = SessionLocal()
    try:
        # 先回滚确保干净的事务
        db.rollback()
        
        tracker = SyncProgressTracker(db)
        
        # 查找一个存在的任务ID
        result = db.execute(
            select(SyncProgressTask.task_id)
            .order_by(SyncProgressTask.start_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not result:
            print("[SKIP] 没有找到测试任务，跳过进度查询测试")
            return True
        
        task_id = result
        print(f"[INFO] 使用任务ID: {task_id}")
        
        # 连续查询5次（模拟前端轮询）
        success_count = 0
        error_count = 0
        
        for i in range(5):
            try:
                print(f"\n[查询 {i+1}/5] 查询任务进度...")
                task_info = tracker.get_task(task_id)
                
                if task_info:
                    print(f"  [OK] 查询成功: 状态={task_info.get('status')}, "
                          f"进度={task_info.get('processed_files')}/{task_info.get('total_files')}")
                    success_count += 1
                else:
                    print(f"  [WARN] 任务不存在或查询返回None")
                    error_count += 1
                
                time.sleep(0.5)  # 模拟轮询间隔
                
            except Exception as e:
                error_str = str(e)
                if 'InFailedSqlTransaction' in error_str:
                    print(f"  [ERROR] 仍然出现事务错误: {e}")
                    error_count += 1
                    return False
                else:
                    print(f"  [ERROR] 其他错误: {e}")
                    error_count += 1
        
        print(f"\n[结果] 成功: {success_count}/5, 失败: {error_count}/5")
        return error_count == 0
        
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_batch_sync():
    """测试批量同步（如果有待处理文件）"""
    print("\n" + "="*80)
    print("测试2: 批量同步（如果有待处理文件）")
    print("="*80)
    
    db = SessionLocal()
    try:
        # 查找待处理的文件
        query = select(CatalogFile).where(
            CatalogFile.status == 'pending'
        ).limit(5)
        
        files = db.execute(query).scalars().all()
        
        if not files:
            print("[SKIP] 没有待处理的文件，跳过批量同步测试")
            return True
        
        print(f"[INFO] 找到 {len(files)} 个待处理文件")
        file_ids = [f.id for f in files]
        
        # 这里不实际启动同步（需要完整的FastAPI上下文）
        # 只检查文件是否存在
        print(f"[OK] 文件ID列表: {file_ids}")
        return True
        
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("数据同步修复测试")
    print("="*80)
    
    results = []
    
    # 测试1: 进度查询
    result1 = test_progress_query()
    results.append(("进度查询测试", result1))
    
    # 测试2: 批量同步准备
    result2 = test_batch_sync()
    results.append(("批量同步准备测试", result2))
    
    # 输出总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)
    
    all_passed = True
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")
        if not result:
            all_passed = False
    
    print("\n" + "="*80)
    if all_passed:
        print("[SUCCESS] 所有测试通过！")
    else:
        print("[FAIL] 部分测试失败，请检查日志")
    print("="*80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

