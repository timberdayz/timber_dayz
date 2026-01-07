#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试Celery任务执行

测试Celery任务是否能正常执行
"""

import sys
from pathlib import Path
import time

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

def test_task_submit():
    """测试任务提交"""
    print("=" * 60)
    print("Celery任务直接测试")
    print("=" * 60)
    
    try:
        from backend.tasks.data_sync_tasks import sync_batch_async
        
        print("\n[1] 提交测试任务...")
        # 提交一个空任务测试（不实际处理文件）
        result = sync_batch_async.delay(
            file_ids=[],  # 空列表，只测试任务提交
            task_id="test_direct_task",
            only_with_template=True,
            allow_quarantine=True,
            max_concurrent=1
        )
        
        print(f"  ✅ 任务已提交")
        print(f"     Celery Task ID: {result.id}")
        print(f"     任务状态: {result.state}")
        
        # 等待任务完成（最多10秒）
        print("\n[2] 等待任务完成...")
        try:
            task_result = result.get(timeout=10)
            print(f"  ✅ 任务完成")
            print(f"     结果: {task_result}")
            return True
        except Exception as e:
            print(f"  ⚠️  任务未完成: {e}")
            print(f"     任务状态: {result.state}")
            print(f"     提示: 请检查Celery Worker是否正在运行")
            return False
            
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_task_submit()
    sys.exit(0 if success else 1)

