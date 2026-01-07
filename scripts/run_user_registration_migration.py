#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行用户注册和审批功能的数据库迁移
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from backend.utils.config import get_settings

def safe_print(text_str: str):
    """安全打印（处理Windows编码问题）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def run_migration():
    """运行数据库迁移"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        # 读取alembic.ini文件（使用UTF-8编码）
        alembic_ini_path = project_root / "alembic.ini"
        alembic_cfg = Config()
        with open(alembic_ini_path, 'r', encoding='utf-8') as f:
            alembic_cfg.file_config.read_file(f)
        
        alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        
        # 检查当前数据库版本
        from alembic.runtime.migration import MigrationContext
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            safe_print(f"[*] 当前数据库版本: {current_rev}")
        
        safe_print("[*] 开始运行数据库迁移...")
        command.upgrade(alembic_cfg, "head")
        safe_print("[OK] 数据库迁移完成")
        
        return True
        
    except Exception as e:
        safe_print(f"[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_migration():
    """验证迁移结果"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        inspector = inspect(engine)
        
        safe_print("\n" + "="*60)
        safe_print("验证迁移结果")
        safe_print("="*60)
        
        # 检查 dim_users 表的字段
        if not inspector.has_table('dim_users'):
            safe_print("[ERROR] dim_users 表不存在")
            return False
        
        columns = [col['name'] for col in inspector.get_columns('dim_users')]
        required_fields = ['status', 'approved_at', 'approved_by', 'rejection_reason']
        
        safe_print("\n[检查] dim_users 表字段:")
        all_exist = True
        for field in required_fields:
            exists = field in columns
            status = "[OK]" if exists else "[ERROR]"
            safe_print(f"  {status} {field}: {exists}")
            if not exists:
                all_exist = False
        
        # 检查 user_approval_logs 表
        has_logs_table = inspector.has_table('user_approval_logs')
        safe_print(f"\n[检查] user_approval_logs 表存在: {has_logs_table}")
        
        # 检查数据库版本
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
            version = result.scalar()
            safe_print(f"\n[检查] 当前数据库版本: {version}")
            expected_versions = ['20260104_user_registration', '20260104_create_user_approval_logs']
            version_ok = any(v in str(version) for v in expected_versions) if version else False
            safe_print(f"  [{'OK' if version_ok else 'WARNING'}] 版本检查")
        
        safe_print("\n" + "="*60)
        if all_exist and has_logs_table:
            safe_print("[OK] 所有迁移验证通过！")
            return True
        else:
            safe_print("[ERROR] 部分迁移验证失败")
            return False
        
    except Exception as e:
        safe_print(f"[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    safe_print("="*60)
    safe_print("用户注册和审批功能 - 数据库迁移")
    safe_print("="*60)
    
    # 运行迁移
    if not run_migration():
        sys.exit(1)
    
    # 验证迁移
    if not verify_migration():
        sys.exit(1)
    
    safe_print("\n[SUCCESS] 迁移和验证完成！")

if __name__ == "__main__":
    main()

