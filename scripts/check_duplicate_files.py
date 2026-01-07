#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查重复文件脚本

找出扫描时被跳过的重复文件（基于file_hash）。
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
from modules.services.catalog_scanner import _compute_sha256
from modules.core.logger import get_logger

logger = get_logger(__name__)


def check_duplicate_files():
    """检查重复文件"""
    db = SessionLocal()
    
    try:
        # 1. 统计数据库中的文件数
        db_count = db.query(func.count(CatalogFile.id)).scalar() or 0
        print(f"\n{'='*60}")
        print(f"📊 重复文件检查")
        print(f"{'='*60}")
        print(f"\n数据库中的文件数: {db_count}")
        
        # 2. 扫描文件系统，找出所有文件
        base_dir = Path("data/raw")
        all_files = []
        seen_hashes = set()
        duplicate_files = []
        
        if base_dir.exists():
            # 扫描所有年份目录
            for year_dir in base_dir.iterdir():
                if not year_dir.is_dir() or not year_dir.name.isdigit():
                    continue
                
                for file_path in year_dir.rglob("*.xlsx"):
                    if file_path.suffix == '.json':
                        continue
                    
                    # 计算文件hash
                    try:
                        file_hash = _compute_sha256(file_path)
                        all_files.append((file_path, file_hash))
                        
                        # 检查数据库中是否已存在
                        existing = db.execute(
                            select(CatalogFile).where(CatalogFile.file_hash == file_hash)
                        ).scalar_one_or_none()
                        
                        if existing:
                            if file_hash in seen_hashes:
                                duplicate_files.append((file_path, file_hash, existing.id))
                            else:
                                seen_hashes.add(file_hash)
                    except Exception as e:
                        logger.warning(f"处理文件失败: {file_path}, 错误: {e}")
        
        # 3. 统计结果
        total_files = len(all_files)
        unique_files = len(seen_hashes)
        duplicate_count = total_files - unique_files
        
        print(f"\n扫描结果:")
        print(f"  - 总文件数: {total_files}")
        print(f"  - 唯一文件数（基于hash）: {unique_files}")
        print(f"  - 重复文件数: {duplicate_count}")
        
        if duplicate_count > 0:
            print(f"\n⚠️  发现 {duplicate_count} 个重复文件（相同内容）")
            print(f"   这些文件在扫描时会被更新而不是新增")
            print(f"\n重复文件列表（前10个）:")
            for i, (file_path, file_hash, existing_id) in enumerate(duplicate_files[:10]):
                print(f"  {i+1}. {file_path.name}")
                print(f"     Hash: {file_hash[:16]}...")
                print(f"     已存在记录ID: {existing_id}")
        else:
            print(f"\n✅ 没有发现重复文件")
        
        # 4. 对比分析
        print(f"\n{'='*60}")
        print(f"🔍 对比分析")
        print(f"{'='*60}")
        print(f"\n扫描发现文件数: {total_files}")
        print(f"数据库中的文件数: {db_count}")
        print(f"差异: {total_files - db_count}个文件")
        
        if total_files - db_count == duplicate_count:
            print(f"\n✅ 差异原因已确认：{duplicate_count}个重复文件")
            print(f"   这是正常行为：基于file_hash去重，重复文件只更新不新增")
        elif total_files - db_count > duplicate_count:
            print(f"\n⚠️  差异大于重复文件数")
            print(f"   可能还有其他原因导致文件未注册")
        
        print(f"\n{'='*60}\n")
        
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        print(f"\n❌ 检查失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_duplicate_files()

