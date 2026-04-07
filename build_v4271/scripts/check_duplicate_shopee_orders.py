#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查Shopee订单文件的重复记录

检查数据库中是否有重复的file_hash或file_path
"""

import sys
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal

db = SessionLocal()

try:
    print(f"\n{'='*80}")
    print(f"📊 检查Shopee订单文件重复记录")
    print(f"{'='*80}\n")
    
    # 1. 查询所有Shopee订单文件
    shopee_orders = db.query(CatalogFile).filter(
        CatalogFile.platform_code == 'shopee',
        CatalogFile.data_domain == 'orders'
    ).all()
    
    print(f"📋 数据库中Shopee订单文件总数: {len(shopee_orders)}个\n")
    
    # 2. 检查file_hash重复
    hash_counts = defaultdict(list)
    for file_record in shopee_orders:
        if file_record.file_hash:
            hash_counts[file_record.file_hash].append(file_record)
    
    duplicate_hashes = {h: files for h, files in hash_counts.items() if len(files) > 1}
    
    print(f"📊 file_hash重复情况:")
    print(f"   唯一hash数: {len(hash_counts)}")
    print(f"   重复hash数: {len(duplicate_hashes)}")
    if duplicate_hashes:
        print(f"   重复hash详情:")
        for hash_val, files in list(duplicate_hashes.items())[:5]:
            print(f"     Hash: {hash_val[:16]}... ({len(files)}个文件)")
            for file_record in files:
                print(f"       - ID: {file_record.id}, 文件名: {file_record.file_name}, 状态: {file_record.status}")
    print()
    
    # 3. 检查file_path重复
    path_counts = defaultdict(list)
    for file_record in shopee_orders:
        if file_record.file_path:
            path_counts[file_record.file_path].append(file_record)
    
    duplicate_paths = {p: files for p, files in path_counts.items() if len(files) > 1}
    
    print(f"📊 file_path重复情况:")
    print(f"   唯一路径数: {len(path_counts)}")
    print(f"   重复路径数: {len(duplicate_paths)}")
    if duplicate_paths:
        print(f"   重复路径详情:")
        for path, files in list(duplicate_paths.items())[:5]:
            print(f"     路径: {path}")
            for file_record in files:
                print(f"       - ID: {file_record.id}, 文件名: {file_record.file_name}, 状态: {file_record.status}, hash: {file_record.file_hash[:16] if file_record.file_hash else 'None'}...")
    print()
    
    # 4. 检查file_name重复
    name_counts = defaultdict(list)
    for file_record in shopee_orders:
        if file_record.file_name:
            name_counts[file_record.file_name].append(file_record)
    
    duplicate_names = {n: files for n, files in name_counts.items() if len(files) > 1}
    
    print(f"📊 file_name重复情况:")
    print(f"   唯一文件名数: {len(name_counts)}")
    print(f"   重复文件名数: {len(duplicate_names)}")
    if duplicate_names:
        print(f"   重复文件名详情:")
        for name, files in list(duplicate_names.items())[:10]:
            print(f"     文件名: {name} ({len(files)}个记录)")
            for file_record in files:
                print(f"       - ID: {file_record.id}, 状态: {file_record.status}, 路径: {file_record.file_path}")
    print()
    
    # 5. 总结
    print(f"{'='*80}")
    print(f"📊 总结")
    print(f"{'='*80}")
    print(f"数据库中Shopee订单文件总数: {len(shopee_orders)}个")
    print(f"唯一file_hash数: {len(hash_counts)}个")
    print(f"唯一file_path数: {len(path_counts)}个")
    print(f"唯一file_name数: {len(name_counts)}个")
    print(f"重复hash数: {len(duplicate_hashes)}个")
    print(f"重复路径数: {len(duplicate_paths)}个")
    print(f"重复文件名数: {len(duplicate_names)}个")
    print(f"{'='*80}\n")
    
except Exception as e:
    print(f"\n❌ 检查失败: {e}\n")
    import traceback
    traceback.print_exc()
finally:
    db.close()

