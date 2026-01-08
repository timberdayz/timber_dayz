#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成完整的生产环境.env配置文件
包含域名和IP地址配置
"""

import secrets
import sys
from pathlib import Path
from cryptography.fernet import Fernet

def generate_secret_key(length=32):
    """生成随机密钥"""
    return secrets.token_urlsafe(length)

def generate_password(length=24):
    """生成强随机密码"""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_fernet_key():
    """生成Fernet加密密钥"""
    return Fernet.generate_key().decode()

def generate_complete_env(server_ip, domain, output_file=".env.production"):
    """生成完整的生产环境配置文件"""
    
    print("\n" + "="*60)
    print("生成完整生产环境配置")
    print("="*60)
    print(f"服务器IP: {server_ip}")
    print(f"域名: {domain}")
    
    # 生成所有密码和密钥
    postgres_password = generate_password(24)
    redis_password = generate_password(16)
    secret_key = generate_secret_key(32)
    jwt_secret_key = generate_secret_key(32)
    account_encryption_key = generate_fernet_key()
    
    print("[OK] 已生成所有密码和密钥")
    
    # 构建域名列表（带www和不带www）
    domain_with_www = f"www.{domain}" if not domain.startswith("www.") else domain
    domain_without_www = domain.replace("www.", "")
    
    # 生成.env文件内容
    env_content = f"""# =====================================================
# 西虹ERP系统 - 生产环境配置（腾讯云2核4G优化）
# =====================================================
# 自动生成时间: 2025-01-XX
# 服务器IP: {server_ip}
# 域名: {domain}
# ⚠️ 重要: 此文件包含敏感信息，请妥善保管！
# =====================================================

# ==================== 环境标识（必须） ====================
ENVIRONMENT=production
APP_ENV=production
DEBUG=false

# ==================== 数据库配置 ====================
# Docker容器内使用服务名 'postgres'
DATABASE_URL=postgresql://erp_user:{postgres_password}@postgres:5432/xihong_erp
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=erp_user
POSTGRES_PASSWORD={postgres_password}
POSTGRES_DB=xihong_erp

# ==================== 安全配置 ====================
# 应用密钥（32位随机字符串）
SECRET_KEY={secret_key}
# JWT签名密钥（32位随机字符串）
JWT_SECRET_KEY={jwt_secret_key}
# 账号加密密钥（Fernet格式）
ACCOUNT_ENCRYPTION_KEY={account_encryption_key}

# ==================== 服务器配置 ====================
# 允许外部访问
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80

# CORS允许的来源（同时支持域名和IP访问）
# 包含: 带www域名、不带www域名、IP地址、HTTPS（如果已配置SSL）
ALLOWED_ORIGINS=http://{domain_with_www},http://{domain_without_www},http://{server_ip},https://{domain_with_www},https://{domain_without_www}

# 允许的主机（同时支持域名和IP）
ALLOWED_HOSTS={domain_with_www},{domain_without_www},{server_ip},localhost

# ==================== Redis配置 ====================
REDIS_URL=redis://:{redis_password}@redis:6379/0
REDIS_PASSWORD={redis_password}
CELERY_BROKER_URL=redis://:{redis_password}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:{redis_password}@redis:6379/0
REDIS_ENABLED=true

# ==================== 前端配置 ====================
# ⚠️ 重要：前端构建时使用 VITE_API_BASE_URL（不是 VITE_API_URL）
# 如果使用Nginx反向代理（推荐），使用相对路径: /api
# 如果直接访问后端，使用完整URL: http://{domain_with_www}:8000
VITE_API_BASE_URL=/api
VITE_MODE=production

# ==================== 性能优化（2核4G服务器） ====================
# 连接池大小（从默认30降到10）
DB_POOL_SIZE=10
# 连接池最大溢出（从默认60降到20）
DB_MAX_OVERFLOW=20
# 连接超时
DB_POOL_TIMEOUT=30
# 连接回收时间
DB_POOL_RECYCLE=1800

# 最大并发采集任务数（从默认5降到2）
MAX_CONCURRENT_TASKS=2

# ==================== Playwright配置 ====================
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0
PLAYWRIGHT_TIMEOUT=30000

# ==================== 日志配置 ====================
LOG_LEVEL=INFO
DATABASE_ECHO=false

# ==================== JWT Token配置 ====================
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_ALGORITHM=HS256

# ==================== 数据保留 ====================
DATA_RETENTION_DAYS=90

# ==================== 文件存储目录 ====================
PROJECT_ROOT=/app
DATA_DIR=/app/data
DATA_RAW_DIR=/app/data/raw
DOWNLOADS_DIR=/app/downloads
TEMP_DIR=/app/temp
LOGS_DIR=/app/logs

# ==================== 其他配置 ====================
PYTHON_VERSION=3.11
NODE_VERSION=18
"""
    
    # 保存配置文件
    output_path = Path(__file__).parent.parent / output_file
    output_path.write_text(env_content, encoding='utf-8')
    
    print(f"\n[OK] 配置文件已生成: {output_path}")
    
    # 保存密码到单独文件（用于参考）
    passwords_file = Path(__file__).parent.parent / ".env.production.passwords.txt"
    passwords_content = f"""# =====================================================
# 生产环境密码和密钥（仅用于参考，请妥善保管）
# =====================================================
# 生成时间: 2025-01-XX
# 服务器IP: {server_ip}
# 域名: {domain}
# ⚠️ 警告: 此文件包含敏感信息，请妥善保管！
# =====================================================

POSTGRES_PASSWORD={postgres_password}
REDIS_PASSWORD={redis_password}
SECRET_KEY={secret_key}
JWT_SECRET_KEY={jwt_secret_key}
ACCOUNT_ENCRYPTION_KEY={account_encryption_key}
"""
    passwords_file.write_text(passwords_content, encoding='utf-8')
    
    print(f"[OK] 密码文件已保存: {passwords_file}")
    print("[WARN] 请妥善保管密码文件，建议在服务器上配置后删除本地副本")
    
    return output_path, {
        'postgres_password': postgres_password,
        'redis_password': redis_password,
        'secret_key': secret_key,
        'jwt_secret_key': jwt_secret_key,
        'account_encryption_key': account_encryption_key
    }

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='生成完整生产环境.env配置文件')
    parser.add_argument('--server-ip', type=str, default='134.175.222.171', help='服务器IP地址')
    parser.add_argument('--domain', type=str, default='www.xihong.site', help='域名')
    parser.add_argument('--output', type=str, default='.env.production', help='输出文件名')
    
    args = parser.parse_args()
    
    # 清理域名（移除http://和https://前缀）
    domain = args.domain.replace('http://', '').replace('https://', '').strip('/')
    
    print("="*60)
    print("完整生产环境配置文件生成工具")
    print("="*60)
    
    # 生成配置文件
    env_file, passwords = generate_complete_env(args.server_ip, domain, args.output)
    
    # 显示摘要
    print("\n" + "="*60)
    print("配置摘要")
    print("="*60)
    print(f"服务器IP: {args.server_ip}")
    print(f"域名: {domain}")
    print(f"配置文件: {env_file}")
    print("\n[生成的密钥]")
    print(f"  POSTGRES_PASSWORD: {'*' * 24} (已生成)")
    print(f"  REDIS_PASSWORD: {'*' * 16} (已生成)")
    print(f"  SECRET_KEY: {'*' * 32} (已生成)")
    print(f"  JWT_SECRET_KEY: {'*' * 32} (已生成)")
    print(f"  ACCOUNT_ENCRYPTION_KEY: {'*' * 44} (已生成)")
    
    print("\n[配置项]")
    print(f"  ALLOWED_ORIGINS: http://{domain},http://{domain.replace('www.', '')},http://{args.server_ip},https://...")
    print(f"  ALLOWED_HOSTS: {domain},{domain.replace('www.', '')},{args.server_ip},localhost")
    print(f"  VITE_API_BASE_URL: /api (Nginx反向代理模式)")
    
    print("\n" + "="*60)
    print("下一步操作")
    print("="*60)
    print("1. 检查生成的配置文件: .env.production")
    print("2. 将配置文件上传到服务器: /opt/xihong_erp/.env")
    print("3. 在服务器上验证配置: python scripts/validate_production_env.py")
    print("4. 删除本地密码文件: .env.production.passwords.txt（可选）")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[退出] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
