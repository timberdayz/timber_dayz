#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接执行SQL添加用户注册和审批字段
（由于Alembic迁移链问题，使用直接SQL方式）
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings

def safe_print(text_str: str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def add_fields():
    """添加字段到dim_users表"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        trans = conn.begin()
        
        try:
            safe_print("[*] 添加status字段...")
            conn.execute(text("""
                ALTER TABLE dim_users 
                ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'
            """))
            
            safe_print("[*] 添加approved_at字段...")
            conn.execute(text("""
                ALTER TABLE dim_users 
                ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP
            """))
            
            safe_print("[*] 添加approved_by字段...")
            conn.execute(text("""
                ALTER TABLE dim_users 
                ADD COLUMN IF NOT EXISTS approved_by BIGINT
            """))
            
            safe_print("[*] 添加rejection_reason字段...")
            conn.execute(text("""
                ALTER TABLE dim_users 
                ADD COLUMN IF NOT EXISTS rejection_reason TEXT
            """))
            
            safe_print("[*] 创建索引...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_status ON dim_users(status)
            """))
            
            safe_print("[*] 创建外键约束...")
            # 先删除可能存在的约束
            conn.execute(text("""
                ALTER TABLE dim_users 
                DROP CONSTRAINT IF EXISTS fk_users_approved_by
            """))
            conn.execute(text("""
                ALTER TABLE dim_users 
                ADD CONSTRAINT fk_users_approved_by 
                FOREIGN KEY (approved_by) REFERENCES dim_users(user_id) ON DELETE SET NULL
            """))
            
            safe_print("[*] 更新现有用户数据...")
            conn.execute(text("""
                UPDATE dim_users 
                SET status = 'active' 
                WHERE status IS NULL OR status = ''
            """))
            
            conn.execute(text("""
                UPDATE dim_users 
                SET is_active = (status = 'active')
            """))
            
            trans.commit()
            safe_print("[OK] 字段添加成功")
            return True
            
        except Exception as e:
            trans.rollback()
            safe_print(f"[ERROR] 添加字段失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            conn.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 数据库连接失败: {e}")
        return False

def add_trigger():
    """添加状态同步触发器"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        trans = conn.begin()
        
        try:
            safe_print("[*] 创建触发器函数...")
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION sync_user_status()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.status = 'active' THEN
                        NEW.is_active = true;
                    ELSE
                        NEW.is_active = false;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            safe_print("[*] 创建触发器...")
            conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_sync_user_status ON dim_users
            """))
            conn.execute(text("""
                CREATE TRIGGER trigger_sync_user_status
                BEFORE INSERT OR UPDATE ON dim_users
                FOR EACH ROW
                EXECUTE FUNCTION sync_user_status();
            """))
            
            trans.commit()
            safe_print("[OK] 触发器创建成功")
            return True
            
        except Exception as e:
            trans.rollback()
            safe_print(f"[ERROR] 创建触发器失败: {e}")
            return False
        finally:
            conn.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 数据库连接失败: {e}")
        return False

def ensure_operator_role():
    """确保operator角色存在"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        trans = conn.begin()
        
        try:
            safe_print("[*] 确保operator角色存在...")
            conn.execute(text("""
                INSERT INTO dim_roles (role_code, role_name, description, is_active, permissions, data_scope, is_system)
                SELECT 
                    'operator',
                    '运营人员',
                    '默认运营角色，用于新用户审批',
                    true,
                    '[]'::jsonb,
                    'all',
                    false
                WHERE NOT EXISTS (
                    SELECT 1 FROM dim_roles WHERE role_code = 'operator'
                )
            """))
            
            trans.commit()
            safe_print("[OK] operator角色确保成功")
            return True
            
        except Exception as e:
            trans.rollback()
            safe_print(f"[ERROR] 确保operator角色失败: {e}")
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
        from sqlalchemy import inspect
        
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('dim_users')]
        required_fields = ['status', 'approved_at', 'approved_by', 'rejection_reason']
        
        safe_print("\n" + "="*60)
        safe_print("验证迁移结果")
        safe_print("="*60)
        
        all_exist = True
        for field in required_fields:
            exists = field in columns
            status = "[OK]" if exists else "[ERROR]"
            safe_print(f"  {status} {field}: {exists}")
            if not exists:
                all_exist = False
        
        # 检查表
        tables = inspector.get_table_names()
        has_logs = 'user_approval_logs' in tables
        safe_print(f"\n[检查] user_approval_logs表存在: {has_logs}")
        
        safe_print("\n" + "="*60)
        if all_exist and has_logs:
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
    safe_print("用户注册和审批功能 - 数据库迁移（直接SQL）")
    safe_print("="*60)
    
    # 添加字段
    if not add_fields():
        sys.exit(1)
    
    # 添加触发器
    if not add_trigger():
        sys.exit(1)
    
    # 确保operator角色
    if not ensure_operator_role():
        sys.exit(1)
    
    # 验证
    if not verify():
        sys.exit(1)
    
    safe_print("\n[SUCCESS] 迁移完成！")

if __name__ == "__main__":
    main()

