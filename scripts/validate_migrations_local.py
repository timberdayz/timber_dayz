#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
本地迁移验证脚本

功能：
1. 启动临时 PostgreSQL 容器
2. 执行所有迁移
3. 验证迁移是否成功
4. 清理临时容器

使用方法:
    python scripts/validate_migrations_local.py
    python scripts/validate_migrations_local.py --skip-cleanup  # 保留容器用于调试
"""

import subprocess
import sys
import time
import os
from pathlib import Path
import argparse


def safe_print(text: str):
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


def check_docker_available():
    """检查 Docker 是否可用"""
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def wait_for_postgres(container_name: str, user: str, db: str, max_wait: int = 30):
    """等待 PostgreSQL 容器就绪"""
    safe_print(f"[INFO] 等待 PostgreSQL 容器就绪...")
    for i in range(max_wait):
        try:
            result = subprocess.run(
                ['docker', 'exec', container_name, 'pg_isready', '-U', user, '-d', db],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                safe_print(f"[OK] PostgreSQL 已就绪 ({i+1}秒)")
                return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        if i < max_wait - 1:
            time.sleep(1)
    
    safe_print(f"[FAIL] PostgreSQL 启动超时（等待 {max_wait} 秒）")
    return False


def validate_migrations_local(skip_cleanup: bool = False):
    """在本地验证迁移脚本"""
    project_root = Path(__file__).parent.parent
    container_name = "xihong_erp_migration_test_postgres"
    
    # 检查 Docker
    if not check_docker_available():
        safe_print("[ERROR] Docker 不可用，请先安装 Docker")
        sys.exit(1)
    
    # 清理可能存在的旧容器
    safe_print(f"[INFO] 清理可能存在的旧容器: {container_name}")
    subprocess.run(
        ['docker', 'stop', container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    subprocess.run(
        ['docker', 'rm', container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    try:
        # 1. 启动临时 PostgreSQL 容器
        safe_print(f"[INFO] 启动临时 PostgreSQL 容器: {container_name}")
        result = subprocess.run([
            'docker', 'run', '-d', '--rm',
            '--name', container_name,
            '-e', 'POSTGRES_USER=migration_test_user',
            '-e', 'POSTGRES_PASSWORD=migration_test_pass',
            '-e', 'POSTGRES_DB=migration_test_db',
            '-p', '5434:5432',  # 使用 5434 端口，避免与本地 PostgreSQL 冲突
            'postgres:15'
        ], capture_output=True, text=True, check=True)
        
        container_id = result.stdout.strip()
        safe_print(f"[OK] PostgreSQL 容器已启动: {container_id[:12]}")
        
        # 2. 等待数据库就绪
        if not wait_for_postgres(container_name, 'migration_test_user', 'migration_test_db'):
            safe_print("[ERROR] 数据库启动失败")
            return False
        
        # 3. 设置环境变量
        env = os.environ.copy()
        env['DATABASE_URL'] = 'postgresql://migration_test_user:migration_test_pass@localhost:5434/migration_test_db'
        
        # 4. 执行迁移
        safe_print("[INFO] 执行数据库迁移...")
        result = subprocess.run(
            ['alembic', 'upgrade', 'heads'],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            safe_print("[FAIL] 迁移执行失败")
            safe_print("\n标准输出:")
            safe_print(result.stdout)
            safe_print("\n标准错误:")
            safe_print(result.stderr)
            return False
        
        safe_print("[OK] 迁移执行成功")
        
        # 5. 验证表数量
        safe_print("[INFO] 验证表结构...")
        result = subprocess.run([
            'docker', 'exec', container_name,
            'psql', '-U', 'migration_test_user', '-d', 'migration_test_db',
            '-t', '-c', "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
        ], capture_output=True, text=True, check=True)
        
        table_count = int(result.stdout.strip())
        safe_print(f"[INFO] 创建了 {table_count} 张表")
        
        if table_count < 50:
            safe_print(f"[WARNING] 表数量过少（期望至少 50 张，实际 {table_count} 张）")
        else:
            safe_print(f"[OK] 表数量正常（{table_count} 张）")
        
        # 6. 验证关键表是否存在
        key_tables = ['dim_products', 'bridge_product_keys', 'fact_product_metrics', 'dim_product_master']
        safe_print("[INFO] 验证关键表是否存在...")
        for table_name in key_tables:
            result = subprocess.run([
                'docker', 'exec', container_name,
                'psql', '-U', 'migration_test_user', '-d', 'migration_test_db',
                '-t', '-c', f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema='public' AND table_name='{table_name}')"
            ], capture_output=True, text=True, check=True)
            
            exists = result.stdout.strip() == 't'
            if exists:
                safe_print(f"  [OK] 表 {table_name} 存在")
            else:
                safe_print(f"  [FAIL] 表 {table_name} 不存在")
                return False
        
        safe_print("\n[OK] 本地迁移验证通过！")
        return True
        
    except subprocess.CalledProcessError as e:
        safe_print(f"[ERROR] 命令执行失败: {e}")
        if e.stderr:
            safe_print(f"错误输出: {e.stderr}")
        return False
    except KeyboardInterrupt:
        safe_print("\n[WARNING] 用户中断，正在清理...")
        return False
    finally:
        # 清理临时容器
        if not skip_cleanup:
            safe_print(f"\n[INFO] 清理临时容器: {container_name}")
            subprocess.run(
                ['docker', 'stop', container_name],
                capture_output=True,
                stderr=subprocess.DEVNULL
            )
            safe_print("[OK] 临时容器已清理")
        else:
            safe_print(f"\n[INFO] 保留临时容器用于调试: {container_name}")
            safe_print(f"[INFO] 数据库连接: postgresql://migration_test_user:migration_test_pass@localhost:5434/migration_test_db")
            safe_print(f"[INFO] 手动清理: docker stop {container_name}")


def main():
    parser = argparse.ArgumentParser(description="本地迁移验证脚本")
    parser.add_argument(
        '--skip-cleanup',
        action='store_true',
        help='保留临时容器用于调试（不自动清理）'
    )
    
    args = parser.parse_args()
    
    success = validate_migrations_local(skip_cleanup=args.skip_cleanup)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
