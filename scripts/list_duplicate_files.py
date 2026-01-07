#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出重复文件脚本

详细列出扫描时发现的重复文件（基于file_hash），包括文件名、路径、hash等信息。
"""

import sys
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.services.catalog_scanner import _compute_sha256, _is_repaired_cache
from modules.core.logger import get_logger

logger = get_logger(__name__)


def list_duplicate_files():
    """列出所有重复文件"""
    db = SessionLocal()
    
    try:
        print(f"\n{'='*80}")
        print(f"📋 重复文件详细列表")
        print(f"{'='*80}\n")
        
        # 1. 扫描文件系统，找出所有文件及其hash
        base_dir = Path("data/raw")
        file_hash_map = defaultdict(list)  # hash -> [file_paths]
        all_files = []
        
        if not base_dir.exists():
            print(f"❌ 扫描目录不存在: {base_dir}")
            return
        
        # 扫描所有年份目录
        year_dirs = []
        for item in base_dir.iterdir():
            if item.is_dir() and item.name.isdigit() and len(item.name) == 4:
                year_dirs.append(item)
        
        print(f"📁 扫描目录: {base_dir}")
        print(f"   发现 {len(year_dirs)} 个年份分区: {', '.join([d.name for d in year_dirs])}\n")
        
        for year_dir in year_dirs:
            for file_path in year_dir.rglob("*"):
                # 跳过目录
                if not file_path.is_file():
                    continue
                
                # 跳过元数据文件
                if file_path.suffix == '.json':
                    continue
                
                # 跳过修复缓存文件
                if _is_repaired_cache(file_path):
                    continue
                
                # 只处理支持的格式
                if file_path.suffix.lower() not in ['.xlsx', '.xls']:
                    continue
                
                # 计算文件hash
                try:
                    file_hash = _compute_sha256(file_path)
                    file_hash_map[file_hash].append(file_path)
                    all_files.append((file_path, file_hash))
                except Exception as e:
                    logger.warning(f"计算文件hash失败: {file_path}, 错误: {e}")
        
        # 2. 查询数据库中的文件hash
        db_files = db.execute(
            select(CatalogFile.file_hash, CatalogFile.id, CatalogFile.file_name, CatalogFile.file_path)
        ).all()
        
        db_hash_map = {}
        for file_hash, file_id, file_name, file_path in db_files:
            if file_hash:
                db_hash_map[file_hash] = {
                    'id': file_id,
                    'file_name': file_name,
                    'file_path': file_path
                }
        
        # 3. 找出重复文件
        duplicate_groups = []
        total_duplicates = 0
        
        for file_hash, file_paths in file_hash_map.items():
            if len(file_paths) > 1:
                # 文件系统中就有重复（相同hash的多个文件）
                duplicate_groups.append({
                    'hash': file_hash,
                    'files': file_paths,
                    'type': 'filesystem_duplicate',
                    'db_record': db_hash_map.get(file_hash)
                })
                total_duplicates += len(file_paths) - 1
            elif file_hash in db_hash_map:
                # 文件已存在于数据库（扫描时会更新而不是新增）
                db_record = db_hash_map[file_hash]
                # 检查文件路径是否不同
                if file_paths[0].name != db_record['file_name'] or str(file_paths[0]) != db_record['file_path']:
                    duplicate_groups.append({
                        'hash': file_hash,
                        'files': file_paths,
                        'type': 'db_existing',
                        'db_record': db_record
                    })
        
        # 4. 统计信息
        print(f"📊 统计信息")
        print(f"{'-'*80}")
        print(f"扫描发现文件总数: {len(all_files)}")
        print(f"唯一文件数（基于hash）: {len(file_hash_map)}")
        print(f"数据库中的文件数: {len(db_hash_map)}")
        print(f"重复文件组数: {len(duplicate_groups)}")
        print(f"重复文件总数: {total_duplicates}")
        print()
        
        # 5. 详细列出重复文件
        if duplicate_groups:
            print(f"{'='*80}")
            print(f"📋 重复文件详细列表")
            print(f"{'='*80}\n")
            
            for idx, group in enumerate(duplicate_groups, 1):
                print(f"【重复组 {idx}】")
                print(f"文件Hash: {group['hash']}")
                
                if group['type'] == 'filesystem_duplicate':
                    print(f"类型: 文件系统中存在多个相同内容的文件")
                    print(f"文件列表:")
                    for i, file_path in enumerate(group['files'], 1):
                        file_size = file_path.stat().st_size if file_path.exists() else 0
                        print(f"  {i}. {file_path.name}")
                        print(f"     路径: {file_path}")
                        print(f"     大小: {file_size:,} 字节 ({file_size/1024:.2f} KB)")
                    
                    if group['db_record']:
                        print(f"\n数据库记录:")
                        print(f"  ID: {group['db_record']['id']}")
                        print(f"  文件名: {group['db_record']['file_name']}")
                        print(f"  路径: {group['db_record']['file_path']}")
                    else:
                        print(f"\n⚠️  数据库中不存在此hash的记录")
                
                elif group['type'] == 'db_existing':
                    print(f"类型: 文件已存在于数据库（扫描时会更新而不是新增）")
                    print(f"文件系统中的文件:")
                    for i, file_path in enumerate(group['files'], 1):
                        file_size = file_path.stat().st_size if file_path.exists() else 0
                        print(f"  {i}. {file_path.name}")
                        print(f"     路径: {file_path}")
                        print(f"     大小: {file_size:,} 字节 ({file_size/1024:.2f} KB)")
                    
                    print(f"\n数据库记录:")
                    print(f"  ID: {group['db_record']['id']}")
                    print(f"  文件名: {group['db_record']['file_name']}")
                    print(f"  路径: {group['db_record']['file_path']}")
                
                print()
        else:
            print(f"✅ 没有发现重复文件")
        
        # 6. 总结
        print(f"{'='*80}")
        print(f"📝 总结")
        print(f"{'='*80}")
        print(f"\n扫描发现文件数: {len(all_files)}")
        print(f"数据库中文件数: {len(db_hash_map)}")
        print(f"差异: {len(all_files) - len(db_hash_map)} 个文件")
        
        if len(all_files) > len(db_hash_map):
            print(f"\n说明:")
            print(f"  - 有 {len(all_files) - len(db_hash_map)} 个文件是重复的（相同内容）")
            print(f"  - 这些文件在扫描时会更新现有记录，不会新增")
            print(f"  - 这是正常行为：基于file_hash去重，避免数据重复")
        elif len(all_files) < len(db_hash_map):
            print(f"\n说明:")
            print(f"  - 数据库中的文件数多于扫描发现的文件数")
            print(f"  - 可能原因：数据库中有历史文件或来自其他目录的文件")
        
        print(f"\n{'='*80}\n")
        
    except Exception as e:
        logger.error(f"列出重复文件失败: {e}", exc_info=True)
        print(f"\n❌ 列出重复文件失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    list_duplicate_files()

