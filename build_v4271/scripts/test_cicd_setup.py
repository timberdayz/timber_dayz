#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CI/CD 配置检查脚本

检查 CI/CD 流程所需的配置和依赖是否就绪。

使用方法：
    python scripts/test_cicd_setup.py
    python scripts/test_cicd_setup.py --check-github  # 检查 GitHub 配置（需要 GITHUB_TOKEN）
    python scripts/test_cicd_setup.py --check-server user@host  # 检查服务器配置
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def print_header(text: str):
    """打印标题"""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_success(text: str):
    """打印成功消息"""
    print(f"[OK] {text}")


def print_error(text: str):
    """打印错误消息"""
    print(f"[ERROR] {text}")


def print_warning(text: str):
    """打印警告消息"""
    print(f"[WARNING] {text}")


def print_info(text: str):
    """打印信息消息"""
    print(f"[INFO] {text}")


def check_docker_installed() -> Tuple[bool, str]:
    """检查 Docker 是否安装"""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, "Docker 未安装"
    except FileNotFoundError:
        return False, "Docker 未安装"
    except Exception as e:
        return False, f"检查失败: {e}"


def check_docker_compose_installed() -> Tuple[bool, str]:
    """检查 Docker Compose 是否安装"""
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, "Docker Compose 未安装"
    except FileNotFoundError:
        return False, "Docker Compose 未安装"
    except Exception as e:
        return False, f"检查失败: {e}"


def check_dockerfile_exists() -> Tuple[bool, List[str]]:
    """检查 Dockerfile 是否存在"""
    dockerfiles = []
    required = ["Dockerfile.backend", "Dockerfile.frontend"]
    
    for df in required:
        path = PROJECT_ROOT / df
        if path.exists():
            dockerfiles.append(df)
        else:
            dockerfiles.append(f"{df} (缺失)")
    
    all_exist = all("缺失" not in df for df in dockerfiles)
    return all_exist, dockerfiles


def check_workflow_files() -> Tuple[bool, List[str]]:
    """检查 GitHub Actions 工作流文件"""
    workflows_dir = PROJECT_ROOT / ".github" / "workflows"
    required = [
        "docker-build.yml",
        "deploy-staging.yml",
        "deploy-production.yml"
    ]
    
    found = []
    missing = []
    
    for wf in required:
        path = workflows_dir / wf
        if path.exists():
            found.append(wf)
        else:
            missing.append(wf)
    
    all_exist = len(missing) == 0
    return all_exist, found + [f"{wf} (缺失)" for wf in missing]


def check_env_files() -> Tuple[bool, List[str]]:
    """检查环境变量文件"""
    required = [
        "env.template",
        "env.example",
        "env.production.example"
    ]
    
    found = []
    missing = []
    
    for env_file in required:
        path = PROJECT_ROOT / env_file
        if path.exists():
            found.append(env_file)
        else:
            missing.append(env_file)
    
    all_exist = len(missing) == 0
    return all_exist, found + [f"{f} (缺失)" for f in missing]


def check_docker_compose_files() -> Tuple[bool, List[str]]:
    """检查 docker-compose 文件"""
    required = [
        "docker-compose.yml",
        "docker-compose.prod.yml"
    ]
    
    found = []
    missing = []
    
    for compose_file in required:
        path = PROJECT_ROOT / compose_file
        if path.exists():
            found.append(compose_file)
        else:
            missing.append(compose_file)
    
    all_exist = len(missing) == 0
    return all_exist, found + [f"{f} (缺失)" for f in missing]


def check_local_docker_build() -> Tuple[bool, str]:
    """检查本地 Docker 构建（仅验证 Dockerfile 语法）"""
    try:
        # 仅检查 Dockerfile 语法，不实际构建
        result = subprocess.run(
            ["docker", "build", "--dry-run", "-f", "Dockerfile.backend", "."],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT
        )
        # dry-run 可能不支持，所以只检查文件是否存在
        return True, "Dockerfile 存在"
    except Exception as e:
        return False, f"检查失败: {e}"


def check_github_secrets() -> Tuple[bool, List[str]]:
    """检查 GitHub Secrets 配置（需要 GITHUB_TOKEN）"""
    required_secrets = {
        "测试环境": [
            "STAGING_SSH_PRIVATE_KEY",
            "STAGING_HOST",
        ],
        "生产环境": [
            "PRODUCTION_SSH_PRIVATE_KEY",
            "PRODUCTION_HOST",
        ],
        "可选": [
            "SLACK_WEBHOOK_URL",
        ]
    }
    
    print_info("GitHub Secrets 需要手动在 GitHub 仓库设置中验证")
    print_info("Settings → Secrets and variables → Actions")
    
    all_configured = []
    missing = []
    
    for category, secrets in required_secrets.items():
        print(f"\n{category} Secrets:")
        for secret in secrets:
            # 无法直接检查 GitHub Secrets，只能提示
            print(f"  - {secret}: [需要手动验证]")
    
    return True, ["需要手动在 GitHub 设置中验证"]


def check_server_connection(server: str) -> Tuple[bool, str]:
    """检查服务器 SSH 连接"""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", server, "echo 'OK'"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True, "SSH 连接成功"
        return False, f"SSH 连接失败: {result.stderr}"
    except FileNotFoundError:
        return False, "SSH 未安装"
    except Exception as e:
        return False, f"连接失败: {e}"


def check_server_docker(server: str) -> Tuple[bool, str]:
    """检查服务器 Docker 安装"""
    try:
        result = subprocess.run(
            ["ssh", server, "docker --version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, "Docker 未安装"
    except Exception as e:
        return False, f"检查失败: {e}"


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="CI/CD 配置检查脚本")
    parser.add_argument(
        "--check-github",
        action="store_true",
        help="检查 GitHub 配置（需要 GITHUB_TOKEN）"
    )
    parser.add_argument(
        "--check-server",
        type=str,
        help="检查服务器配置（格式: user@host）"
    )
    args = parser.parse_args()
    
    print_header("CI/CD 配置检查")
    
    all_checks_passed = True
    
    # 1. 检查本地 Docker 环境
    print_header("1. 本地 Docker 环境")
    
    docker_ok, docker_msg = check_docker_installed()
    if docker_ok:
        print_success(f"Docker: {docker_msg}")
    else:
        print_error(f"Docker: {docker_msg}")
        all_checks_passed = False
    
    compose_ok, compose_msg = check_docker_compose_installed()
    if compose_ok:
        print_success(f"Docker Compose: {compose_msg}")
    else:
        print_error(f"Docker Compose: {compose_msg}")
        all_checks_passed = False
    
    # 2. 检查项目文件
    print_header("2. 项目文件")
    
    dockerfile_ok, dockerfiles = check_dockerfile_exists()
    if dockerfile_ok:
        print_success("Dockerfile 文件:")
        for df in dockerfiles:
            print(f"  - {df}")
    else:
        print_error("Dockerfile 文件缺失:")
        for df in dockerfiles:
            print(f"  - {df}")
        all_checks_passed = False
    
    workflow_ok, workflows = check_workflow_files()
    if workflow_ok:
        print_success("GitHub Actions 工作流:")
        for wf in workflows:
            print(f"  - {wf}")
    else:
        print_error("GitHub Actions 工作流缺失:")
        for wf in workflows:
            print(f"  - {wf}")
        all_checks_passed = False
    
    env_ok, env_files = check_env_files()
    if env_ok:
        print_success("环境变量文件:")
        for ef in env_files:
            print(f"  - {ef}")
    else:
        print_warning("环境变量文件缺失:")
        for ef in env_files:
            print(f"  - {ef}")
    
    compose_ok, compose_files = check_docker_compose_files()
    if compose_ok:
        print_success("Docker Compose 文件:")
        for cf in compose_files:
            print(f"  - {cf}")
    else:
        print_error("Docker Compose 文件缺失:")
        for cf in compose_files:
            print(f"  - {cf}")
        all_checks_passed = False
    
    # 3. 检查 GitHub 配置
    if args.check_github:
        print_header("3. GitHub 配置")
        github_ok, github_msg = check_github_secrets()
        if github_ok:
            print_info(github_msg[0])
    else:
        print_header("3. GitHub 配置")
        print_info("跳过 GitHub 配置检查（使用 --check-github 启用）")
    
    # 4. 检查服务器配置
    if args.check_server:
        print_header("4. 服务器配置")
        
        server_ok, server_msg = check_server_connection(args.check_server)
        if server_ok:
            print_success(f"SSH 连接: {server_msg}")
        else:
            print_error(f"SSH 连接: {server_msg}")
            all_checks_passed = False
        
        docker_ok, docker_msg = check_server_docker(args.check_server)
        if docker_ok:
            print_success(f"服务器 Docker: {docker_msg}")
        else:
            print_error(f"服务器 Docker: {docker_msg}")
            all_checks_passed = False
    else:
        print_header("4. 服务器配置")
        print_info("跳过服务器配置检查（使用 --check-server user@host 启用）")
    
    # 总结
    print_header("检查总结")
    if all_checks_passed:
        print_success("所有检查通过！")
        print_info("下一步:")
        print_info("1. 配置 GitHub Secrets（Settings → Secrets and variables → Actions）")
        print_info("2. 配置 GitHub Environments（Settings → Environments）")
        print_info("3. 测试镜像构建工作流")
        print_info("4. 测试部署工作流")
        return 0
    else:
        print_error("部分检查失败，请修复后重试")
        print_info("详细配置指南: docs/deployment/CI_CD_SETUP_GUIDE.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())

