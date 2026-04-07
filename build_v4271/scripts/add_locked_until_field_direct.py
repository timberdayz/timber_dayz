#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接添加 locked_until 字段到数据库

用于账户锁定机制
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy import create_engine, text, inspect
from backend.utils.config import get_settings

def safe_print(msg):
    """安全打印（避免Windows编码错误）"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))

def add_locked_until_field():
    """添加 locked_until 字段"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        trans = conn.begin()
        
        try:
            safe_print("[*] 检查 locked_until 字段...")
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('dim_users')]
            
            if 'locked_until' in columns:
                safe_print("[OK] locked_until 字段已存在，跳过添加")
                trans.rollback()
                return True
            
            safe_print("[*] 添加 locked_until 字段...")
            conn.execute(text("""
                ALTER TABLE dim_users
                ADD COLUMN locked_until TIMESTAMP NULL
            """))
            
            safe_print("[*] 添加字段注释...")
            conn.execute(text("""
                COMMENT ON COLUMN dim_users.locked_until IS '账户锁定到期时间'
            """))
            
            safe_print("[*] 创建索引...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_locked_until
                ON dim_users(locked_until)
            """))
            
            trans.commit()
            safe_print("[OK] locked_until 字段添加成功")
            return True
            
        except Exception as e:
            trans.rollback()
            safe_print(f"[ERROR] 添加字段失败: {e}")
            return False
        finally:
            conn.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 数据库连接失败: {e}")
        return False

def verify():
    """验证迁移结果"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('dim_users')]
        
        safe_print("=" * 60)
        safe_print("验证迁移结果")
        safe_print("=" * 60)
        safe_print(f"  [OK] locked_until: {'locked_until' in columns}")
        safe_print("=" * 60)
        
        if 'locked_until' in columns:
            safe_print("[OK] 迁移验证通过")
            return True
        else:
            safe_print("[ERROR] 迁移验证失败")
            return False
            
    except Exception as e:
        safe_print(f"[ERROR] 验证失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("账户锁定字段 - 数据库迁移（直接SQL方式）")
    print("=" * 60)
    
    if add_locked_until_field():
        if verify():
            print("\n[SUCCESS] 迁移完成")
            sys.exit(0)
        else:
            print("\n[ERROR] 验证失败")
            sys.exit(1)
    else:
        print("\n[ERROR] 迁移失败")
        sys.exit(1)

