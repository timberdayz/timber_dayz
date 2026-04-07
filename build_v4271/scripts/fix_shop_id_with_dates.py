#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修复数据库中包含日期的 shop_id

v4.17.0修复：对于miaoshou平台的inventory和orders数据域，
如果shop_id包含日期格式（如 products_snapshot_20250926），
统一设置为 'none'，避免去重失败。

使用方法：
    python scripts/fix_shop_id_with_dates.py
"""

import sys
import re
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from modules.core.db.schema import CatalogFile
from modules.core.validators import normalize_platform, normalize_data_domain
from modules.core.logger import get_logger

logger = get_logger(__name__)


def fix_shop_id_with_dates(dry_run: bool = True):
    """
    批量修复数据库中包含日期的 shop_id
    
    Args:
        dry_run: 如果为True，只显示将要修复的记录，不实际修改
    """
    # 获取数据库引擎
    from backend.utils.config import get_settings
    from sqlalchemy import create_engine
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    
    session = Session(engine)
    
    try:
        # 查询所有需要检查的记录
        # 条件：miaoshou平台的inventory或orders数据域
        all_files = session.execute(
            select(CatalogFile).where(
                CatalogFile.platform_code.in_(['miaoshou', 'shou'])  # 兼容可能的变体
            )
        ).scalars().all()
        
        fixed_count = 0
        skipped_count = 0
        
        for file_record in all_files:
            # 标准化平台和数据域
            norm_platform = normalize_platform(file_record.platform_code or '')
            norm_domain = normalize_data_domain(file_record.data_domain or '')
            
            # 只处理miaoshou平台的inventory和orders数据域
            if norm_platform != 'miaoshou' or norm_domain not in ['inventory', 'orders']:
                continue
            
            # 检查shop_id是否包含日期格式或snapshot关键字
            shop_id = file_record.shop_id
            if not shop_id:
                continue
            
            shop_id_str = str(shop_id)
            has_date_pattern = bool(re.search(r'\d{8}', shop_id_str))
            has_snapshot = '_snapshot_' in shop_id_str.lower()
            
            # 如果包含日期或snapshot，需要修复
            if has_date_pattern or has_snapshot:
                fixed_count += 1  # 先计数
                if dry_run:
                    logger.info(
                        f"[DRY RUN] 将修复: file_id={file_record.id}, "
                        f"file_name={file_record.file_name}, "
                        f"platform={norm_platform}, domain={norm_domain}, "
                        f"old_shop_id={shop_id} → new_shop_id='none'"
                    )
                else:
                    # 实际修复
                    file_record.shop_id = 'none'
                    # 更新file_metadata
                    file_metadata = file_record.file_metadata or {}
                    if not isinstance(file_metadata, dict):
                        file_metadata = {}
                    file_metadata['shop_resolution'] = {
                        'confidence': 1.0,
                        'source': 'batch_fix_script',
                        'detail': f'v4.17.0批量修复：原shop_id包含日期（{shop_id}），统一为none',
                        'fixed_at': '2025-01-31',
                    }
                    file_record.file_metadata = file_metadata
                    
                    logger.info(
                        f"[FIXED] 已修复: file_id={file_record.id}, "
                        f"file_name={file_record.file_name}, "
                        f"old_shop_id={shop_id} → new_shop_id='none'"
                    )
            else:
                skipped_count += 1
        
        if not dry_run:
            session.commit()
            logger.info(f"[完成] 修复了 {fixed_count} 条记录，跳过了 {skipped_count} 条记录")
        else:
            logger.info(f"[DRY RUN] 将修复 {fixed_count} 条记录，跳过 {skipped_count} 条记录")
            logger.info("[提示] 运行脚本时添加 --execute 参数来实际执行修复")
        
        return fixed_count
        
    except Exception as e:
        session.rollback()
        logger.error(f"修复过程中出错: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量修复数据库中包含日期的 shop_id')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='实际执行修复（默认只显示将要修复的记录）'
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN 模式：只显示将要修复的记录，不实际修改")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("执行模式：将实际修改数据库")
        logger.info("=" * 60)
    
    try:
        fixed_count = fix_shop_id_with_dates(dry_run=dry_run)
        
        if dry_run and fixed_count > 0:
            print("\n" + "=" * 60)
            print(f"发现 {fixed_count} 条需要修复的记录")
            print("运行以下命令来实际执行修复：")
            print("  python scripts/fix_shop_id_with_dates.py --execute")
            print("=" * 60)
        elif not dry_run:
            print("\n" + "=" * 60)
            print(f"成功修复 {fixed_count} 条记录")
            print("=" * 60)
    except Exception as e:
        logger.error(f"脚本执行失败: {e}", exc_info=True)
        sys.exit(1)

