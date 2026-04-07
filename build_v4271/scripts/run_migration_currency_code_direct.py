#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接执行currency_code字段迁移SQL

功能：
1. 直接执行SQL迁移（绕过Alembic配置问题）
2. 验证表结构
3. 检查索引
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect, text
from backend.utils.config import get_settings
from modules.core.logger import get_logger

logger = get_logger(__name__)


def run_migration_direct():
    """直接执行SQL迁移"""
    try:
        # 获取数据库连接
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        # 所有fact_raw_data_*表列表
        tables = [
            'fact_raw_data_orders_daily',
            'fact_raw_data_orders_weekly',
            'fact_raw_data_orders_monthly',
            'fact_raw_data_products_daily',
            'fact_raw_data_products_weekly',
            'fact_raw_data_products_monthly',
            'fact_raw_data_traffic_daily',
            'fact_raw_data_traffic_weekly',
            'fact_raw_data_traffic_monthly',
            'fact_raw_data_services_daily',
            'fact_raw_data_services_weekly',
            'fact_raw_data_services_monthly',
            'fact_raw_data_inventory_snapshot',
        ]
        
        print("[*] 开始执行数据库迁移...")
        print(f"[*] 共需处理 {len(tables)} 个表\n")
        
        inspector = inspect(engine)
        success_count = 0
        skip_count = 0
        error_count = 0
        
        with engine.connect() as conn:
            # 开始事务
            trans = conn.begin()
            
            try:
                for idx, table_name in enumerate(tables, 1):
                    print(f"[{idx}/{len(tables)}] 处理表: {table_name}")
                    
                    if not inspector.has_table(table_name):
                        print(f"  [WARN] 表不存在，跳过\n")
                        skip_count += 1
                        continue
                    
                    # 检查字段是否已存在
                    columns = [col['name'] for col in inspector.get_columns(table_name)]
                    
                    if 'currency_code' not in columns:
                        # 添加currency_code字段
                        print(f"  [*] 添加 currency_code 字段...", end=" ", flush=True)
                        conn.execute(text(f"""
                            ALTER TABLE {table_name} 
                            ADD COLUMN currency_code VARCHAR(3) NULL
                        """))
                        print("[OK]")
                    else:
                        print(f"  [SKIP] currency_code 字段已存在")
                    
                    # 检查索引是否已存在
                    indexes = [idx_obj['name'] for idx_obj in inspector.get_indexes(table_name)]
                    index_name = f'ix_{table_name}_currency'
                    
                    if index_name not in indexes:
                        # 创建索引
                        print(f"  [*] 创建货币索引...", end=" ", flush=True)
                        conn.execute(text(f"""
                            CREATE INDEX {index_name} 
                            ON {table_name}(currency_code)
                        """))
                        print("[OK]")
                    else:
                        print(f"  [SKIP] 货币索引已存在")
                    
                    success_count += 1
                    print()
                
                # 提交事务
                trans.commit()
                print(f"[OK] 数据库迁移完成: 成功 {success_count} 个，跳过 {skip_count} 个")
                return True
                
            except Exception as e:
                # 回滚事务
                trans.rollback()
                raise e
                
    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration():
    """验证迁移结果"""
    try:
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        inspector = inspect(engine)
        
        # 所有fact_raw_data_*表列表
        tables = [
            'fact_raw_data_orders_daily',
            'fact_raw_data_orders_weekly',
            'fact_raw_data_orders_monthly',
            'fact_raw_data_products_daily',
            'fact_raw_data_products_weekly',
            'fact_raw_data_products_monthly',
            'fact_raw_data_traffic_daily',
            'fact_raw_data_traffic_weekly',
            'fact_raw_data_traffic_monthly',
            'fact_raw_data_services_daily',
            'fact_raw_data_services_weekly',
            'fact_raw_data_services_monthly',
            'fact_raw_data_inventory_snapshot',
        ]
        
        print("\n[*] 验证表结构...")
        all_ok = True
        
        for table_name in tables:
            if not inspector.has_table(table_name):
                print(f"  [WARN] 表 {table_name} 不存在，跳过")
                continue
            
            # 检查currency_code字段
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            if 'currency_code' not in columns:
                print(f"  [ERROR] 表 {table_name} 缺少 currency_code 字段")
                all_ok = False
            else:
                # 检查字段类型
                for col in inspector.get_columns(table_name):
                    if col['name'] == 'currency_code':
                        col_type = str(col['type'])
                        nullable = col['nullable']
                        print(f"  [OK] 表 {table_name}.currency_code: 类型={col_type}, nullable={nullable}")
                        break
            
            # 检查索引
            indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
            currency_index_found = False
            for idx_name in indexes:
                if 'currency' in idx_name.lower():
                    currency_index_found = True
                    print(f"  [OK] 表 {table_name} 有货币索引: {idx_name}")
                    break
            
            if not currency_index_found:
                print(f"  [WARN] 表 {table_name} 缺少货币索引")
        
        print("\n[*] 验证完成")
        return all_ok
        
    except Exception as e:
        print(f"[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("数据库迁移和验证脚本（直接SQL方式）")
    print("=" * 60)
    
    # 运行迁移
    if not run_migration_direct():
        print("\n[ERROR] 迁移失败，请检查错误信息")
        return 1
    
    # 验证迁移
    if not verify_migration():
        print("\n[WARN] 验证发现一些问题，请检查")
        return 1
    
    print("\n" + "=" * 60)
    print("[OK] 所有检查通过！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

