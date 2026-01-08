#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查密码配置和镜像仓库可用性
"""

import os
import sys
from pathlib import Path
import subprocess
import re

def check_env_file():
    """检查.env文件中的密码配置"""
    env_file = Path(__file__).parent.parent / ".env"
    
    if not env_file.exists():
        print("[WARN] .env 文件不存在")
        return False
    
    print("\n" + "="*60)
    print("密码配置检查")
    print("="*60)
    
    required_keys = [
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "SECRET_KEY",
        "JWT_SECRET_KEY",
        "ACCOUNT_ENCRYPTION_KEY"
    ]
    
    optional_keys = [
        "PGADMIN_PASSWORD",
        "METABASE_ENCRYPTION_SECRET_KEY",
        "METABASE_EMBEDDING_SECRET_KEY"
    ]
    
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查必需配置
    print("\n[必需配置]")
    all_configured = True
    for key in required_keys:
        pattern = rf"^{key}=(.*)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value and value not in ["", "YOUR_SECURE_PASSWORD_HERE", "YOUR_SECRET_KEY_CHANGE_THIS", 
                                       "YOUR_REDIS_PASSWORD_HERE", "YOUR_JWT_SECRET_KEY_CHANGE_THIS"]:
                # 只显示前4个字符和后4个字符
                masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "*" * len(value)
                print(f"  [OK] {key}: {masked} (已配置)")
            else:
                print(f"  [FAIL] {key}: [未配置或使用默认值]")
                all_configured = False
        else:
            print(f"  [FAIL] {key}: [未找到]")
            all_configured = False
    
    # 检查可选配置
    print("\n[可选配置]")
    for key in optional_keys:
        pattern = rf"^{key}=(.*)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value and value not in ["", "CHANGE_THIS"]:
                masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "*" * len(value)
                print(f"  [OK] {key}: {masked} (已配置)")
            else:
                print(f"  [WARN] {key}: [未配置]")
        else:
            print(f"  [WARN] {key}: [未找到]")
    
    return all_configured

def get_github_repo():
    """获取GitHub仓库信息"""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # 提取仓库名
            match = re.search(r"github\.com[:/]([^/]+/[^/]+)\.git", url)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"[ERROR] 无法获取GitHub仓库信息: {e}")
    return None

def check_registry_accessibility(repo_name):
    """检查镜像仓库是否可访问"""
    if not repo_name:
        print("\n[WARN] 无法确定GitHub仓库，跳过镜像仓库检查")
        return False
    
    backend_image = f"ghcr.io/{repo_name}/backend"
    frontend_image = f"ghcr.io/{repo_name}/frontend"
    
    print("\n" + "="*60)
    print("镜像仓库检查")
    print("="*60)
    
    print(f"\n[仓库信息]")
    print(f"  GitHub仓库: {repo_name}")
    print(f"  后端镜像: {backend_image}")
    print(f"  前端镜像: {frontend_image}")
    
    print(f"\n[可用性检查]")
    
    # 检查Docker是否可用
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"  [OK] Docker已安装: {result.stdout.strip()}")
        else:
            print(f"  [FAIL] Docker未安装或不可用")
            return False
    except FileNotFoundError:
        print(f"  [FAIL] Docker未安装")
        return False
    
    # 尝试拉取镜像（不实际拉取，只检查是否存在）
    print(f"\n[镜像检查]")
    print(f"  注意: 需要GitHub认证才能访问私有镜像")
    print(f"  如果镜像未公开，需要先登录: docker login ghcr.io")
    
    # 检查是否已登录
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"  [OK] Docker守护进程运行正常")
    except Exception as e:
        print(f"  [WARN] 无法检查Docker状态: {e}")
    
    return True

def generate_passwords():
    """生成密码和密钥"""
    print("\n" + "="*60)
    print("密码生成工具")
    print("="*60)
    
    try:
        import secrets
        from cryptography.fernet import Fernet
        
        print("\n[生成密码]")
        print("  POSTGRES_PASSWORD:")
        print(f"    {secrets.token_urlsafe(24)}")
        
        print("\n  REDIS_PASSWORD:")
        print(f"    {secrets.token_urlsafe(24)}")
        
        print("\n[生成密钥]")
        print("  SECRET_KEY:")
        print(f"    {secrets.token_urlsafe(32)}")
        
        print("\n  JWT_SECRET_KEY:")
        print(f"    {secrets.token_urlsafe(32)}")
        
        print("\n  ACCOUNT_ENCRYPTION_KEY:")
        print(f"    {Fernet.generate_key().decode()}")
        
    except ImportError as e:
        print(f"\n[ERROR] 缺少依赖: {e}")
        print("  请安装: pip install cryptography")

def main():
    """主函数"""
    print("="*60)
    print("密码配置和镜像仓库检查工具")
    print("="*60)
    
    # 检查密码配置
    passwords_ok = check_env_file()
    
    # 获取仓库信息
    repo_name = get_github_repo()
    
    # 检查镜像仓库
    registry_ok = check_registry_accessibility(repo_name)
    
    # 总结
    print("\n" + "="*60)
    print("检查总结")
    print("="*60)
    
    if passwords_ok:
        print("  [OK] 所有必需密码已配置")
    else:
        print("  [FAIL] 部分密码未配置，请查看上方详情")
        print("\n  生成新密码命令:")
        print("    python scripts/check_passwords_and_registry.py --generate")
    
    if repo_name:
        print(f"  [OK] GitHub仓库: {repo_name}")
        print(f"  [OK] 镜像仓库: ghcr.io/{repo_name}")
    else:
        print("  [FAIL] 无法确定GitHub仓库")
    
    if registry_ok:
        print("  [OK] Docker环境正常")
    else:
        print("  [WARN] Docker环境检查失败")
    
    print("\n[部署建议]")
    print("  1. 确保所有密码已配置（使用强密码）")
    print("  2. 在GitHub Actions中配置PRODUCTION_SSH_PRIVATE_KEY等Secrets")
    print("  3. 确保GitHub仓库的Packages权限已启用")
    print("  4. 在服务器上登录镜像仓库: docker login ghcr.io")
    
    return 0 if passwords_ok and repo_name else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--generate":
        generate_passwords()
    else:
        sys.exit(main())
