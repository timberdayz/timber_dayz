#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证miaoshou库存文件重命名结果
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db
from sqlalchemy import text, select
from modules.core.db import CatalogFile

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def main():
    safe_print("\n" + "="*70)
    safe_print("验证miaoshou库存文件重命名结果")
    safe_print("="*70)
    
    db = next(get_db())
    
    try:
        # 检查inventory域文件
        safe_print("\n[1] 检查inventory域文件...")
        query = select(CatalogFile).where(
            CatalogFile.platform_code == 'miaoshou',
            CatalogFile.data_domain == 'inventory',
            CatalogFile.granularity == 'snapshot'
        )
        inventory_files = db.execute(query).scalars().all()
        safe_print(f"  找到 {len(inventory_files)} 个inventory域文件:")
        for f in inventory_files[:10]:  # 只显示前10个
            safe_print(f"    - {f.file_name}")
        if len(inventory_files) > 10:
            safe_print(f"    ... 还有 {len(inventory_files) - 10} 个文件")
        
        # 检查是否还有products域的文件
        safe_print("\n[2] 检查是否还有products域文件...")
        query2 = select(CatalogFile).where(
            CatalogFile.platform_code == 'miaoshou',
            CatalogFile.data_domain == 'products',
            CatalogFile.granularity == 'snapshot'
        )
        products_files = db.execute(query2).scalars().all()
        if len(products_files) == 0:
            safe_print("  [OK] 没有products域的snapshot文件（已全部迁移）")
        else:
            safe_print(f"  [WARN] 仍有 {len(products_files)} 个products域文件:")
            for f in products_files[:5]:
                safe_print(f"    - {f.file_name}")
        
        # 检查文件命名格式
        safe_print("\n[3] 检查文件命名格式...")
        wrong_naming = []
        for f in inventory_files:
            if 'products' in f.file_name:
                wrong_naming.append(f.file_name)
        
        if len(wrong_naming) == 0:
            safe_print("  [OK] 所有inventory域文件命名正确（不包含products）")
        else:
            safe_print(f"  [FAIL] 发现 {len(wrong_naming)} 个命名错误的文件:")
            for name in wrong_naming[:5]:
                safe_print(f"    - {name}")
        
        # 总结
        safe_print("\n" + "="*70)
        safe_print("[SUCCESS] 验证完成！")
        safe_print("="*70)
        safe_print(f"  inventory域文件: {len(inventory_files)} 个")
        safe_print(f"  products域文件: {len(products_files)} 个")
        safe_print(f"  命名错误文件: {len(wrong_naming)} 个")
        
    except Exception as e:
        safe_print(f"\n[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()

