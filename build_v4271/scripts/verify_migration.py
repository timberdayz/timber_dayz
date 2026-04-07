#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证迁移后的系统状态

检查：
1. fact_orders 和 fact_order_items 表是否已删除
2. 系统是否可以正常导入
3. target_breakdown 表状态
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_tables_deleted(engine):
    """检查 fact_orders 和 fact_order_items 表是否已删除"""
    print("\n" + "="*60)
    print("验证1: 检查 fact_orders 和 fact_order_items 表是否已删除")
    print("="*60)
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('fact_orders', 'fact_order_items')
        """))
        tables = [row[0] for row in result]
        
        if tables:
            print(f"[WARNING] 以下表仍然存在: {', '.join(tables)}")
            return False
        else:
            print("[OK] fact_orders 和 fact_order_items 表已成功删除")
            return True


def check_system_import():
    """检查系统是否可以正常导入"""
    print("\n" + "="*60)
    print("验证2: 检查系统是否可以正常导入")
    print("="*60)
    
    try:
        from backend.main import app
        print("[OK] 后端可以正常导入，没有 ImportError")
        return True
    except ImportError as e:
        print(f"[ERROR] 导入失败: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 其他错误: {e}")
        return False


def check_target_breakdown(engine):
    """检查 target_breakdown 表状态"""
    print("\n" + "="*60)
    print("验证3: 检查 target_breakdown 表状态")
    print("="*60)
    
    with engine.connect() as conn:
        # 检查表是否存在
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'target_breakdown'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            print("[WARNING] target_breakdown 表不存在")
            return False
        
        # 检查记录数
        result = conn.execute(text("SELECT COUNT(*) FROM target_breakdown"))
        count = result.scalar()
        print(f"[INFO] target_breakdown 表记录数: {count}")
        
        # 检查示例数据
        if count > 0:
            result = conn.execute(text("""
                SELECT platform_code, shop_id, breakdown_type 
                FROM target_breakdown 
                LIMIT 5
            """))
            rows = result.fetchall()
            print("[INFO] 示例数据:")
            for row in rows:
                print(f"  platform_code={row[0]}, shop_id={row[1]}, type={row[2]}")
        else:
            print("[INFO] 表为空，可以测试创建分解数据")
        
        return True


def main():
    """主函数"""
    try:
        settings = get_settings()
        database_url = settings.DATABASE_URL
        
        print("="*60)
        print("数据库迁移验证")
        print("="*60)
        print(f"数据库: {database_url.split('@')[-1] if '@' in database_url else 'SQLite'}")
        
        engine = create_engine(database_url)
        
        # 验证1: 检查表是否删除
        tables_deleted = check_tables_deleted(engine)
        
        # 验证2: 检查系统导入
        import_ok = check_system_import()
        
        # 验证3: 检查 target_breakdown
        breakdown_ok = check_target_breakdown(engine)
        
        # 总结
        print("\n" + "="*60)
        print("验证总结")
        print("="*60)
        print(f"表删除状态: {'[OK]' if tables_deleted else '[FAIL]'}")
        print(f"系统导入: {'[OK]' if import_ok else '[FAIL]'}")
        print(f"分解表状态: {'[OK]' if breakdown_ok else '[FAIL]'}")
        
        if tables_deleted and import_ok and breakdown_ok:
            print("\n[SUCCESS] 所有验证通过！")
            return 0
        else:
            print("\n[WARNING] 部分验证失败，请检查上述错误")
            return 1
        
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
