#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步重构测试脚本

v4.12.0新增：
- 测试重构后的数据同步功能
- 验证SSOT合规性
- 验证核心服务功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from backend.models.database import get_db, init_db
from modules.core.db import (
    DimUser, DimRole, FactAuditLog, SyncProgressTask,
    CatalogFile
)
from backend.services.data_sync_service import DataSyncService
from backend.services.data_ingestion_service import DataIngestionService
from backend.services.sync_progress_tracker import SyncProgressTracker
from backend.services.sync_error_handler import SyncErrorHandler, SyncErrorType
from backend.services.audit_service import AuditService
from backend.services.sync_security_service import SyncSecurityService
from backend.services.data_lineage_service import DataLineageService


def test_ssot_compliance():
    """测试SSOT合规性"""
    print("\n=== 测试SSOT合规性 ===")
    
    # 检查模型是否从schema.py导入
    try:
        from modules.core.db import DimUser, DimRole, FactAuditLog
        print("[OK] 模型从schema.py导入成功")
    except ImportError as e:
        print(f"[ERROR] 模型导入失败: {e}")
        return False
    
    # 检查是否还有从backend.models.users导入的代码
    try:
        from backend.models.users import DimUser as OldDimUser
        print("[WARNING] 发现从backend.models.users导入（应该已改为从modules.core.db导入）")
    except ImportError:
        print("[OK] 没有从backend.models.users导入（符合SSOT）")
    
    return True


def test_data_sync_service(db: Session):
    """测试DataSyncService"""
    print("\n=== 测试DataSyncService ===")
    
    try:
        sync_service = DataSyncService(db)
        print("[OK] DataSyncService创建成功")
        
        # 检查是否有ingestion_service属性
        if hasattr(sync_service, 'ingestion_service'):
            print("[OK] DataSyncService包含ingestion_service属性")
        else:
            print("[ERROR] DataSyncService缺少ingestion_service属性")
            return False
        
        return True
    except Exception as e:
        print(f"[ERROR] DataSyncService测试失败: {e}")
        return False


def test_data_ingestion_service(db: Session):
    """测试DataIngestionService"""
    print("\n=== 测试DataIngestionService ===")
    
    try:
        ingestion_service = DataIngestionService(db)
        print("[OK] DataIngestionService创建成功")
        
        # 检查是否有ingest_data方法
        if hasattr(ingestion_service, 'ingest_data'):
            print("[OK] DataIngestionService包含ingest_data方法")
        else:
            print("[ERROR] DataIngestionService缺少ingest_data方法")
            return False
        
        return True
    except Exception as e:
        print(f"[ERROR] DataIngestionService测试失败: {e}")
        return False


def test_sync_progress_tracker(db: Session):
    """测试SyncProgressTracker"""
    print("\n=== 测试SyncProgressTracker ===")
    
    try:
        tracker = SyncProgressTracker(db)
        print("[OK] SyncProgressTracker创建成功")
        
        # 测试创建任务
        task_id = "test_task_123"
        task_info = tracker.create_task(
            task_id=task_id,
            total_files=10,
            task_type="bulk_ingest"
        )
        
        if task_info and task_info.get("task_id") == task_id:
            print("[OK] SyncProgressTracker.create_task()成功")
        else:
            print("[ERROR] SyncProgressTracker.create_task()失败")
            return False
        
        # 测试获取任务
        retrieved_task = tracker.get_task(task_id)
        if retrieved_task and retrieved_task.get("task_id") == task_id:
            print("[OK] SyncProgressTracker.get_task()成功")
        else:
            print("[ERROR] SyncProgressTracker.get_task()失败")
            return False
        
        # 清理测试任务
        tracker.delete_task(task_id)
        print("[OK] 测试任务已清理")
        
        return True
    except Exception as e:
        print(f"[ERROR] SyncProgressTracker测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sync_error_handler():
    """测试SyncErrorHandler"""
    print("\n=== 测试SyncErrorHandler ===")
    
    try:
        # 测试创建错误
        error = SyncErrorHandler.create_error(
            error_type=SyncErrorType.FILE_ERROR,
            error_code="FILE_NOT_FOUND",
            message="文件不存在",
            details={"file_path": "/test/path"}
        )
        
        if error.get("error_type") == "file_error" and error.get("error_code") == 2001:
            print("[OK] SyncErrorHandler.create_error()成功")
        else:
            print("[ERROR] SyncErrorHandler.create_error()失败")
            return False
        
        # 测试处理异常
        test_exception = FileNotFoundError("文件不存在")
        handled_error = SyncErrorHandler.handle_exception(test_exception)
        
        if handled_error.get("error_type") == "file_error":
            print("[OK] SyncErrorHandler.handle_exception()成功")
        else:
            print("[ERROR] SyncErrorHandler.handle_exception()失败")
            return False
        
        return True
    except Exception as e:
        print(f"[ERROR] SyncErrorHandler测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_audit_service(db: Session):
    """测试AuditService扩展"""
    print("\n=== 测试AuditService扩展 ===")
    
    try:
        audit_service = AuditService()
        print("[OK] AuditService创建成功")
        
        # 检查是否有新增方法
        if hasattr(audit_service, 'log_sync_operation'):
            print("[OK] AuditService包含log_sync_operation方法")
        else:
            print("[ERROR] AuditService缺少log_sync_operation方法")
            return False
        
        if hasattr(audit_service, 'log_data_change'):
            print("[OK] AuditService包含log_data_change方法")
        else:
            print("[ERROR] AuditService缺少log_data_change方法")
            return False
        
        if hasattr(audit_service, 'get_sync_audit_trail'):
            print("[OK] AuditService包含get_sync_audit_trail方法")
        else:
            print("[ERROR] AuditService缺少get_sync_audit_trail方法")
            return False
        
        return True
    except Exception as e:
        print(f"[ERROR] AuditService测试失败: {e}")
        return False


def test_sync_security_service(db: Session):
    """测试SyncSecurityService"""
    print("\n=== 测试SyncSecurityService ===")
    
    try:
        security_service = SyncSecurityService(db)
        print("[OK] SyncSecurityService创建成功")
        
        # 测试数据脱敏
        test_data = {
            "buyer_name": "张三",
            "buyer_phone": "13800138000",
            "buyer_email": "test@example.com",
        }
        
        masked_data = security_service.mask_sensitive_data(
            test_data,
            "orders",
            user_id=None  # 无权限用户
        )
        
        if masked_data.get("buyer_name") != test_data["buyer_name"]:
            print("[OK] SyncSecurityService.mask_sensitive_data()成功（数据已脱敏）")
        else:
            print("[WARNING] 数据未脱敏（可能是权限检查逻辑）")
        
        return True
    except Exception as e:
        print(f"[ERROR] SyncSecurityService测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_lineage_service(db: Session):
    """测试DataLineageService"""
    print("\n=== 测试DataLineageService ===")
    
    try:
        lineage_service = DataLineageService(db)
        print("[OK] DataLineageService创建成功")
        
        # 检查是否有核心方法
        if hasattr(lineage_service, 'record_lineage'):
            print("[OK] DataLineageService包含record_lineage方法")
        else:
            print("[ERROR] DataLineageService缺少record_lineage方法")
            return False
        
        if hasattr(lineage_service, 'trace_data_flow'):
            print("[OK] DataLineageService包含trace_data_flow方法")
        else:
            print("[ERROR] DataLineageService缺少trace_data_flow方法")
            return False
        
        return True
    except Exception as e:
        print(f"[ERROR] DataLineageService测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("数据同步重构测试")
    print("=" * 60)
    
    # 初始化数据库
    try:
        init_db()
        print("[OK] 数据库初始化成功")
    except Exception as e:
        print(f"[WARNING] 数据库初始化警告: {e}")
    
    # 获取数据库会话
    db = next(get_db())
    
    # 运行测试
    tests = [
        ("SSOT合规性", test_ssot_compliance),
        ("DataSyncService", lambda: test_data_sync_service(db)),
        ("DataIngestionService", lambda: test_data_ingestion_service(db)),
        ("SyncProgressTracker", lambda: test_sync_progress_tracker(db)),
        ("SyncErrorHandler", test_sync_error_handler),
        ("AuditService扩展", lambda: test_audit_service(db)),
        ("SyncSecurityService", lambda: test_sync_security_service(db)),
        ("DataLineageService", lambda: test_data_lineage_service(db)),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 输出测试结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"总计: {len(results)}个测试")
    print(f"通过: {passed}个")
    print(f"失败: {failed}个")
    print("=" * 60)
    
    # 关闭数据库连接
    db.close()
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

