#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证用户注册和审批API是否正确注册

使用方法：
    python backend/verify_registration_api.py

此脚本会检查：
1. API路由是否正确注册
2. Schemas是否正确导入
3. 错误码是否正确定义
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def verify_api_routes():
    """验证API路由是否正确注册"""
    print("=" * 60)
    print("[1/4] 验证API路由注册")
    print("=" * 60)
    
    try:
        from backend.main import app
        
        # 检查路由
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                methods = ', '.join(route.methods) if route.methods else 'N/A'
                routes.append((route.path, methods))
        
        # 检查关键路由
        required_routes = [
            ("/api/auth/register", "POST"),
            ("/api/users/{user_id}/approve", "POST"),
            ("/api/users/{user_id}/reject", "POST"),
            ("/api/users/pending", "GET"),
        ]
        
        found_routes = []
        missing_routes = []
        
        for required_path, required_method in required_routes:
            found = False
            for path, methods in routes:
                if required_path in path and required_method in methods:
                    found = True
                    found_routes.append((required_path, required_method))
                    break
            if not found:
                missing_routes.append((required_path, required_method))
        
        print(f"\n总路由数: {len(routes)}")
        print(f"\n找到的关键路由 ({len(found_routes)}/{len(required_routes)}):")
        for path, method in found_routes:
            print(f"  [OK] {method} {path}")
        
        if missing_routes:
            print(f"\n缺失的路由 ({len(missing_routes)}):")
            for path, method in missing_routes:
                print(f"  [FAIL] {method} {path}")
            return False
        else:
            print("\n[SUCCESS] 所有关键路由已正确注册")
            return True
    
    except Exception as e:
        print(f"\n[ERROR] 验证路由时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_schemas():
    """验证Schemas是否正确导入"""
    print("\n" + "=" * 60)
    print("[2/4] 验证Schemas导入")
    print("=" * 60)
    
    try:
        from backend.schemas.auth import (
            RegisterRequest,
            RegisterResponse,
            ApproveUserRequest,
            RejectUserRequest,
            PendingUserResponse
        )
        
        schemas = [
            ("RegisterRequest", RegisterRequest),
            ("RegisterResponse", RegisterResponse),
            ("ApproveUserRequest", ApproveUserRequest),
            ("RejectUserRequest", RejectUserRequest),
            ("PendingUserResponse", PendingUserResponse),
        ]
        
        print("\n找到的Schemas:")
        for name, schema_class in schemas:
            print(f"  [OK] {name}")
            # 验证字段
            if hasattr(schema_class, 'model_fields'):
                fields = list(schema_class.model_fields.keys())
                print(f"      字段: {', '.join(fields[:5])}{'...' if len(fields) > 5 else ''}")
        
        print("\n[SUCCESS] 所有Schemas已正确导入")
        return True
    
    except Exception as e:
        print(f"\n[ERROR] 验证Schemas时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_error_codes():
    """验证错误码是否正确定义"""
    print("\n" + "=" * 60)
    print("[3/4] 验证错误码定义")
    print("=" * 60)
    
    try:
        from backend.utils.error_codes import ErrorCode, get_error_type, get_error_message
        
        required_codes = [
            ("AUTH_ACCOUNT_PENDING", 4005),
            ("AUTH_ACCOUNT_REJECTED", 4006),
            ("AUTH_ACCOUNT_SUSPENDED", 4007),
            ("AUTH_ACCOUNT_INACTIVE", 4008),
        ]
        
        print("\n找到的错误码:")
        all_found = True
        for code_name, code_value in required_codes:
            if hasattr(ErrorCode, code_name):
                code = getattr(ErrorCode, code_name)
                if code == code_value:
                    error_type = get_error_type(code)
                    error_msg = get_error_message(code, "")
                    print(f"  [OK] {code_name} = {code} ({error_type})")
                    if error_msg:
                        print(f"       消息: {error_msg}")
                else:
                    print(f"  [WARN] {code_name} = {code} (期望 {code_value})")
                    all_found = False
            else:
                print(f"  [FAIL] {code_name} 未定义")
                all_found = False
        
        if all_found:
            print("\n[SUCCESS] 所有错误码已正确定义")
            return True
        else:
            print("\n[WARN] 部分错误码定义不正确")
            return False
    
    except Exception as e:
        print(f"\n[ERROR] 验证错误码时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_models():
    """验证数据库模型是否正确导入"""
    print("\n" + "=" * 60)
    print("[4/4] 验证数据库模型")
    print("=" * 60)
    
    try:
        from modules.core.db import DimUser, UserApprovalLog
        
        # 检查DimUser是否有新字段
        user_fields = [col.name for col in DimUser.__table__.columns]
        required_fields = ["status", "approved_at", "approved_by", "rejection_reason"]
        
        print("\nDimUser表字段检查:")
        found_fields = []
        missing_fields = []
        for field in required_fields:
            if field in user_fields:
                found_fields.append(field)
                print(f"  [OK] {field}")
            else:
                missing_fields.append(field)
                print(f"  [FAIL] {field} 缺失")
        
        # 检查UserApprovalLog模型
        print("\nUserApprovalLog模型检查:")
        approval_fields = [col.name for col in UserApprovalLog.__table__.columns]
        required_approval_fields = ["log_id", "user_id", "action", "approved_by", "reason", "created_at"]
        
        found_approval_fields = []
        missing_approval_fields = []
        for field in required_approval_fields:
            if field in approval_fields:
                found_approval_fields.append(field)
                print(f"  [OK] {field}")
            else:
                missing_approval_fields.append(field)
                print(f"  [FAIL] {field} 缺失")
        
        if not missing_fields and not missing_approval_fields:
            print("\n[SUCCESS] 所有数据库模型字段正确")
            return True
        else:
            print("\n[WARN] 部分数据库模型字段缺失（可能需要运行迁移）")
            return False
    
    except Exception as e:
        print(f"\n[ERROR] 验证数据库模型时出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("用户注册和审批API验证")
    print("=" * 60)
    print("\n此脚本验证API路由、Schemas、错误码和数据库模型的正确性")
    print("注意：此脚本不测试实际API调用，只验证代码结构\n")
    
    results = []
    
    # 验证路由
    results.append(("API路由", verify_api_routes()))
    
    # 验证Schemas
    results.append(("Schemas", verify_schemas()))
    
    # 验证错误码
    results.append(("错误码", verify_error_codes()))
    
    # 验证模型
    results.append(("数据库模型", verify_models()))
    
    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n[SUCCESS] 所有验证通过！")
        print("\n下一步：")
        print("1. 启动后端服务: python run.py 或 python run_new.py")
        print("2. 运行API测试: python backend/test_registration_api_manual.py")
    else:
        print("\n[WARN] 部分验证失败，请检查上述错误信息")
    
    print("=" * 60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

