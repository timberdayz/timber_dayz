#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移执行脚本
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

def run_migration():
    """执行数据库迁移"""
    
    # 1. 备份数据库
    db_path = Path('data/unified_erp_system.db')
    backup_path = Path(f'data/unified_erp_system.db.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        print(f'✅ 数据库已备份: {backup_path}')
    else:
        print('❌ 数据库文件不存在')
        return False
    
    # 2. 执行迁移
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # 2.1 增加 granularity 字段
        try:
            cursor.execute("""
                ALTER TABLE fact_product_metrics 
                ADD COLUMN granularity VARCHAR(20) DEFAULT 'daily'
            """)
            print('✅ 已添加 granularity 字段')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                print('⚠️ granularity 字段已存在，跳过')
            else:
                raise
        
        # 2.2 增加 time_dimension 字段
        try:
            cursor.execute("""
                ALTER TABLE fact_product_metrics 
                ADD COLUMN time_dimension VARCHAR(50) DEFAULT NULL
            """)
            print('✅ 已添加 time_dimension 字段')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                print('⚠️ time_dimension 字段已存在，跳过')
            else:
                raise
        
        # 2.3 为现有数据设置默认值
        cursor.execute("""
            UPDATE fact_product_metrics 
            SET granularity = 'daily' 
            WHERE granularity IS NULL
        """)
        print(f'✅ 已更新 {cursor.rowcount} 条记录的 granularity 字段')
        
        cursor.execute("""
            UPDATE fact_product_metrics 
            SET time_dimension = DATE(metric_date) 
            WHERE time_dimension IS NULL
        """)
        print(f'✅ 已更新 {cursor.rowcount} 条记录的 time_dimension 字段')
        
        # 2.4 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_metrics_granularity 
            ON fact_product_metrics(granularity)
        """)
        print('✅ 已创建 granularity 索引')
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_metrics_time_dimension 
            ON fact_product_metrics(time_dimension)
        """)
        print('✅ 已创建 time_dimension 索引')
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_product_metrics_composite 
            ON fact_product_metrics(platform_code, shop_id, metric_date, granularity, time_dimension)
        """)
        print('✅ 已创建复合索引')
        
        conn.commit()
        
        # 3. 验证迁移结果
        print('\n=== 验证表结构 ===')
        cursor.execute("PRAGMA table_info(fact_product_metrics)")
        for row in cursor.fetchall():
            if 'granularity' in row[1] or 'time_dimension' in row[1]:
                print(f'  {row[1]}: {row[2]}')
        
        print('\n=== 验证数据完整性 ===')
        cursor.execute('SELECT COUNT(*) FROM fact_product_metrics')
        total = cursor.fetchone()[0]
        print(f'  总记录数: {total}')
        
        print('\n=== 验证粒度分布 ===')
        cursor.execute('SELECT granularity, COUNT(*) FROM fact_product_metrics GROUP BY granularity')
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[1]} 条记录')
        
        conn.close()
        print('\n✅ 数据库迁移完成')
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f'\n❌ 迁移失败: {e}')
        print(f'   数据库已回滚，备份文件: {backup_path}')
        return False

if __name__ == "__main__":
    run_migration()

