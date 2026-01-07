#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
环境变量配置文件生成脚本

根据 env.template 生成不同环境的配置文件：
- env.example（通用示例）
- env.development.example（开发环境）
- env.production.example（生产环境）
- env.docker.example（Docker 环境，可选）

使用方法：
    python scripts/generate-env-files.py
    python scripts/generate-env-files.py --include-docker  # 包含 docker 配置
"""

import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_FILE = PROJECT_ROOT / "env.template"

# 环境特定配置覆盖
ENV_OVERRIDES = {
    "development": {
        "ENVIRONMENT": "development",
        "APP_ENV": "development",
        "DEBUG": "true",
        "HOST": "127.0.0.1",
        "POSTGRES_PORT_EXTERNAL": "15432",
        "POSTGRES_USER": "erp_dev",
        "POSTGRES_PASSWORD": "dev_pass_2025",
        "POSTGRES_DB": "xihong_erp_dev",
        "DATABASE_URL": "postgresql://erp_dev:dev_pass_2025@localhost:15432/xihong_erp_dev",
        "SECRET_KEY": "dev-secret-key-not-for-production",
        "JWT_SECRET_KEY": "dev-jwt-secret-not-for-production",
        "DB_POOL_SIZE": "10",
        "DB_MAX_OVERFLOW": "10",
        "DATABASE_ECHO": "true",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": "logs/backend-dev.log",
        "PLAYWRIGHT_HEADLESS": "false",
        "PLAYWRIGHT_SLOW_MO": "100",
        "VITE_MODE": "development",
        "ALLOWED_ORIGINS": "http://localhost:5173,http://localhost:5174,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:3000",
        "MAX_CONCURRENT_TASKS": "2",
        "DATA_RETENTION_DAYS": "30",
        "REDIS_ENABLED": "false",
        "PGADMIN_EMAIL": "dev@xihong.com",
        "PGADMIN_PASSWORD": "dev123",
    },
    "production": {
        "ENVIRONMENT": "production",
        "APP_ENV": "production",
        "DEBUG": "false",
        "HOST": "0.0.0.0",
        "POSTGRES_PORT_EXTERNAL": "5432",
        "POSTGRES_PASSWORD": "YOUR_SECURE_PASSWORD_HERE",
        "DATABASE_URL": "postgresql://erp_user:YOUR_SECURE_PASSWORD_HERE@postgres:5432/xihong_erp",
        "SECRET_KEY": "YOUR_SECRET_KEY_CHANGE_THIS_TO_RANDOM_STRING_AT_LEAST_32_CHARACTERS",
        "JWT_SECRET_KEY": "YOUR_JWT_SECRET_KEY_CHANGE_THIS_TO_RANDOM_STRING_AT_LEAST_32_CHARACTERS",
        "DB_POOL_SIZE": "30",
        "DB_MAX_OVERFLOW": "60",
        "DATABASE_ECHO": "false",
        "LOG_LEVEL": "INFO",
        "LOG_FILE": "logs/backend.log",
        "PLAYWRIGHT_HEADLESS": "true",
        "PLAYWRIGHT_SLOW_MO": "0",
        "VITE_MODE": "production",
        "VITE_API_URL": "https://your-domain.com/api",
        "ALLOWED_ORIGINS": "https://your-domain.com,https://www.your-domain.com",
        "ALLOWED_HOSTS": "your-domain.com,www.your-domain.com,localhost",
        "MAX_CONCURRENT_TASKS": "5",
        "DATA_RETENTION_DAYS": "90",
        "REDIS_ENABLED": "true",
        "REDIS_URL": "redis://redis:6379/0",
        "CELERY_BROKER_URL": "redis://:${REDIS_PASSWORD}@redis:6379/0",
        "CELERY_RESULT_BACKEND": "redis://:${REDIS_PASSWORD}@redis:6379/0",
        "REDIS_PASSWORD": "YOUR_REDIS_PASSWORD_HERE",
        "PGADMIN_PASSWORD": "YOUR_PGADMIN_PASSWORD_HERE",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "your-email@example.com",
        "SMTP_PASSWORD": "your-email-password",
        "SMTP_FROM": "noreply@your-domain.com",
        "ALERT_EMAIL_TO": "ops-team@your-domain.com",
        "ALERT_EMAIL_CRITICAL": "critical-alerts@your-domain.com",
        "ALERT_EMAIL_WARNING": "warning-alerts@your-domain.com",
        "ALERT_EMAIL_CELERY": "celery-alerts@your-domain.com",
        "GRAFANA_ADMIN_PASSWORD": "YOUR_GRAFANA_PASSWORD_HERE",
    },
    "docker": {
        "ENVIRONMENT": "production",
        "APP_ENV": "production",
        "DEBUG": "false",
        "HOST": "0.0.0.0",
        "POSTGRES_HOST": "postgres",
        "POSTGRES_PORT": "5432",
        "DATABASE_URL": "postgresql://erp_user:erp_pass_2025@postgres:5432/xihong_erp",
        "SECRET_KEY": "docker-secret-key-change-in-production",
        "JWT_SECRET_KEY": "docker-jwt-secret-key-change-in-production",
        "REDIS_URL": "redis://redis:6379/0",
        "VITE_API_URL": "http://backend:8000",
        "ALLOWED_ORIGINS": "http://frontend,http://localhost:5174,http://localhost:80",
        "PLAYWRIGHT_HEADLESS": "true",
        "UPLOAD_DIR": "/app/uploads",
        "TEMP_DIR": "/app/temp",
        "DATA_DIR": "/app/data",
        "DOWNLOADS_DIR": "/app/downloads",
        "PROJECT_ROOT": "/app",
    },
}


def parse_template(template_path: Path) -> List[Tuple[str, str, str]]:
    """
    解析模板文件，返回 (变量名, 值, 注释) 列表
    
    Returns:
        List[Tuple[str, str, str]]: (变量名, 值, 注释) 元组列表
    """
    if not template_path.exists():
        print(f"[ERROR] 模板文件不存在: {template_path}")
        sys.exit(1)
    
    lines = template_path.read_text(encoding='utf-8').split('\n')
    variables = []
    current_section = ""
    current_comment = []
    
    for line in lines:
        line = line.rstrip()
        
        # 跳过空行和纯注释行
        if not line or line.startswith('#'):
            if line.startswith('#') and not line.startswith('# ='):
                # 收集注释（但不包括分隔符）
                if not line.startswith('# ='):
                    current_comment.append(line)
            continue
        
        # 检查是否是分隔符
        if line.startswith('# ='):
            current_section = line
            current_comment = []
            continue
        
        # 解析变量行
        if '=' in line:
            # 提取变量名和值
            match = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', line)
            if match:
                var_name = match.group(1)
                var_value = match.group(2).rstrip()
                
                # 提取行内注释
                if '#' in var_value:
                    parts = var_value.split('#', 1)
                    var_value = parts[0].rstrip()
                    inline_comment = '#' + parts[1]
                    current_comment.append(inline_comment)
                
                # 合并注释
                comment = '\n'.join(current_comment) if current_comment else ""
                variables.append((var_name, var_value, comment))
                current_comment = []
    
    return variables


def generate_env_file(
    variables: List[Tuple[str, str, str]],
    env_type: str,
    output_path: Path,
    include_docker: bool = False
) -> None:
    """
    生成环境配置文件
    
    Args:
        variables: 变量列表
        env_type: 环境类型（development/production/docker/example）
        output_path: 输出文件路径
        include_docker: 是否包含 Docker 配置
    """
    overrides = ENV_OVERRIDES.get(env_type, {})
    
    # 生成文件头
    if env_type == "example":
        header = f"""# =====================================================
# 西虹ERP系统 - 环境变量配置模板
# =====================================================
# 复制此文件为 .env 并根据实际情况修改配置
#
# 快速开始:
# 1. 复制文件: cp env.example .env
# 2. 修改密码: 编辑 POSTGRES_PASSWORD 和 SECRET_KEY
# 3. 启动服务: python run.py --use-docker
#
# 部署模式:
# - 开发模式: python run.py --use-docker
# - 生产模式: docker-compose -f docker-compose.prod.yml up -d
# =====================================================

"""
    elif env_type == "development":
        header = f"""# =====================================================
# 西虹ERP系统 - 开发环境配置
# =====================================================
# 用于本地开发和测试
# 使用方式: cp env.development.example .env.development
# 或: python run.py --use-docker（自动使用 .env）
# =====================================================

"""
    elif env_type == "production":
        header = f"""# =====================================================
# 西虹ERP系统 - 生产环境配置
# =====================================================
# 用于生产部署
# 使用方式: cp env.production.example .env
# ⚠️ 重要: 必须修改所有密码和密钥！
# =====================================================

"""
    elif env_type == "docker":
        header = f"""# =====================================================
# 西虹ERP系统 - Docker专用配置
# =====================================================
# 用于Docker Compose部署
# 使用方式: cp env.docker.example .env
# =====================================================

"""
    else:
        header = ""
    
    lines = [header]
    current_section = ""
    
    for var_name, var_value, comment in variables:
        # 应用环境特定覆盖
        if var_name in overrides:
            var_value = overrides[var_name]
        
        # 添加注释
        if comment:
            lines.append(comment)
        
        # 添加变量行
        lines.append(f"{var_name}={var_value}")
        lines.append("")
    
    # 写入文件
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"[OK] 已生成: {output_path}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="生成环境变量配置文件")
    parser.add_argument(
        "--include-docker",
        action="store_true",
        help="包含 Docker 配置文件（env.docker.example）"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("环境变量配置文件生成工具")
    print("=" * 60)
    
    # 解析模板
    print(f"\n[1/3] 读取模板文件: {TEMPLATE_FILE}")
    variables = parse_template(TEMPLATE_FILE)
    print(f"      找到 {len(variables)} 个环境变量")
    
    # 生成配置文件
    print(f"\n[2/3] 生成配置文件...")
    
    # env.example（通用示例）
    generate_env_file(
        variables,
        "example",
        PROJECT_ROOT / "env.example"
    )
    
    # env.development.example
    generate_env_file(
        variables,
        "development",
        PROJECT_ROOT / "env.development.example"
    )
    
    # env.production.example
    generate_env_file(
        variables,
        "production",
        PROJECT_ROOT / "env.production.example"
    )
    
    # env.docker.example（可选）
    if args.include_docker:
        generate_env_file(
            variables,
            "docker",
            PROJECT_ROOT / "env.docker.example"
        )
    
    print(f"\n[3/3] 完成！")
    print("\n生成的文件:")
    print("  - env.example（通用示例）")
    print("  - env.development.example（开发环境）")
    print("  - env.production.example（生产环境）")
    if args.include_docker:
        print("  - env.docker.example（Docker 环境）")
    print("\n提示: 复制对应的 .example 文件为 .env 并根据实际情况修改")


if __name__ == "__main__":
    main()

