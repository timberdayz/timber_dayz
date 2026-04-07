#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复重复文件记录问题

方案1+方案3：
1. 重新计算所有旧记录的file_hash（使用新的计算方式）
2. 清理重复记录（基于file_path，保留最新的记录）

执行步骤：
1. 重新计算所有记录的file_hash（如果文件存在）
2. 识别重复记录（基于file_path）
3. 清理重复记录（保留hash匹配的记录，删除hash不匹配的记录）
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
from modules.services.catalog_scanner import _compute_sha256
from modules.services.shop_resolver import ShopResolver

db = SessionLocal()

def recompute_file_hash(file_record: CatalogFile) -> tuple[str, bool]:
    """
    重新计算文件的hash（使用新的计算方式）
    
    Returns:
        (new_hash, success): 新hash和是否成功
    """
    if not file_record.file_path:
        return None, False
    
    file_path = Path(file_record.file_path)
    if not file_path.exists():
        return None, False
    
    try:
        # 获取shop_id和platform_code
        shop_id = file_record.shop_id or 'none'
        platform_code = file_record.platform_code or file_record.source_platform or 'unknown'
        
        # 使用新方式计算hash
        new_hash = _compute_sha256(
            file_path,
            shop_id=shop_id if shop_id != 'none' else None,  # 如果shop_id是'none'，传None
            platform_code=platform_code
        )
        
        return new_hash, True
    except Exception as e:
        print(f"      ❌ 计算hash失败: {e}")
        return None, False

def main(dry_run: bool = True):
    """
    主函数
    
    Args:
        dry_run: 是否为试运行模式（不实际修改数据库）
    """
    print(f"\n{'='*80}")
    print(f"🔧 修复重复文件记录")
    print(f"{'='*80}\n")
    
    if dry_run:
        print(f"⚠️  试运行模式（不会实际修改数据库）\n")
    else:
        print(f"⚠️  执行模式（将实际修改数据库）\n")
    
    try:
        # 1. 获取所有记录
        all_files = db.query(CatalogFile).all()
        print(f"📋 总记录数: {len(all_files)}个\n")
        
        # 2. 按file_path分组，识别重复记录
        # v4.18.0: 使用相对路径，与数据库存储格式一致
        print(f"📊 识别重复记录（基于file_path）...")
        path_groups = defaultdict(list)
        
        for file_record in all_files:
            if file_record.file_path:
                # 直接使用数据库中存储的路径格式（相对路径）
                path_groups[file_record.file_path].append(file_record)
        
        duplicate_paths = {p: files for p, files in path_groups.items() if len(files) > 1}
        print(f"   唯一路径数: {len(path_groups)}")
        print(f"   重复路径数: {len(duplicate_paths)}\n")
        
        if not duplicate_paths:
            print(f"✅ 没有发现重复记录\n")
            return
        
        # 3. 重新计算hash并识别需要删除的记录
        print(f"📊 重新计算hash并识别需要删除的记录...\n")
        
        records_to_delete = []
        records_to_update = []
        
        for path, files in duplicate_paths.items():
            file_path = Path(path)
            if not file_path.exists():
                print(f"   ⚠️  文件不存在，跳过: {file_path.name}")
                continue
            
            print(f"   文件: {file_path.name} ({len(files)}个记录)")
            
            # 重新计算正确的hash
            # 使用第一个记录的shop_id和platform_code作为参考
            reference_record = files[0]
            shop_id = reference_record.shop_id or 'none'
            platform_code = reference_record.platform_code or reference_record.source_platform or 'unknown'
            
            correct_hash, success = recompute_file_hash(reference_record)
            if not success:
                print(f"      ❌ 无法计算正确hash，跳过")
                continue
            
            print(f"      正确hash: {correct_hash[:16]}...")
            
            # 检查每个记录
            for file_record in files:
                current_hash = file_record.file_hash or ''
                is_correct = (current_hash == correct_hash)
                
                print(f"      记录ID {file_record.id}:")
                print(f"        当前hash: {current_hash[:16] if current_hash else 'None'}...")
                print(f"        状态: {file_record.status}")
                print(f"        shop_id: {file_record.shop_id}, platform: {file_record.platform_code}")
                
                if is_correct:
                    print(f"        ✅ hash正确，保留")
                else:
                    print(f"        ❌ hash不正确，标记删除")
                    records_to_delete.append(file_record)
            
            # 如果所有记录的hash都不正确，保留最新的记录
            if all(record.file_hash != correct_hash for record in files):
                print(f"      ⚠️  所有记录的hash都不正确，保留最新的记录（ID: {max(files, key=lambda r: r.id).id}）")
                # 更新最新记录的hash
                latest_record = max(files, key=lambda r: r.id)
                records_to_update.append((latest_record, correct_hash))
                # 删除其他记录
                for record in files:
                    if record.id != latest_record.id:
                        records_to_delete.append(record)
            else:
                # 删除hash不正确的记录
                for record in files:
                    if record.file_hash != correct_hash:
                        records_to_delete.append(record)
            
            print()
        
        # 4. 执行删除和更新
        print(f"📊 执行操作:")
        print(f"   需要删除的记录数: {len(records_to_delete)}")
        print(f"   需要更新hash的记录数: {len(records_to_update)}\n")
        
        if records_to_delete or records_to_update:
            if dry_run:
                print(f"⚠️  试运行模式，不会实际修改数据库")
                print(f"\n   将删除的记录ID: {[r.id for r in records_to_delete]}")
                print(f"   将更新hash的记录ID: {[r.id for r, _ in records_to_update]}\n")
            else:
                # 执行删除
                deleted_count = 0
                for record in records_to_delete:
                    try:
                        print(f"   删除记录 ID {record.id}: {record.file_name}")
                        db.delete(record)
                        deleted_count += 1
                    except Exception as e:
                        print(f"      ❌ 删除失败: {e}")
                
                # 执行更新
                updated_count = 0
                for record, new_hash in records_to_update:
                    try:
                        print(f"   更新记录 ID {record.id}: {record.file_name}")
                        record.file_hash = new_hash
                        updated_count += 1
                    except Exception as e:
                        print(f"      ❌ 更新失败: {e}")
                
                # 提交事务
                db.commit()
                print(f"\n✅ 操作完成:")
                print(f"   删除记录: {deleted_count}个")
                print(f"   更新记录: {updated_count}个\n")
        else:
            print(f"✅ 没有需要操作记录\n")
        
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"\n❌ 修复失败: {e}\n")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="修复重复文件记录")
    parser.add_argument("--execute", action="store_true", help="实际执行（默认是试运行）")
    
    args = parser.parse_args()
    
    main(dry_run=not args.execute)

