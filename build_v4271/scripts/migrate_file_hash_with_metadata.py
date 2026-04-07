#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移file_hash脚本

将现有记录的file_hash更新为包含shop_id和platform_code的新hash值。
"""

import sys
from pathlib import Path
import hashlib

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select, update
from modules.core.db import CatalogFile
from backend.models.database import SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def _compute_sha256_with_metadata(file_path: Path, shop_id: str = None, platform_code: str = None, block_size: int = 1024 * 1024) -> str:
    """
    计算文件SHA256哈希（包含shop_id和platform_code）
    
    ⭐ v4.17.3修复：将shop_id和platform_code纳入hash计算
    """
    h = hashlib.sha256()
    
    # 先加入shop_id和platform_code（如果存在）
    if shop_id:
        h.update(f"shop_id:{shop_id}".encode('utf-8'))
    if platform_code:
        h.update(f"platform:{platform_code}".encode('utf-8'))
    
    # 再加入文件内容
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    
    return h.hexdigest()


def migrate_file_hash(dry_run: bool = True):
    """
    迁移file_hash
    
    Args:
        dry_run: 如果为True，只显示将要更新的记录，不实际更新
    """
    db = SessionLocal()
    
    try:
        print(f"\n{'='*80}")
        print(f"🔄 file_hash迁移脚本（v4.17.3修复）")
        print(f"{'='*80}\n")
        
        if dry_run:
            print(f"⚠️  运行模式: DRY RUN（只显示，不实际更新）\n")
        else:
            print(f"⚠️  运行模式: 实际更新（将修改数据库）\n")
        
        # 1. 查询所有需要更新的记录
        files = db.execute(
            select(CatalogFile).where(
                CatalogFile.file_hash.isnot(None),
                CatalogFile.file_path.isnot(None)
            )
        ).scalars().all()
        
        print(f"📊 统计信息")
        print(f"{'-'*80}")
        print(f"需要更新的记录数: {len(files)}")
        print()
        
        # 2. 处理每条记录
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        print(f"📋 处理记录")
        print(f"{'-'*80}")
        
        for idx, file_record in enumerate(files, 1):
            try:
                # 检查文件是否存在
                file_path = Path(file_record.file_path)
                if not file_path.exists():
                    logger.warning(f"文件不存在，跳过: {file_path}")
                    skipped_count += 1
                    continue
                
                # 获取shop_id和platform_code
                shop_id = file_record.shop_id
                platform_code = file_record.platform_code or file_record.source_platform
                
                # 计算新的hash
                new_hash = _compute_sha256_with_metadata(
                    file_path,
                    shop_id=shop_id,
                    platform_code=platform_code
                )
                
                # 检查hash是否变化
                old_hash = file_record.file_hash
                if old_hash == new_hash:
                    # hash没有变化，跳过
                    skipped_count += 1
                    continue
                
                # 显示更新信息
                if idx <= 10 or not dry_run:  # 只显示前10条或实际更新时显示所有
                    print(f"{idx}. {file_record.file_name}")
                    print(f"   旧hash: {old_hash[:16]}...")
                    print(f"   新hash: {new_hash[:16]}...")
                    print(f"   shop_id: {shop_id}, platform_code: {platform_code}")
                
                # 更新记录
                if not dry_run:
                    # 检查新hash是否已存在（避免冲突）
                    existing = db.execute(
                        select(CatalogFile).where(CatalogFile.file_hash == new_hash)
                    ).scalar_one_or_none()
                    
                    if existing and existing.id != file_record.id:
                        logger.error(
                            f"新hash已存在（冲突）: {file_record.file_name}, "
                            f"新hash={new_hash[:16]}..., 已存在记录ID={existing.id}"
                        )
                        error_count += 1
                        continue
                    
                    # 更新hash
                    db.execute(
                        update(CatalogFile)
                        .where(CatalogFile.id == file_record.id)
                        .values(file_hash=new_hash)
                    )
                    updated_count += 1
                else:
                    updated_count += 1
                
            except Exception as e:
                logger.error(f"处理记录失败: {file_record.file_name}, 错误: {e}", exc_info=True)
                error_count += 1
        
        # 3. 提交事务
        if not dry_run:
            db.commit()
            print(f"\n✅ 已提交 {updated_count} 条记录的更新")
        else:
            print(f"\n📊 预览结果（DRY RUN）")
        
        # 4. 显示统计
        print(f"\n{'='*80}")
        print(f"📊 迁移统计")
        print(f"{'='*80}")
        print(f"总记录数: {len(files)}")
        print(f"更新记录数: {updated_count}")
        print(f"跳过记录数: {skipped_count}（hash未变化或文件不存在）")
        print(f"错误记录数: {error_count}")
        print()
        
        if dry_run:
            print(f"💡 提示: 这是DRY RUN模式，没有实际更新数据库")
            print(f"   要实际执行更新，请运行: python scripts/migrate_file_hash_with_metadata.py --execute")
        else:
            print(f"✅ 迁移完成！")
        
        print(f"\n{'='*80}\n")
        
    except Exception as e:
        logger.error(f"迁移失败: {e}", exc_info=True)
        db.rollback()
        print(f"\n❌ 迁移失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="迁移file_hash（包含shop_id和platform_code）")
    parser.add_argument("--execute", action="store_true", help="实际执行更新（默认是DRY RUN）")
    args = parser.parse_args()
    
    migrate_file_hash(dry_run=not args.execute)

