#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试GitHub Actions部署流程
检查部署配置和镜像仓库可用性
"""

import os
import sys
import subprocess
from pathlib import Path

def check_github_secrets():
    """检查GitHub Secrets配置"""
    print("\n" + "="*60)
    print("GitHub Secrets 配置检查")
    print("="*60)
    
    required_secrets = [
        "PRODUCTION_SSH_PRIVATE_KEY",
        "PRODUCTION_HOST",
        "PRODUCTION_USER",
        "PRODUCTION_PATH"
    ]
    
    optional_secrets = [
        "PRODUCTION_URL",
        "SLACK_WEBHOOK_URL"
    ]
    
    print("\n[必需Secrets]")
    print("  注意: 这些Secrets需要在GitHub仓库中配置")
    print("  位置: Settings > Secrets and variables > Actions")
    print()
    
    for secret in required_secrets:
        print(f"  - {secret}")
    
    print("\n[可选Secrets]")
    for secret in optional_secrets:
        print(f"  - {secret} (可选)")
    
    print("\n[配置说明]")
    print("  1. PRODUCTION_SSH_PRIVATE_KEY: 服务器SSH私钥（完整内容）")
    print("  2. PRODUCTION_HOST: 服务器IP地址（如：123.456.789.0）")
    print("  3. PRODUCTION_USER: SSH用户名（如：root或ubuntu）")
    print("  4. PRODUCTION_PATH: 项目路径（如：/opt/xihong_erp）")
    print("  5. PRODUCTION_URL: 生产环境URL（用于健康检查，可选）")

def check_github_repo():
    """检查GitHub仓库信息"""
    print("\n" + "="*60)
    print("GitHub仓库信息")
    print("="*60)
    
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            print(f"\n[仓库URL]")
            print(f"  {url}")
            
            # 提取仓库名
            import re
            match = re.search(r"github\.com[:/]([^/]+/[^/]+)\.git", url)
            if match:
                repo_name = match.group(1)
                print(f"\n[仓库名称]")
                print(f"  {repo_name}")
                
                print(f"\n[镜像仓库地址]")
                print(f"  后端: ghcr.io/{repo_name}/backend")
                print(f"  前端: ghcr.io/{repo_name}/frontend")
                
                return repo_name
    except Exception as e:
        print(f"[ERROR] 无法获取GitHub仓库信息: {e}")
    
    return None

def check_docker_images():
    """检查Docker镜像"""
    print("\n" + "="*60)
    print("Docker镜像检查")
    print("="*60)
    
    repo_name = check_github_repo()
    if not repo_name:
        print("[WARN] 无法确定仓库名称，跳过镜像检查")
        return
    
    backend_image = f"ghcr.io/{repo_name}/backend"
    frontend_image = f"ghcr.io/{repo_name}/frontend"
    
    print(f"\n[检查镜像]")
    print(f"  后端: {backend_image}:latest")
    print(f"  前端: {frontend_image}:latest")
    
    # 检查本地是否有镜像
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            images = result.stdout.strip().split('\n')
            backend_found = any(backend_image in img for img in images)
            frontend_found = any(frontend_image in img for img in images)
            
            if backend_found:
                print(f"  [OK] 后端镜像已存在（本地）")
            else:
                print(f"  [INFO] 后端镜像不存在（本地），需要从仓库拉取")
            
            if frontend_found:
                print(f"  [OK] 前端镜像已存在（本地）")
            else:
                print(f"  [INFO] 前端镜像不存在（本地），需要从仓库拉取")
    except Exception as e:
        print(f"  [WARN] 无法检查本地镜像: {e}")

def check_workflow_files():
    """检查工作流文件"""
    print("\n" + "="*60)
    print("GitHub Actions 工作流检查")
    print("="*60)
    
    workflow_dir = Path(__file__).parent.parent / ".github" / "workflows"
    
    if not workflow_dir.exists():
        print("[FAIL] .github/workflows 目录不存在")
        return
    
    workflows = {
        "docker-build.yml": "Docker镜像构建和推送",
        "deploy-production.yml": "生产环境部署",
        "deploy-staging.yml": "测试环境部署",
        "ci.yml": "CI流程"
    }
    
    print("\n[工作流文件]")
    for filename, description in workflows.items():
        workflow_file = workflow_dir / filename
        if workflow_file.exists():
            print(f"  [OK] {filename} - {description}")
        else:
            print(f"  [FAIL] {filename} - {description} (文件不存在)")

def test_deployment_readiness():
    """测试部署就绪状态"""
    print("\n" + "="*60)
    print("部署就绪状态检查")
    print("="*60)
    
    checks = {
        "GitHub仓库": check_github_repo() is not None,
        "Docker已安装": check_docker_installed(),
        "工作流文件": check_workflow_files_exist(),
    }
    
    print("\n[检查结果]")
    all_ok = True
    for check_name, result in checks.items():
        if result:
            print(f"  [OK] {check_name}")
        else:
            print(f"  [FAIL] {check_name}")
            all_ok = False
    
    return all_ok

def check_docker_installed():
    """检查Docker是否安装"""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_workflow_files_exist():
    """检查工作流文件是否存在"""
    workflow_dir = Path(__file__).parent.parent / ".github" / "workflows"
    required_files = ["docker-build.yml", "deploy-production.yml"]
    
    if not workflow_dir.exists():
        return False
    
    for filename in required_files:
        if not (workflow_dir / filename).exists():
            return False
    
    return True

def main():
    """主函数"""
    print("="*60)
    print("GitHub Actions 部署测试工具")
    print("="*60)
    
    # 检查GitHub Secrets配置
    check_github_secrets()
    
    # 检查GitHub仓库
    repo_name = check_github_repo()
    
    # 检查Docker镜像
    if repo_name:
        check_docker_images()
    
    # 检查工作流文件
    check_workflow_files()
    
    # 测试部署就绪状态
    is_ready = test_deployment_readiness()
    
    # 总结
    print("\n" + "="*60)
    print("部署测试总结")
    print("="*60)
    
    if is_ready:
        print("\n[OK] 基本配置检查通过")
        print("\n[下一步]")
        print("  1. 确认GitHub Secrets已配置")
        print("  2. 在GitHub Actions中手动触发部署工作流")
        print("  3. 或推送版本标签触发自动部署: git tag v4.19.7 && git push origin v4.19.7")
    else:
        print("\n[FAIL] 部分检查未通过，请查看上方详情")
    
    print("\n[部署工作流]")
    print("  1. 打开GitHub仓库: https://github.com/timberdayz/timber_dayz")
    print("  2. 进入 Actions 标签页")
    print("  3. 选择 'Deploy to Production' 工作流")
    print("  4. 点击 'Run workflow'")
    print("  5. 输入镜像标签（如：latest 或 v4.19.7）")
    print("  6. 输入确认信息: DEPLOY")
    print("  7. 点击 'Run workflow' 开始部署")
    
    return 0 if is_ready else 1

if __name__ == "__main__":
    sys.exit(main())
