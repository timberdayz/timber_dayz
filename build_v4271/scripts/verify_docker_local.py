#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Docker 化验证脚本
检查 Docker 环境、配置文件、构建和运行状态
"""

import subprocess
import sys
import os
from pathlib import Path
import json

def safe_print(text, color="white"):
    """安全打印（处理Windows编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def run_command(cmd, check=True):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_docker_installed():
    """检查 Docker 是否安装"""
    safe_print("\n[1/9] 检查 Docker 环境...")
    
    # 检查 docker 命令
    success, stdout, stderr = run_command("docker --version", check=False)
    if not success:
        safe_print("  [FAIL] Docker 未安装或不在 PATH 中")
        return False, None
    safe_print(f"  [OK] Docker 已安装: {stdout.strip()}")
    
    # 检查 docker-compose 或 docker compose
    success_v1, stdout_v1, _ = run_command("docker-compose --version", check=False)
    success_v2, stdout_v2, _ = run_command("docker compose version", check=False)
    
    if success_v1:
        safe_print(f"  [OK] docker-compose (v1) 已安装: {stdout_v1.strip()}")
        return True, "v1"
    elif success_v2:
        safe_print(f"  [OK] docker compose (v2) 已安装: {stdout_v2.strip()}")
        return True, "v2"
    else:
        safe_print("  [FAIL] docker-compose 未安装")
        return False, None

def check_docker_running():
    """检查 Docker 是否运行"""
    safe_print("\n[2/9] 检查 Docker 服务状态...")
    
    success, stdout, stderr = run_command("docker ps", check=False)
    if not success:
        safe_print("  [FAIL] Docker 服务未运行")
        safe_print(f"  错误: {stderr[:200]}")
        return False
    
    safe_print("  [OK] Docker 服务正在运行")
    return True

def check_config_files(compose_version):
    """检查配置文件"""
    safe_print("\n[3/9] 检查 Docker Compose 配置文件...")
    
    required_files = [
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.prod.yml",
        "Dockerfile.backend",
        "Dockerfile.frontend",
    ]
    
    all_exist = True
    for file in required_files:
        if Path(file).exists():
            safe_print(f"  [OK] {file} 存在")
        else:
            safe_print(f"  [FAIL] {file} 不存在")
            all_exist = False
    
    # 检查配置文件语法
    safe_print("\n  验证配置文件语法...")
    if compose_version == "v1":
        cmd = "docker-compose -f docker-compose.yml -f docker-compose.dev.yml config"
    else:
        cmd = "docker compose -f docker-compose.yml -f docker-compose.dev.yml config"
    
    success, stdout, stderr = run_command(cmd, check=False)
    if success:
        safe_print("  [OK] 配置文件语法正确")
    else:
        safe_print("  [WARN] 配置文件语法验证失败")
        error_lines = stderr.split('\n')[-5:] if stderr else []
        for line in error_lines:
            if line.strip():
                safe_print(f"    {line}")
    
    return all_exist

def check_dockerfiles():
    """检查 Dockerfile"""
    safe_print("\n[4/9] 检查 Dockerfile...")
    
    dockerfiles = {
        "Dockerfile.backend": ["FROM", "WORKDIR", "COPY", "RUN"],
        "Dockerfile.frontend": ["FROM", "WORKDIR", "COPY", "RUN"],
    }
    
    all_valid = True
    for dockerfile, required_keywords in dockerfiles.items():
        if not Path(dockerfile).exists():
            safe_print(f"  [FAIL] {dockerfile} 不存在")
            all_valid = False
            continue
        
        try:
            content = Path(dockerfile).read_text(encoding='utf-8')
            missing = [kw for kw in required_keywords if kw not in content]
            
            if missing:
                safe_print(f"  [WARN] {dockerfile} 缺少关键指令: {', '.join(missing)}")
            else:
                safe_print(f"  [OK] {dockerfile} 结构完整")
        except Exception as e:
            safe_print(f"  [WARN] {dockerfile} 读取失败: {e}")
    
    return all_valid

def check_profiles():
    """检查 profiles 配置"""
    safe_print("\n[5/9] 检查 Profiles 配置...")
    
    # 读取 docker-compose.yml
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        safe_print("  [FAIL] docker-compose.yml 不存在")
        return False
    
    try:
        content = compose_file.read_text(encoding='utf-8')
    except Exception as e:
        safe_print(f"  [FAIL] 无法读取 docker-compose.yml: {e}")
        return False
    
    # 检查关键服务是否有 profiles（使用更准确的匹配）
    services_needing_profiles = ["backend", "frontend", "postgres", "redis"]
    missing_profiles = []
    
    for service in services_needing_profiles:
        # 查找服务定义（考虑缩进）
        service_pattern = f"  {service}:"
        if service_pattern in content:
            # 找到服务块（直到下一个顶级服务或文件结束）
            service_start = content.find(service_pattern)
            # 查找下一个顶级服务（以两个空格开头的服务名）
            next_service_pattern = "\n  "
            service_end = content.find(next_service_pattern, service_start + len(service_pattern))
            if service_end == -1:
                service_end = len(content)
            
            service_block = content[service_start:service_end]
            # 检查是否有 profiles（考虑多行格式）
            if "profiles:" in service_block or f"{service}:" in content and "profiles:" in content[content.find(f"{service}:"):content.find(f"{service}:")+2000]:
                safe_print(f"  [OK] {service} 服务有 profiles 配置")
            else:
                missing_profiles.append(service)
                safe_print(f"  [WARN] {service} 服务缺少 profiles 配置")
        else:
            safe_print(f"  [WARN] {service} 服务未在 docker-compose.yml 中找到")
    
    if missing_profiles:
        safe_print(f"  [WARN] 以下服务缺少 profiles: {', '.join(missing_profiles)}")
        return False
    
    return True

def check_prod_profiles():
    """检查 docker-compose.prod.yml 中的 profiles（使用 Docker Compose 验证）"""
    safe_print("\n[6/9] 检查 docker-compose.prod.yml Profiles 配置...")
    
    prod_file = Path("docker-compose.prod.yml")
    if not prod_file.exists():
        safe_print("  [WARN] docker-compose.prod.yml 不存在")
        return False
    
    # 使用 Docker Compose 实际验证配置（更可靠）
    compose_version = "v1"  # 默认使用 v1
    success_v2, _, _ = run_command("docker compose version", check=False)
    if success_v2:
        compose_version = "v2"
    
    if compose_version == "v1":
        cmd = "docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config"
    else:
        cmd = "docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile production config"
    
    success, stdout, stderr = run_command(cmd, check=False)
    
    if not success:
        safe_print("  [WARN] Docker Compose 配置验证失败，无法检查 profiles")
        safe_print(f"  错误: {stderr[:200]}")
        return False
    
    # 检查关键服务是否在合并后的配置中
    services_needing_profiles = ["backend", "frontend", "nginx", "celery-worker", "celery-beat"]
    missing_profiles = []
    
    for service in services_needing_profiles:
        # 检查服务是否在配置中
        if f"  {service}:" in stdout:
            # 检查是否有 profiles
            service_start = stdout.find(f"  {service}:")
            service_end = stdout.find("\n  ", service_start + 1)
            if service_end == -1:
                service_end = min(service_start + 2000, len(stdout))
            
            service_block = stdout[service_start:service_end]
            if "profiles:" in service_block:
                safe_print(f"  [OK] {service} 服务有 profiles 配置")
            else:
                missing_profiles.append(service)
                safe_print(f"  [WARN] {service} 服务缺少 profiles 配置")
        else:
            missing_profiles.append(service)
            safe_print(f"  [WARN] {service} 服务未在合并后的配置中找到")
    
    if missing_profiles:
        safe_print(f"  [WARN] 以下服务缺少 profiles: {', '.join(missing_profiles)}")
        return False
    
    return True

def check_build_files():
    """检查构建文件"""
    safe_print("\n[7/9] 检查构建文件...")
    
    # 检查 .dockerignore
    if Path(".dockerignore").exists():
        safe_print("  [OK] .dockerignore 存在")
    else:
        safe_print("  [WARN] .dockerignore 不存在（建议添加）")
    
    # 检查必要的构建文件
    build_files = [
        "backend/requirements.txt",
        "frontend/package.json",
    ]
    
    all_exist = True
    for file in build_files:
        if Path(file).exists():
            safe_print(f"  [OK] {file} 存在")
        else:
            safe_print(f"  [FAIL] {file} 不存在")
            all_exist = False
    
    return all_exist

def check_healthchecks():
    """检查健康检查配置（使用 Docker Compose 验证）"""
    safe_print("\n[8/9] 检查健康检查配置...")
    
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        return False
    
    # 使用 Docker Compose 实际验证配置（更可靠）
    compose_version = "v1"
    success_v2, _, _ = run_command("docker compose version", check=False)
    if success_v2:
        compose_version = "v2"
    
    if compose_version == "v1":
        cmd = "docker-compose -f docker-compose.yml config"
    else:
        cmd = "docker compose -f docker-compose.yml config"
    
    success, stdout, stderr = run_command(cmd, check=False)
    
    if not success:
        safe_print("  [WARN] Docker Compose 配置验证失败，无法检查 healthcheck")
        return False
    
    services_with_healthcheck = ["backend", "frontend", "postgres", "redis"]
    missing_healthcheck = []
    
    for service in services_with_healthcheck:
        if f"  {service}:" in stdout:
            service_start = stdout.find(f"  {service}:")
            service_end = stdout.find("\n  ", service_start + 1)
            if service_end == -1:
                service_end = min(service_start + 2000, len(stdout))
            
            service_block = stdout[service_start:service_end]
            if "healthcheck:" in service_block:
                safe_print(f"  [OK] {service} 服务有 healthcheck 配置")
            else:
                missing_healthcheck.append(service)
                safe_print(f"  [WARN] {service} 服务缺少 healthcheck 配置")
        else:
            safe_print(f"  [WARN] {service} 服务未找到")
    
    if missing_healthcheck:
        safe_print(f"  [WARN] 以下服务缺少 healthcheck: {', '.join(missing_healthcheck)}")
        return False
    
    return True

def check_volumes_and_networks():
    """检查 volumes 和 networks 配置"""
    safe_print("\n[9/9] 检查 Volumes 和 Networks 配置...")
    
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        return False
    
    try:
        content = compose_file.read_text(encoding='utf-8')
    except Exception as e:
        safe_print(f"  [FAIL] 无法读取 docker-compose.yml: {e}")
        return False
    
    # 检查 volumes 定义
    if "volumes:" in content and "postgres_data:" in content:
        safe_print("  [OK] Volumes 配置存在")
    else:
        safe_print("  [WARN] Volumes 配置可能不完整")
    
    # 检查 networks 定义
    if "networks:" in content and "erp_network:" in content:
        safe_print("  [OK] Networks 配置存在")
    else:
        safe_print("  [WARN] Networks 配置可能不完整")
    
    return True

def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("西虹ERP系统 - Docker 化验证")
    safe_print("=" * 80)
    
    # 检查 Docker 环境
    docker_ok, compose_version = check_docker_installed()
    if not docker_ok:
        safe_print("\n[错误] Docker 环境检查失败，请先安装 Docker")
        sys.exit(1)
    
    if not check_docker_running():
        safe_print("\n[错误] Docker 服务未运行，请启动 Docker")
        sys.exit(1)
    
    # 检查配置文件
    config_ok = check_config_files(compose_version)
    
    # 检查 Dockerfile
    dockerfile_ok = check_dockerfiles()
    
    # 检查 profiles
    profiles_ok = check_profiles()
    prod_profiles_ok = check_prod_profiles()
    
    # 检查构建文件
    build_ok = check_build_files()
    
    # 检查健康检查
    healthcheck_ok = check_healthchecks()
    
    # 检查 volumes 和 networks
    volumes_ok = check_volumes_and_networks()
    
    # 总结
    safe_print("\n" + "=" * 80)
    safe_print("验证总结")
    safe_print("=" * 80)
    
    checks = {
        "Docker 环境": docker_ok,
        "配置文件": config_ok,
        "Dockerfile": dockerfile_ok,
        "Profiles (docker-compose.yml)": profiles_ok,
        "Profiles (docker-compose.prod.yml)": prod_profiles_ok,
        "构建文件": build_ok,
        "健康检查": healthcheck_ok,
        "Volumes/Networks": volumes_ok,
    }
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    for name, result in checks.items():
        status = "[OK]" if result else "[WARN]"
        safe_print(f"  {status} {name}")
    
    safe_print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        safe_print("\n[成功] 所有检查通过！Docker 化配置完整。")
    else:
        safe_print("\n[警告] 部分检查未通过，请修复后重新验证。")
    
    safe_print("\n" + "=" * 80)
    safe_print("下一步建议")
    safe_print("=" * 80)
    safe_print("\n如果所有检查通过，可以尝试启动服务：")
    if compose_version == "v1":
        safe_print("  docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d")
    else:
        safe_print("  docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d")
    safe_print("\n检查服务状态：")
    if compose_version == "v1":
        safe_print("  docker-compose ps")
    else:
        safe_print("  docker compose ps")
    safe_print("\n查看服务日志：")
    if compose_version == "v1":
        safe_print("  docker-compose logs -f")
    else:
        safe_print("  docker compose logs -f")
    safe_print("=" * 80)

if __name__ == "__main__":
    main()
