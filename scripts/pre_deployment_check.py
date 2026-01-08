#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署前检查脚本
自动检查所有部署前必需项，确保部署顺利
"""

import os
import sys
import subprocess
from pathlib import Path
import socket
import urllib.request
import urllib.error
import re

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def check_file_exists(file_path, description):
    """检查文件是否存在"""
    path = Path(file_path)
    if path.exists():
        safe_print(f"  [OK] {description}: {file_path}")
        return True
    else:
        safe_print(f"  [FAIL] {description}: {file_path} (文件不存在)")
        return False

def check_env_file():
    """检查.env.production文件"""
    safe_print("\n" + "="*60)
    safe_print("1. 配置文件检查")
    safe_print("="*60)
    
    env_file = Path(__file__).parent.parent / ".env.production"
    if not env_file.exists():
        safe_print("  [FAIL] .env.production 文件不存在")
        safe_print("  建议: 运行 python scripts/generate_complete_env.py 生成配置文件")
        return False
    
    # 读取配置文件
    try:
        content = env_file.read_text(encoding='utf-8')
    except Exception as e:
        safe_print(f"  [FAIL] 无法读取配置文件: {e}")
        return False
    
    # 检查必需配置
    required_configs = {
        'ENVIRONMENT': 'production',
        'APP_ENV': 'production',
        'HOST': '0.0.0.0',
        'VITE_API_BASE_URL': '/api',
    }
    
    all_ok = True
    for key, expected_value in required_configs.items():
        if f"{key}={expected_value}" in content:
            safe_print(f"  [OK] {key}={expected_value}")
        else:
            safe_print(f"  [FAIL] {key} 配置不正确（期望: {expected_value}）")
            all_ok = False
    
    # 检查密码配置
    password_configs = ['POSTGRES_PASSWORD', 'SECRET_KEY', 'JWT_SECRET_KEY', 'REDIS_PASSWORD']
    weak_passwords = [
        'erp_pass_2025',
        'xihong-erp-secret-key-2025',
        'xihong-erp-jwt-secret-2025',
        'YOUR_SECURE_PASSWORD_HERE',
        'YOUR_SECRET_KEY_CHANGE_THIS',
        'YOUR_REDIS_PASSWORD_HERE',
    ]
    
    for key in password_configs:
        if f"{key}=" in content:
            # 检查是否为默认值
            lines = content.split('\n')
            for line in lines:
                if line.startswith(f"{key}="):
                    value = line.split('=', 1)[1].strip()
                    if not value or any(weak in value for weak in weak_passwords):
                        safe_print(f"  [FAIL] {key} 使用默认值或未配置")
                        all_ok = False
                    else:
                        safe_print(f"  [OK] {key} 已配置（已掩码显示）")
                    break
    
    # 检查服务器配置（不能包含占位符）
    server_configs = ['ALLOWED_ORIGINS', 'ALLOWED_HOSTS']
    for key in server_configs:
        if f"{key}=" in content:
            for line in content.split('\n'):
                if line.startswith(f"{key}="):
                    value = line.split('=', 1)[1].strip()
                    if 'YOUR_SERVER_IP' in value or 'your-domain.com' in value:
                        safe_print(f"  [FAIL] {key} 包含占位符，需要修改为实际值")
                        all_ok = False
                    else:
                        safe_print(f"  [OK] {key} 已配置")
                    break
    
    return all_ok

def check_docker_compose_files():
    """检查Docker Compose配置文件"""
    safe_print("\n" + "="*60)
    safe_print("2. Docker Compose配置检查")
    safe_print("="*60)
    
    project_root = Path(__file__).parent.parent
    required_files = [
        ('docker-compose.yml', '基础配置'),
        ('docker-compose.prod.yml', '生产环境配置'),
        ('docker-compose.cloud.yml', '云服务器优化配置'),
    ]
    
    all_ok = True
    for filename, description in required_files:
        file_path = project_root / filename
        if file_path.exists():
            safe_print(f"  [OK] {description}: {filename}")
        else:
            safe_print(f"  [FAIL] {description}: {filename} (文件不存在)")
            all_ok = False
    
    # 验证Docker Compose配置语法（使用profile）
    if all_ok:
        try:
            # 使用production profile检查配置
            result = subprocess.run(
                ['docker-compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.prod.yml', '-f', 'docker-compose.cloud.yml', '--profile', 'production', 'config'],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
                env=os.environ.copy()  # 使用当前环境变量
            )
            if result.returncode == 0:
                safe_print("  [OK] Docker Compose配置语法正确")
            else:
                # 检查是否是环境变量缺失的警告（可接受）
                error_output = result.stderr or result.stdout or ""
                if "depends on undefined service" in error_output:
                    safe_print(f"  [FAIL] Docker Compose配置语法错误")
                    error_msg = error_output[:300]
                    safe_print(f"  错误: {error_msg}")
                    safe_print("  [提示] 可能原因: 服务依赖关系配置错误")
                    all_ok = False
                elif "variable is not set" in error_output:
                    safe_print("  [WARN] Docker Compose配置有警告（环境变量未设置）")
                    safe_print("  [提示] 这是正常的，部署时会从.env文件读取")
                else:
                    safe_print(f"  [WARN] Docker Compose配置检查失败")
                    if error_output:
                        error_msg = error_output[:200]
                        safe_print(f"  错误: {error_msg}")
        except FileNotFoundError:
            safe_print("  [WARN] docker-compose 命令未找到（跳过语法检查）")
        except subprocess.TimeoutExpired:
            safe_print("  [WARN] Docker Compose配置检查超时")
        except Exception as e:
            safe_print(f"  [WARN] Docker Compose配置检查失败: {e}")
    
    return all_ok

def check_github_secrets():
    """检查GitHub Secrets配置（提示）"""
    safe_print("\n" + "="*60)
    safe_print("3. GitHub配置检查")
    safe_print("="*60)
    
    safe_print("  [INFO] 请在GitHub仓库中检查以下Secrets:")
    safe_print("    位置: Settings > Secrets and variables > Actions")
    safe_print("    仓库: https://github.com/timberdayz/timber_dayz")
    safe_print("")
    safe_print("  必需Secrets:")
    safe_print("    - PRODUCTION_SSH_PRIVATE_KEY")
    safe_print("    - PRODUCTION_HOST")
    safe_print("    - PRODUCTION_USER (可选，默认: root)")
    safe_print("    - PRODUCTION_PATH (可选，默认: /opt/xihong_erp)")
    safe_print("")
    safe_print("  [提示] 无法自动检查，请手动确认")
    
    return True  # 无法自动检查，返回True

def check_docker_images():
    """检查Docker镜像"""
    safe_print("\n" + "="*60)
    safe_print("4. 镜像仓库检查")
    safe_print("="*60)
    
    # 获取仓库信息
    try:
        result = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+/[^/]+)\.git", url)
            if match:
                repo_name = match.group(1)
                backend_image = f"ghcr.io/{repo_name}/backend:latest"
                frontend_image = f"ghcr.io/{repo_name}/frontend:latest"
                
                safe_print(f"  [INFO] 仓库: {repo_name}")
                safe_print(f"  [INFO] 后端镜像: {backend_image}")
                safe_print(f"  [INFO] 前端镜像: {frontend_image}")
                safe_print("")
                safe_print("  [提示] 请在服务器上测试镜像拉取:")
                safe_print(f"    docker pull {backend_image}")
                safe_print(f"    docker pull {frontend_image}")
                
                return True
    except Exception as e:
        safe_print(f"  [WARN] 无法获取仓库信息: {e}")
    
    return True

def check_network_config():
    """检查网络配置"""
    safe_print("\n" + "="*60)
    safe_print("5. 网络配置检查")
    safe_print("="*60)
    
    # 检查.env.production中的网络配置
    env_file = Path(__file__).parent.parent / ".env.production"
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        
        # 检查ALLOWED_ORIGINS
        if 'ALLOWED_ORIGINS=' in content:
            for line in content.split('\n'):
                if line.startswith('ALLOWED_ORIGINS='):
                    value = line.split('=', 1)[1].strip()
                    if 'YOUR_SERVER_IP' in value or 'your-domain.com' in value:
                        safe_print("  [FAIL] ALLOWED_ORIGINS 包含占位符")
                        return False
                    elif '*' in value:
                        safe_print("  [FAIL] ALLOWED_ORIGINS 包含 * (不安全)")
                        return False
                    else:
                        safe_print(f"  [OK] ALLOWED_ORIGINS: {value[:60]}...")
                    break
        
        # 检查ALLOWED_HOSTS
        if 'ALLOWED_HOSTS=' in content:
            for line in content.split('\n'):
                if line.startswith('ALLOWED_HOSTS='):
                    value = line.split('=', 1)[1].strip()
                    if 'YOUR_SERVER_IP' in value or 'your-domain.com' in value:
                        safe_print("  [FAIL] ALLOWED_HOSTS 包含占位符")
                        return False
                    else:
                        safe_print(f"  [OK] ALLOWED_HOSTS: {value}")
                    break
        
        # 检查VITE_API_BASE_URL
        if 'VITE_API_BASE_URL=/api' in content:
            safe_print("  [OK] VITE_API_BASE_URL=/api (Nginx反向代理模式)")
        else:
            safe_print("  [WARN] VITE_API_BASE_URL 可能未配置为 /api")
    
    return True

def check_nginx_config():
    """检查Nginx配置"""
    safe_print("\n" + "="*60)
    safe_print("6. Nginx配置检查")
    safe_print("="*60)
    
    nginx_file = Path(__file__).parent.parent / "nginx" / "nginx.prod.conf"
    if not nginx_file.exists():
        safe_print("  [FAIL] nginx/nginx.prod.conf 文件不存在")
        return False
    
    content = nginx_file.read_text(encoding='utf-8')
    
    # 检查API代理配置
    if 'location /api/' in content and 'proxy_pass http://backend' in content:
        safe_print("  [OK] /api/ 路径代理到 backend")
    else:
        safe_print("  [FAIL] /api/ 路径代理配置不正确")
        return False
    
    # 检查前端代理配置
    if 'location /' in content and 'proxy_pass http://frontend' in content:
        safe_print("  [OK] / 路径代理到 frontend")
    else:
        safe_print("  [WARN] / 路径代理配置可能不正确")
    
    return True

def check_security_config():
    """检查安全配置"""
    safe_print("\n" + "="*60)
    safe_print("7. 安全配置检查")
    safe_print("="*60)
    
    env_file = Path(__file__).parent.parent / ".env.production"
    if not env_file.exists():
        return False
    
    content = env_file.read_text(encoding='utf-8')
    
    # 检查是否使用默认密码
    weak_passwords = [
        'erp_pass_2025',
        'xihong-erp-secret-key-2025',
        'xihong-erp-jwt-secret-2025',
        'YOUR_SECURE_PASSWORD_HERE',
        'YOUR_SECRET_KEY_CHANGE_THIS',
        'YOUR_REDIS_PASSWORD_HERE',
    ]
    
    all_ok = True
    for weak_pwd in weak_passwords:
        if weak_pwd in content:
            safe_print(f"  [FAIL] 检测到弱密码或默认值: {weak_pwd}")
            all_ok = False
    
    if all_ok:
        safe_print("  [OK] 未检测到默认密码或弱密码")
    
    # 检查CORS配置
    if 'ALLOWED_ORIGINS=*' in content:
        safe_print("  [FAIL] ALLOWED_ORIGINS 包含 * (不安全)")
        all_ok = False
    else:
        safe_print("  [OK] ALLOWED_ORIGINS 配置安全")
    
    return all_ok

def check_resources():
    """检查资源限制配置"""
    safe_print("\n" + "="*60)
    safe_print("8. 资源限制检查")
    safe_print("="*60)
    
    cloud_file = Path(__file__).parent.parent / "docker-compose.cloud.yml"
    if cloud_file.exists():
        safe_print("  [OK] docker-compose.cloud.yml 存在（2核4G优化配置）")
        
        content = cloud_file.read_text(encoding='utf-8')
        if 'cpus: \'1.0\'' in content or 'DB_POOL_SIZE=10' in content:
            safe_print("  [OK] 资源限制已优化（2核4G）")
        else:
            safe_print("  [WARN] 资源限制可能未优化")
    else:
        safe_print("  [WARN] docker-compose.cloud.yml 不存在（建议使用）")
    
    return True

def check_frontend_config():
    """检查前端配置"""
    safe_print("\n" + "="*60)
    safe_print("9. 前端配置检查")
    safe_print("="*60)
    
    # 检查Dockerfile
    dockerfile = Path(__file__).parent.parent / "frontend" / "Dockerfile.prod"
    if dockerfile.exists():
        content = dockerfile.read_text(encoding='utf-8')
        if 'VITE_API_BASE_URL' in content:
            safe_print("  [OK] frontend/Dockerfile.prod 包含 VITE_API_BASE_URL")
        else:
            safe_print("  [WARN] frontend/Dockerfile.prod 可能未包含 VITE_API_BASE_URL")
    else:
        safe_print("  [FAIL] frontend/Dockerfile.prod 不存在")
        return False
    
    # 检查.env.production
    env_file = Path(__file__).parent.parent / ".env.production"
    if env_file.exists():
        content = env_file.read_text(encoding='utf-8')
        if 'VITE_API_BASE_URL=/api' in content:
            safe_print("  [OK] VITE_API_BASE_URL=/api (Nginx反向代理模式)")
        else:
            safe_print("  [WARN] VITE_API_BASE_URL 可能未配置为 /api")
    
    return True

def main():
    """主函数"""
    safe_print("="*60)
    safe_print("部署前检查工具")
    safe_print("="*60)
    safe_print("版本: v4.19.7")
    safe_print("适用: 腾讯云2核4G Linux服务器")
    safe_print("="*60)
    
    checks = [
        ("配置文件", check_env_file),
        ("Docker Compose配置", check_docker_compose_files),
        ("GitHub配置", check_github_secrets),
        ("镜像仓库", check_docker_images),
        ("网络配置", check_network_config),
        ("Nginx配置", check_nginx_config),
        ("安全配置", check_security_config),
        ("资源限制", check_resources),
        ("前端配置", check_frontend_config),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            safe_print(f"\n[ERROR] {name} 检查失败: {e}")
            results[name] = False
    
    # 总结
    safe_print("\n" + "="*60)
    safe_print("检查结果总结")
    safe_print("="*60)
    
    all_ok = True
    critical_checks = ['配置文件', 'Docker Compose配置', '安全配置', '网络配置', 'Nginx配置']
    
    for name, result in results.items():
        if result:
            status = "[OK]"
            if name in critical_checks:
                status = "[OK] [P0]"
            safe_print(f"  {status} {name}: 通过")
        else:
            status = "[FAIL]"
            if name in critical_checks:
                status = "[FAIL] [P0]"
            safe_print(f"  {status} {name}: 未通过")
            all_ok = False
    
    safe_print("\n" + "="*60)
    if all_ok:
        safe_print("[OK] 所有检查通过，可以开始部署！")
        safe_print("\n[下一步]")
        safe_print("  1. 上传配置文件到服务器: scp .env.production user@134.175.222.171:/opt/xihong_erp/.env")
        safe_print("  2. 在服务器上验证配置")
        safe_print("  3. 使用GitHub Actions或手动部署")
    else:
        safe_print("[FAIL] 部分检查未通过，请修复后重新检查")
        safe_print("\n[建议]")
        safe_print("  1. 修复所有[FAIL]项（特别是[P0]级别）")
        safe_print("  2. 重新运行检查脚本: python scripts/pre_deployment_check.py")
        safe_print("  3. 确认所有配置正确后再部署")
    
    safe_print("="*60)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        safe_print("\n\n[退出] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        safe_print(f"\n[ERROR] 检查失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
