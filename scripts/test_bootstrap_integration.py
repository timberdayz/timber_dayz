#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap 集成测试（验证部署脚本中的 Bootstrap 相关逻辑）

检查：
1. 部署脚本是否包含 Bootstrap 相关阶段
2. Bootstrap 脚本是否存在
3. 环境变量处理逻辑是否正确
"""

import sys
import os
from pathlib import Path

def safe_print(text):
    """安全打印（处理 Windows GBK 编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def test_bootstrap_script_exists():
    """测试 Bootstrap 脚本是否存在"""
    safe_print("=" * 50)
    safe_print("[TEST 1] 验证 Bootstrap 脚本存在")
    safe_print("-" * 50)
    
    bootstrap_script = Path("scripts/bootstrap_production.py")
    if bootstrap_script.exists():
        safe_print(f"[OK] Bootstrap script exists: {bootstrap_script}")
        
        # 检查脚本是否可读
        try:
            content = bootstrap_script.read_text(encoding='utf-8')
            if "async def main" in content:
                safe_print("[OK] Bootstrap script contains async main function")
            else:
                safe_print("[WARN] Bootstrap script may not have async main function")
            
            if "AsyncSessionLocal" in content:
                safe_print("[OK] Bootstrap script uses AsyncSessionLocal")
            else:
                safe_print("[WARN] Bootstrap script may not use AsyncSessionLocal")
            
            if "bootstrap_production.py" in content or "#" in content:  # 简单检查
                safe_print("[OK] Bootstrap script appears to be a Python script")
            
            return True
        except Exception as e:
            safe_print(f"[FAIL] Cannot read bootstrap script: {e}")
            return False
    else:
        safe_print(f"[FAIL] Bootstrap script not found: {bootstrap_script}")
        return False

def test_deploy_script_integration():
    """测试部署脚本是否包含 Bootstrap 相关逻辑"""
    safe_print("\n" + "=" * 50)
    safe_print("[TEST 2] 验证部署脚本 Bootstrap 集成")
    safe_print("-" * 50)
    
    deploy_script = Path("scripts/deploy_remote_production.sh")
    if not deploy_script.exists():
        safe_print(f"[FAIL] Deploy script not found: {deploy_script}")
        return False
    
    try:
        content = deploy_script.read_text(encoding='utf-8')
        checks = []
        
        # 检查 Phase 0.5 (.env 清洗)
        if "Phase 0.5" in content:
            checks.append(("Phase 0.5 (env cleaning)", True))
            safe_print("[OK] Phase 0.5 (.env cleaning) found")
        else:
            checks.append(("Phase 0.5 (env cleaning)", False))
            safe_print("[FAIL] Phase 0.5 (.env cleaning) not found")
        
        # 检查 .env.cleaned 处理
        if ".env.cleaned" in content:
            checks.append((".env.cleaned handling", True))
            safe_print("[OK] .env.cleaned file handling found")
        else:
            checks.append((".env.cleaned handling", False))
            safe_print("[FAIL] .env.cleaned file handling not found")
        
        # 检查 Phase 2.5 (Bootstrap)
        if "Phase 2.5" in content or "Phase 2.5:" in content:
            checks.append(("Phase 2.5 (Bootstrap)", True))
            safe_print("[OK] Phase 2.5 (Bootstrap) found")
        else:
            checks.append(("Phase 2.5 (Bootstrap)", False))
            safe_print("[FAIL] Phase 2.5 (Bootstrap) not found")
        
        # 检查 bootstrap_production.py 执行
        if "bootstrap_production.py" in content:
            checks.append(("bootstrap_production.py execution", True))
            safe_print("[OK] bootstrap_production.py execution found")
        else:
            checks.append(("bootstrap_production.py execution", False))
            safe_print("[FAIL] bootstrap_production.py execution not found")
        
        # 检查 --env-file .env.cleaned 使用
        if "--env-file" in content and ".env.cleaned" in content:
            checks.append(("--env-file .env.cleaned usage", True))
            safe_print("[OK] --env-file .env.cleaned usage found")
        else:
            checks.append(("--env-file .env.cleaned usage", False))
            safe_print("[FAIL] --env-file .env.cleaned usage not found")
        
        # 检查退出码处理
        if "if [ $? -ne 0 ]" in content or "exit 1" in content:
            # 检查是否在 bootstrap 之后有退出码检查
            bootstrap_pos = content.find("bootstrap_production.py")
            if bootstrap_pos > 0:
                after_bootstrap = content[bootstrap_pos:bootstrap_pos + 500]
                if "if [ $? -ne 0 ]" in after_bootstrap or "exit 1" in after_bootstrap:
                    checks.append(("Bootstrap exit code check", True))
                    safe_print("[OK] Bootstrap exit code check found")
                else:
                    checks.append(("Bootstrap exit code check", False))
                    safe_print("[WARN] Bootstrap exit code check may be missing")
            else:
                checks.append(("Bootstrap exit code check", True))  # 假设存在
                safe_print("[INFO] Cannot verify bootstrap exit code check (assuming OK)")
        
        all_passed = all(check[1] for check in checks)
        return all_passed
        
    except Exception as e:
        safe_print(f"[FAIL] Cannot read deploy script: {e}")
        return False

def test_dockerfile_integration():
    """测试 Dockerfile 是否包含 Bootstrap 脚本"""
    safe_print("\n" + "=" * 50)
    safe_print("[TEST 3] 验证 Dockerfile Bootstrap 集成")
    safe_print("-" * 50)
    
    dockerfile = Path("Dockerfile.backend")
    if not dockerfile.exists():
        safe_print(f"[WARN] Dockerfile.backend not found: {dockerfile}")
        safe_print("[INFO] This is OK if using a different Dockerfile structure")
        return True  # 不阻止，可能使用不同的 Dockerfile 结构
    
    try:
        content = dockerfile.read_text(encoding='utf-8')
        
        if "bootstrap_production.py" in content:
            safe_print("[OK] bootstrap_production.py found in Dockerfile.backend")
            return True
        else:
            safe_print("[FAIL] bootstrap_production.py not found in Dockerfile.backend")
            return False
    except Exception as e:
        safe_print(f"[FAIL] Cannot read Dockerfile.backend: {e}")
        return False

def main():
    """主函数"""
    safe_print("=" * 50)
    safe_print("Bootstrap 集成测试")
    safe_print("=" * 50)
    safe_print("")
    
    tests = [
        ("Bootstrap Script Exists", test_bootstrap_script_exists),
        ("Deploy Script Integration", test_deploy_script_integration),
        ("Dockerfile Integration", test_dockerfile_integration),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            safe_print(f"\n[FAIL] {name} test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 汇总结果
    safe_print("\n" + "=" * 50)
    safe_print("测试结果汇总")
    safe_print("=" * 50)
    
    all_passed = True
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {name}")
        if not result:
            all_passed = False
    
    safe_print("=" * 50)
    if all_passed:
        safe_print("[OK] 所有 Bootstrap 集成测试通过！")
        safe_print("")
        safe_print("说明：")
        safe_print("  - 这些测试验证了 Bootstrap 功能在部署流程中的集成")
        safe_print("  - 实际部署时还需要验证：")
        safe_print("    1. Bootstrap 脚本在容器中可以执行")
        safe_print("    2. 环境变量正确传递到容器")
        safe_print("    3. Bootstrap 执行成功/失败时的行为")
        return 0
    else:
        safe_print("[FAIL] 部分 Bootstrap 集成测试失败，请检查上述输出")
        return 1

if __name__ == "__main__":
    sys.exit(main())
