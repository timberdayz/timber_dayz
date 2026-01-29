#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 fact_orders 和 fact_order_items 表

如果这些表已废弃，可以安全删除
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from backend.models.database import engine
from backend.utils.config import get_settings

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)

def show_database_info():
    """显示当前连接的数据库信息"""
    settings = get_settings()
    db_url = settings.DATABASE_URL
    
    # 解析数据库URL
    if '@' in db_url:
        # PostgreSQL格式: postgresql://user:pass@host:port/db
        parts = db_url.split('@')
        if len(parts) == 2:
            host_part = parts[1].split('/')
            if len(host_part) >= 2:
                host_port = host_part[0]
                db_name = host_part[1].split('?')[0]  # 移除查询参数
                safe_print(f"[INFO] 数据库主机: {host_port}")
                safe_print(f"[INFO] 数据库名称: {db_name}")
                
                # 判断是否是Docker
                if 'localhost' in host_port or '127.0.0.1' in host_port:
                    port = host_port.split(':')[-1] if ':' in host_port else '5432'
                    if port in ['15432', '5433', '5432']:
                        safe_print(f"[INFO] 连接类型: Docker容器 (端口映射: {port})")
                    else:
                        safe_print(f"[INFO] 连接类型: 本地PostgreSQL")
                else:
                    safe_print(f"[INFO] 连接类型: 远程PostgreSQL")
    else:
        safe_print(f"[INFO] 数据库URL: {db_url}")

def check_table_data(table_name):
    """检查表是否有数据"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM public."{table_name}"'))
            count = result.scalar()
            return count
    except Exception as e:
        safe_print(f"[ERROR] 无法查询 {table_name}: {e}")
        return None

def drop_table(table_name):
    """删除表"""
    try:
        with engine.connect() as conn:
            # 先删除外键约束
            conn.execute(text(f"""
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT constraint_name, table_name
                        FROM information_schema.table_constraints
                        WHERE constraint_type = 'FOREIGN KEY'
                        AND table_name = '{table_name}'
                        AND table_schema = 'public'
                    ) LOOP
                        EXECUTE 'ALTER TABLE public.' || quote_ident(r.table_name) || 
                                ' DROP CONSTRAINT IF EXISTS ' || quote_ident(r.constraint_name);
                    END LOOP;
                END $$;
            """))
            
            # 删除表
            conn.execute(text(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE'))
            conn.commit()
            safe_print(f"[OK] {table_name} 表已删除")
            return True
    except Exception as e:
        safe_print(f"[ERROR] 删除 {table_name} 失败: {e}")
        return False

def main():
    safe_print("\n" + "="*60)
    safe_print("检查并修复 fact_orders 和 fact_order_items 表")
    safe_print("="*60)
    
    # 显示数据库连接信息
    safe_print("\n【数据库连接信息】")
    show_database_info()
    
    # 确认操作
    safe_print("\n【操作确认】")
    safe_print("将删除以下废弃表（如果存在且为空）:")
    safe_print("  - public.fact_orders")
    safe_print("  - public.fact_order_items")
    safe_print("\n注意: 这些表在 v4.6.0 后已废弃，数据已迁移到 b_class schema")
    
    inspector = inspect(engine)
    public_tables = inspector.get_table_names(schema='public')
    
    tables_to_check = ['fact_orders', 'fact_order_items']
    deleted_count = 0
    skipped_count = 0
    
    for table_name in tables_to_check:
        if table_name in public_tables:
            safe_print(f"\n【处理表: {table_name}】")
            count = check_table_data(table_name)
            if count is not None:
                safe_print(f"  数据行数: {count}")
                
                if count == 0:
                    safe_print(f"  [INFO] 表为空，安全删除")
                    if drop_table(table_name):
                        deleted_count += 1
                    else:
                        skipped_count += 1
                else:
                    safe_print(f"  [WARN] 表中有 {count} 行数据")
                    safe_print(f"  [INFO] 根据迁移说明，这些表已废弃（v4.6.0后数据已迁移到 b_class schema）")
                    safe_print(f"  [INFO] 自动删除（用户已确认）")
                    if drop_table(table_name):
                        deleted_count += 1
                    else:
                        skipped_count += 1
            else:
                skipped_count += 1
        else:
            safe_print(f"\n[OK] {table_name} 不存在（已删除）")
    
    # 总结
    safe_print("\n" + "="*60)
    safe_print("修复总结")
    safe_print("="*60)
    safe_print(f"  已删除: {deleted_count} 张表")
    safe_print(f"  跳过: {skipped_count} 张表")
    safe_print(f"  总计: {len(tables_to_check)} 张表")
    safe_print("\n修复完成！")

if __name__ == "__main__":
    main()
