#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据修复脚本：为历史订单明细数据关联product_id

用途：
- 为fact_order_items表中product_id为NULL的历史数据关联product_id
- 通过BridgeProductKeys查找对应的product_id
- 支持批量修复和增量修复

使用方法：
    python scripts/fix_historical_product_id_association.py [--batch-size=1000] [--dry-run]
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import select, update, func
from backend.models.database import get_db
from modules.core.db import FactOrderItem, BridgeProductKeys
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """Windows兼容的安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def fix_product_id_association(
    db: Session,
    batch_size: int = 1000,
    dry_run: bool = False
) -> dict:
    """
    为历史订单明细数据关联product_id
    
    Args:
        db: 数据库会话
        batch_size: 批量处理大小
        dry_run: 是否只检查不更新
    
    Returns:
        修复统计信息
    """
    stats = {
        'total_items': 0,
        'items_without_product_id': 0,
        'items_fixed': 0,
        'items_not_found': 0,
        'errors': 0
    }
    
    try:
        # 1. 统计需要修复的数据量
        safe_print("=" * 70)
        safe_print("开始修复历史订单明细的product_id关联")
        safe_print("=" * 70)
        
        total_query = select(FactOrderItem).where(FactOrderItem.product_id.is_(None))
        total_count = db.execute(select(func.count()).select_from(total_query.subquery())).scalar()
        stats['items_without_product_id'] = total_count
        
        safe_print(f"\n[1] 统计信息:")
        safe_print(f"  - 总订单明细数: {stats['total_items']}")
        safe_print(f"  - 缺少product_id的记录数: {stats['items_without_product_id']}")
        
        if stats['items_without_product_id'] == 0:
            safe_print("\n[OK] 所有订单明细都已关联product_id，无需修复")
            return stats
        
        if dry_run:
            safe_print("\n[DRY RUN] 仅检查，不更新数据")
            return stats
        
        # 2. 批量修复
        safe_print(f"\n[2] 开始批量修复（批量大小: {batch_size}）...")
        
        offset = 0
        while True:
            # 查询一批需要修复的记录
            items_query = select(FactOrderItem).where(
                FactOrderItem.product_id.is_(None)
            ).limit(batch_size).offset(offset)
            
            items = db.execute(items_query).scalars().all()
            
            if not items:
                break
            
            safe_print(f"\n  处理第 {offset + 1} - {offset + len(items)} 条记录...")
            
            fixed_count = 0
            not_found_count = 0
            
            for item in items:
                try:
                    # 查找对应的product_id
                    bridge = db.query(BridgeProductKeys).filter(
                        BridgeProductKeys.platform_code == item.platform_code,
                        BridgeProductKeys.shop_id == item.shop_id,
                        BridgeProductKeys.platform_sku == item.platform_sku
                    ).first()
                    
                    if bridge:
                        # 更新product_id
                        db.execute(
                            update(FactOrderItem)
                            .where(
                                FactOrderItem.platform_code == item.platform_code,
                                FactOrderItem.shop_id == item.shop_id,
                                FactOrderItem.order_id == item.order_id,
                                FactOrderItem.platform_sku == item.platform_sku
                            )
                            .values(product_id=bridge.product_id)
                        )
                        fixed_count += 1
                    else:
                        not_found_count += 1
                        logger.debug(
                            f"未找到product_id: platform_code={item.platform_code}, "
                            f"shop_id={item.shop_id}, platform_sku={item.platform_sku}"
                        )
                except Exception as e:
                    stats['errors'] += 1
                    logger.warning(
                        f"修复失败: order_id={item.order_id}, platform_sku={item.platform_sku}, error={e}",
                        exc_info=True
                    )
            
            # 提交批量更新
            db.commit()
            
            stats['items_fixed'] += fixed_count
            stats['items_not_found'] += not_found_count
            
            safe_print(f"  - 已修复: {fixed_count} 条")
            safe_print(f"  - 未找到: {not_found_count} 条")
            
            offset += batch_size
            
            if len(items) < batch_size:
                break
        
        # 3. 输出统计信息
        safe_print("\n" + "=" * 70)
        safe_print("修复完成统计")
        safe_print("=" * 70)
        safe_print(f"  - 缺少product_id的记录数: {stats['items_without_product_id']}")
        safe_print(f"  - 已修复记录数: {stats['items_fixed']}")
        safe_print(f"  - 未找到product_id的记录数: {stats['items_not_found']}")
        safe_print(f"  - 错误数: {stats['errors']}")
        safe_print("=" * 70)
        
    except Exception as e:
        db.rollback()
        logger.error(f"修复过程出错: {e}", exc_info=True)
        raise
    
    return stats


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='为历史订单明细数据关联product_id')
    parser.add_argument('--batch-size', type=int, default=1000, help='批量处理大小（默认: 1000）')
    parser.add_argument('--dry-run', action='store_true', help='仅检查，不更新数据')
    
    args = parser.parse_args()
    
    db = next(get_db())
    try:
        stats = fix_product_id_association(
            db=db,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
        
        if args.dry_run:
            safe_print("\n[DRY RUN] 检查完成，未更新数据")
        else:
            safe_print("\n[OK] 修复完成")
        
        return 0
    except Exception as e:
        safe_print(f"\n[ERROR] 修复失败: {e}")
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())

