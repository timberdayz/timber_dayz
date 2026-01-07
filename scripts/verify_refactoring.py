#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步重构验证脚本（简化版）

v4.12.0新增：
- 快速验证重构后的代码是否正确
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(msg):
    """安全打印（Windows兼容）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('gbk', errors='ignore').decode('gbk'))

def test_imports():
    """测试导入"""
    safe_print("\n=== 测试导入 ===")
    
    try:
        from modules.core.db import DimUser, DimRole, FactAuditLog, SyncProgressTask
        safe_print("[OK] schema.py模型导入成功")
    except Exception as e:
        safe_print(f"[ERROR] schema.py模型导入失败: {e}")
        return False
    
    try:
        from backend.services.data_sync_service import DataSyncService
        safe_print("[OK] DataSyncService导入成功")
    except Exception as e:
        safe_print(f"[ERROR] DataSyncService导入失败: {e}")
        return False
    
    try:
        from backend.services.data_ingestion_service import DataIngestionService
        safe_print("[OK] DataIngestionService导入成功")
    except Exception as e:
        safe_print(f"[ERROR] DataIngestionService导入失败: {e}")
        return False
    
    try:
        from backend.services.sync_progress_tracker import SyncProgressTracker
        safe_print("[OK] SyncProgressTracker导入成功")
    except Exception as e:
        safe_print(f"[ERROR] SyncProgressTracker导入失败: {e}")
        return False
    
    try:
        from backend.services.sync_error_handler import SyncErrorHandler, SyncErrorType
        safe_print("[OK] SyncErrorHandler导入成功")
    except Exception as e:
        safe_print(f"[ERROR] SyncErrorHandler导入失败: {e}")
        return False
    
    try:
        from backend.services.audit_service import AuditService
        safe_print("[OK] AuditService导入成功")
    except Exception as e:
        safe_print(f"[ERROR] AuditService导入失败: {e}")
        return False
    
    try:
        from backend.services.sync_security_service import SyncSecurityService
        safe_print("[OK] SyncSecurityService导入成功")
    except Exception as e:
        safe_print(f"[ERROR] SyncSecurityService导入失败: {e}")
        return False
    
    try:
        from backend.services.data_lineage_service import DataLineageService
        safe_print("[OK] DataLineageService导入成功")
    except Exception as e:
        safe_print(f"[ERROR] DataLineageService导入失败: {e}")
        return False
    
    try:
        from backend.routers import data_sync
        safe_print("[OK] data_sync路由导入成功")
    except Exception as e:
        safe_print(f"[ERROR] data_sync路由导入失败: {e}")
        return False
    
    return True

def test_service_creation():
    """测试服务创建"""
    safe_print("\n=== 测试服务创建 ===")
    
    try:
        from backend.models.database import get_db
        db = next(get_db())
        
        from backend.services.data_sync_service import DataSyncService
        sync_service = DataSyncService(db)
        safe_print("[OK] DataSyncService创建成功")
        
        from backend.services.data_ingestion_service import DataIngestionService
        ingestion_service = DataIngestionService(db)
        safe_print("[OK] DataIngestionService创建成功")
        
        from backend.services.sync_progress_tracker import SyncProgressTracker
        tracker = SyncProgressTracker(db)
        safe_print("[OK] SyncProgressTracker创建成功")
        
        from backend.services.sync_security_service import SyncSecurityService
        security_service = SyncSecurityService(db)
        safe_print("[OK] SyncSecurityService创建成功")
        
        from backend.services.data_lineage_service import DataLineageService
        lineage_service = DataLineageService(db)
        safe_print("[OK] DataLineageService创建成功")
        
        db.close()
        return True
    except Exception as e:
        safe_print(f"[ERROR] 服务创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handler():
    """测试错误处理"""
    safe_print("\n=== 测试错误处理 ===")
    
    try:
        from backend.services.sync_error_handler import SyncErrorHandler, SyncErrorType
        
        error = SyncErrorHandler.create_error(
            error_type=SyncErrorType.FILE_ERROR,
            error_code="FILE_NOT_FOUND",
            message="测试错误"
        )
        
        if error.get("error_code") == 2001:
            safe_print("[OK] SyncErrorHandler.create_error()成功")
        else:
            safe_print(f"[ERROR] SyncErrorHandler.create_error()失败: {error}")
            return False
        
        return True
    except Exception as e:
        safe_print(f"[ERROR] 错误处理测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_audit_service():
    """测试审计服务"""
    safe_print("\n=== 测试审计服务 ===")
    
    try:
        from backend.services.audit_service import AuditService
        
        audit_service = AuditService()
        
        if hasattr(audit_service, 'log_sync_operation'):
            safe_print("[OK] AuditService包含log_sync_operation方法")
        else:
            safe_print("[ERROR] AuditService缺少log_sync_operation方法")
            return False
        
        if hasattr(audit_service, 'log_data_change'):
            safe_print("[OK] AuditService包含log_data_change方法")
        else:
            safe_print("[ERROR] AuditService缺少log_data_change方法")
            return False
        
        return True
    except Exception as e:
        safe_print(f"[ERROR] 审计服务测试失败: {e}")
        return False

def main():
    """主函数"""
    safe_print("=" * 60)
    safe_print("数据同步重构验证")
    safe_print("=" * 60)
    
    results = []
    
    results.append(("导入测试", test_imports()))
    results.append(("服务创建测试", test_service_creation()))
    results.append(("错误处理测试", test_error_handler()))
    results.append(("审计服务测试", test_audit_service()))
    
    safe_print("\n" + "=" * 60)
    safe_print("验证结果汇总")
    safe_print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    safe_print("\n" + "=" * 60)
    safe_print(f"总计: {len(results)}个测试")
    safe_print(f"通过: {passed}个")
    safe_print(f"失败: {failed}个")
    safe_print("=" * 60)
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

