#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行currency_code字段迁移脚本

功能：
1. 运行Alembic迁移
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


def run_migration():
    """运行数据库迁移"""
    try:
        # 获取数据库连接
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        # 运行Alembic迁移
        from alembic import command
        from alembic.config import Config
        
        alembic_cfg = Config(str(project_root / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(project_root / "migrations"))
        
        print("[*] 开始运行数据库迁移...")
        command.upgrade(alembic_cfg, "head")
        print("[OK] 数据库迁移完成")
        
        return True
        
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
                        if 'VARCHAR(3)' not in col_type and 'String(3)' not in col_type:
                            print(f"  [WARN] 表 {table_name}.currency_code 类型可能不正确: {col_type}")
                        if not nullable:
                            print(f"  [WARN] 表 {table_name}.currency_code 应该是nullable=True")
                        break
                print(f"  [OK] 表 {table_name} 有 currency_code 字段")
            
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
    print("数据库迁移和验证脚本")
    print("=" * 60)
    
    # 运行迁移
    if not run_migration():
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

