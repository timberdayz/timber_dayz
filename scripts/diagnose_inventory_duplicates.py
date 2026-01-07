#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断库存文件重复问题

检查：
1. 文件系统中有多少库存文件
2. 数据库中有多少库存文件记录
3. 为什么会有重复记录
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
from modules.core.path_manager import get_data_raw_dir
from modules.services.catalog_scanner import _compute_sha256

db = SessionLocal()

try:
    print(f"\n{'='*80}")
    print(f"📊 库存文件重复问题诊断")
    print(f"{'='*80}\n")
    
    # 1. 检查文件系统中的库存文件
    print(f"📋 文件系统中的库存文件:")
    scan_dir = get_data_raw_dir()
    inventory_files = []
    
    for year_dir in scan_dir.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
            for file_path in year_dir.rglob("*.*"):
                if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                    if file_path.suffix != '.json':
                        file_name_lower = file_path.name.lower()
                        if 'inventory' in file_name_lower or 'snapshot' in file_name_lower:
                            inventory_files.append(file_path)
    
    print(f"   扫描到的文件数: {len(inventory_files)}个")
    if inventory_files:
        print(f"   文件列表:")
        for file_path in sorted(inventory_files):
            print(f"     - {file_path.name}")
    print()
    
    # 2. 检查数据库中的库存文件记录
    print(f"📋 数据库中的库存文件记录:")
    db_inventory = db.query(CatalogFile).filter(
        CatalogFile.data_domain == 'inventory'
    ).all()
    
    print(f"   数据库记录数: {len(db_inventory)}个")
    print()
    
    # 3. 检查file_hash重复情况
    print(f"📊 file_hash重复情况:")
    hash_counts = defaultdict(list)
    for file_record in db_inventory:
        if file_record.file_hash:
            hash_counts[file_record.file_hash].append(file_record)
    
    duplicate_hashes = {h: files for h, files in hash_counts.items() if len(files) > 1}
    unique_hashes = {h: files for h, files in hash_counts.items() if len(files) == 1}
    
    print(f"   唯一hash数: {len(hash_counts)}")
    print(f"   重复hash数: {len(duplicate_hashes)}")
    print(f"   唯一hash记录数: {len(unique_hashes)}")
    print()
    
    # 4. 检查file_path重复情况
    # v4.18.0: 使用相对路径，与数据库存储格式一致
    print(f"📊 file_path重复情况:")
    path_counts = defaultdict(list)
    for file_record in db_inventory:
        if file_record.file_path:
            # 直接使用数据库中存储的路径格式（相对路径）
            path_counts[file_record.file_path].append(file_record)
    
    duplicate_paths = {p: files for p, files in path_counts.items() if len(files) > 1}
    
    print(f"   唯一路径数: {len(path_counts)}")
    print(f"   重复路径数: {len(duplicate_paths)}")
    if duplicate_paths:
        print(f"   重复路径详情:")
        for path, files in list(duplicate_paths.items())[:10]:
            print(f"     路径: {path}")
            for file_record in files:
                print(f"       - ID: {file_record.id}, 文件名: {file_record.file_name}")
                print(f"         状态: {file_record.status}, shop_id: {file_record.shop_id}")
                print(f"         hash: {file_record.file_hash[:16] if file_record.file_hash else 'None'}...")
    print()
    
    # 5. 检查file_name重复情况
    print(f"📊 file_name重复情况:")
    name_counts = defaultdict(list)
    for file_record in db_inventory:
        if file_record.file_name:
            name_counts[file_record.file_name].append(file_record)
    
    duplicate_names = {n: files for n, files in name_counts.items() if len(files) > 1}
    
    print(f"   唯一文件名数: {len(name_counts)}")
    print(f"   重复文件名数: {len(duplicate_names)}")
    if duplicate_names:
        print(f"   重复文件名详情:")
        for name, files in sorted(duplicate_names.items()):
            print(f"     文件名: {name} ({len(files)}个记录)")
            for file_record in files:
                print(f"       - ID: {file_record.id}, 状态: {file_record.status}")
                print(f"         路径: {file_record.file_path}")
                print(f"         shop_id: {file_record.shop_id}, platform: {file_record.platform_code}")
                print(f"         hash: {file_record.file_hash[:16] if file_record.file_hash else 'None'}...")
    print()
    
    # 6. 检查hash计算方式差异
    print(f"📊 file_hash计算方式检查:")
    print(f"   检查旧记录和新记录的hash是否不同...")
    
    # 对于重复的文件名，检查它们的hash是否不同
    for name, files in list(duplicate_names.items())[:5]:
        if len(files) > 1:
            print(f"\n   文件名: {name}")
            # 找到实际文件
            actual_file = None
            for file_path in inventory_files:
                if file_path.name == name:
                    actual_file = file_path
                    break
            
            if actual_file:
                # 使用新方式计算hash（包含shop_id和platform_code）
                new_hash = _compute_sha256(
                    actual_file,
                    shop_id='none',  # miaoshou库存文件的shop_id应该是'none'
                    platform_code='miaoshou'
                )
                print(f"     实际文件路径: {actual_file}")
                print(f"     新hash（shop_id='none', platform='miaoshou'）: {new_hash[:16]}...")
                
                for file_record in files:
                    print(f"      记录ID {file_record.id}:")
                    print(f"        旧hash: {file_record.file_hash[:16] if file_record.file_hash else 'None'}...")
                    print(f"        shop_id: {file_record.shop_id}")
                    print(f"        platform: {file_record.platform_code}")
                    if file_record.file_hash == new_hash:
                        print(f"        ✅ hash匹配")
                    else:
                        print(f"        ❌ hash不匹配（可能是旧计算方式）")
    
    # 7. 总结
    print(f"\n{'='*80}")
    print(f"📊 诊断总结")
    print(f"{'='*80}")
    print(f"文件系统中库存文件: {len(inventory_files)}个")
    print(f"数据库中库存文件记录: {len(db_inventory)}个")
    print(f"唯一file_hash数: {len(hash_counts)}个")
    print(f"唯一file_path数: {len(path_counts)}个")
    print(f"唯一file_name数: {len(name_counts)}个")
    print(f"重复hash数: {len(duplicate_hashes)}个")
    print(f"重复路径数: {len(duplicate_paths)}个")
    print(f"重复文件名数: {len(duplicate_names)}个")
    print()
    
    if len(duplicate_names) > 0:
        print(f"🔍 问题分析:")
        print(f"   ⚠️  发现重复记录：{len(duplicate_names)}个文件名有多个记录")
        print(f"   💡 可能原因：")
        print(f"      1. file_hash计算方式改变（v4.17.3修复后，hash包含shop_id和platform_code）")
        print(f"      2. 旧记录的hash不包含shop_id和platform_code，新记录的hash包含")
        print(f"      3. 导致同一个文件被注册为多条记录")
        print(f"   💡 解决方案：")
        print(f"      1. 重新计算所有旧记录的file_hash（使用新的计算方式）")
        print(f"      2. 或者清理重复记录，只保留最新的记录")
        print(f"      3. 或者修改去重逻辑，基于file_path而不是file_hash")
    
    print(f"{'='*80}\n")
    
except Exception as e:
    print(f"\n❌ 诊断失败: {e}\n")
    import traceback
    traceback.print_exc()
finally:
    db.close()

