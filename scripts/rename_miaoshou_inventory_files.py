#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量重命名miaoshou库存文件脚本
将 miaoshou_products_snapshot_*.xlsx 重命名为 miaoshou_inventory_snapshot_*.xlsx
并更新catalog_files表中的记录
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text, select
from modules.core.db import CatalogFile
import shutil
from datetime import datetime

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def main():
    safe_print("\n" + "="*70)
    safe_print("批量重命名miaoshou库存文件")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # Step 1: 查找所有需要重命名的文件（catalog_files表中的记录）
        safe_print("\n[Step 1] 查找需要重命名的文件...")
        query = select(CatalogFile).where(
            CatalogFile.platform_code == 'miaoshou',
            CatalogFile.data_domain == 'products',
            CatalogFile.granularity == 'snapshot'
        )
        files = db.execute(query).scalars().all()
        
        safe_print(f"  找到 {len(files)} 个文件需要重命名")
        
        if len(files) == 0:
            safe_print("  [INFO] 没有需要重命名的文件")
            return
        
        # Step 2: 重命名文件并更新数据库
        safe_print("\n[Step 2] 开始重命名文件...")
        renamed_count = 0
        failed_count = 0
        
        for file_record in files:
            try:
                old_path = Path(file_record.file_path)
                old_name = file_record.file_name
                
                # 检查文件是否存在
                if not old_path.exists():
                    safe_print(f"  [WARN] 文件不存在，跳过: {old_name}")
                    # 即使文件不存在，也更新数据库记录
                    new_name = old_name.replace('products', 'inventory')
                    file_record.file_name = new_name
                    file_record.data_domain = 'inventory'
                    db.commit()
                    renamed_count += 1
                    continue
                
                # 生成新文件名
                new_name = old_name.replace('products', 'inventory')
                new_path = old_path.parent / new_name
                
                # 重命名文件
                if old_path != new_path:
                    shutil.move(str(old_path), str(new_path))
                    safe_print(f"  [OK] {old_name} -> {new_name}")
                
                # 更新数据库记录
                file_record.file_name = new_name
                file_record.file_path = str(new_path)
                file_record.data_domain = 'inventory'
                db.commit()
                
                renamed_count += 1
                
            except Exception as e:
                safe_print(f"  [FAIL] 重命名失败 {file_record.file_name}: {e}")
                failed_count += 1
                db.rollback()
        
        # Step 3: 更新所有miaoshou+products+snapshot的记录（即使文件不存在）
        safe_print("\n[Step 3] 更新数据库记录...")
        update_query = text("""
            UPDATE catalog_files
            SET data_domain = 'inventory',
                file_name = REPLACE(file_name, 'products', 'inventory')
            WHERE platform_code = 'miaoshou'
              AND data_domain = 'products'
              AND granularity = 'snapshot'
        """)
        result = db.execute(update_query)
        db.commit()
        updated_count = result.rowcount
        
        safe_print(f"  [OK] 更新了 {updated_count} 条数据库记录")
        
        # Step 4: 验证结果
        safe_print("\n[Step 4] 验证结果...")
        remaining_query = select(CatalogFile).where(
            CatalogFile.platform_code == 'miaoshou',
            CatalogFile.data_domain == 'products',
            CatalogFile.granularity == 'snapshot'
        )
        remaining = db.execute(remaining_query).scalars().all()
        
        if len(remaining) == 0:
            safe_print("  [OK] 所有记录已更新为inventory域")
        else:
            safe_print(f"  [WARN] 仍有 {len(remaining)} 条记录未更新")
        
        # Step 5: 检查inventory域记录
        inventory_query = select(CatalogFile).where(
            CatalogFile.platform_code == 'miaoshou',
            CatalogFile.data_domain == 'inventory',
            CatalogFile.granularity == 'snapshot'
        )
        inventory_files = db.execute(inventory_query).scalars().all()
        safe_print(f"  [OK] inventory域现有 {len(inventory_files)} 个文件")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] 文件重命名完成！")
        safe_print("="*70)
        safe_print(f"  文件重命名: {renamed_count} 个成功, {failed_count} 个失败")
        safe_print(f"  数据库更新: {updated_count} 条记录")
        safe_print(f"  inventory域文件: {len(inventory_files)} 个")
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

