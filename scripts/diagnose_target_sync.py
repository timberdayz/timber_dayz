#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
目标数据同步诊断脚本

功能：
- 检查目标数据是否完整
- 检查同步状态
- 诊断同步问题
- 提供修复建议
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import get_async_db
from modules.core.db import SalesTarget, TargetBreakdown
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def check_target_data():
    """检查目标数据完整性"""
    print("=" * 60)
    print("目标数据同步诊断")
    print("=" * 60)
    
    async for db in get_async_db():
        try:
            # 1. 检查 sales_targets 表
            print("\n[1] 检查 sales_targets 表（目标主表）")
            targets = (await db.execute(
                select(SalesTarget).where(SalesTarget.status == "active")
            )).scalars().all()
            
            print(f"   - 活跃目标数量: {len(targets)}")
            for target in targets:
                print(f"     * ID={target.id}, 名称={target.target_name}, "
                      f"周期={target.period_start} ~ {target.period_end}, "
                      f"目标金额={target.target_amount}")
            
            # 2. 检查 target_breakdown 表
            print("\n[2] 检查 target_breakdown 表（目标分解表）")
            breakdowns = (await db.execute(
                select(TargetBreakdown).where(
                    TargetBreakdown.target_id.in_([t.id for t in targets])
                )
            )).scalars().all()
            
            print(f"   - 分解总数: {len(breakdowns)}")
            shop_breakdowns = [b for b in breakdowns if b.breakdown_type == "shop"]
            print(f"   - 店铺分解数: {len(shop_breakdowns)}")
            
            if shop_breakdowns:
                print("   - 店铺分解详情:")
                for bd in shop_breakdowns[:5]:  # 只显示前5个
                    print(f"     * Target ID={bd.target_id}, Shop={bd.shop_id}, "
                          f"Platform={bd.platform_code}, Amount={bd.target_amount}")
            
            # 3. 检查 a_class.sales_targets_a 表
            print("\n[3] 检查 a_class.sales_targets_a 表（A类目标聚合表）")
            result = await db.execute(text("""
                SELECT COUNT(*) as cnt FROM a_class.sales_targets_a
            """))
            a_class_count = result.scalar() or 0
            print(f"   - 记录数: {a_class_count}")
            
            if a_class_count > 0:
                result = await db.execute(text("""
                    SELECT "店铺ID", "年月", "目标销售额", "目标订单数"
                    FROM a_class.sales_targets_a
                    ORDER BY "年月" DESC, "店铺ID"
                    LIMIT 5
                """))
                print("   - 前5条记录:")
                for row in result:
                    print(f"     * 店铺ID={row[0]}, 年月={row[1]}, "
                          f"目标销售额={row[2]}, 目标订单数={row[3]}")
            else:
                print("   [WARNING] 表为空！")
            
            # 4. 检查同步状态
            print("\n[4] 检查同步状态")
            if len(shop_breakdowns) > 0 and a_class_count == 0:
                print("   [ERROR] 问题：有店铺分解数据，但 a_class.sales_targets_a 表为空")
                print("   [TIP] 建议：需要手动触发同步")
            elif len(shop_breakdowns) == 0:
                print("   [WARNING] 警告：目标没有店铺分解数据")
                print("   [TIP] 建议：需要在目标管理页面创建店铺分解")
            elif a_class_count > 0:
                print("   [OK] 同步状态正常")
            
            # 5. 检查字段名匹配
            print("\n[5] 检查字段名匹配")
            try:
                result = await db.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'a_class' 
                      AND table_name = 'sales_targets_a'
                    ORDER BY ordinal_position
                """))
                columns = result.fetchall()
                print("   - a_class.sales_targets_a 表字段:")
                for col in columns:
                    print(f"     * {col[0]} ({col[1]})")
                
                # 检查是否使用中文字段名
                column_names = [col[0] for col in columns]
                if "目标销售额" in column_names:
                    print("   [OK] 表使用中文字段名")
                elif "target_sales_amount" in column_names:
                    print("   [WARNING] 表使用英文字段名（可能与同步服务不匹配）")
            except Exception as e:
                print(f"   [ERROR] 检查字段名失败: {e}")
            
            # 6. 检查同步服务字段名
            print("\n[6] 检查同步服务使用的字段名")
            from backend.services.target_sync_service import TargetSyncService
            service = TargetSyncService(db)
            # 读取同步服务的SQL
            import inspect
            source = inspect.getsource(service._upsert_sales_target_a)
            if '"目标销售额"' in source or '"店铺ID"' in source:
                print("   [OK] 同步服务使用中文字段名")
            elif "target_sales_amount" in source or "shop_id" in source:
                print("   [WARNING] 同步服务使用英文字段名（可能与表结构不匹配）")
            
            # 7. 提供修复建议
            print("\n" + "=" * 60)
            print("诊断总结")
            print("=" * 60)
            
            issues = []
            if len(targets) == 0:
                issues.append("没有活跃目标")
            if len(shop_breakdowns) == 0:
                issues.append("目标没有店铺分解数据")
            if a_class_count == 0 and len(shop_breakdowns) > 0:
                issues.append("a_class.sales_targets_a 表为空，需要同步")
            
            if issues:
                print("发现的问题:")
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
                print("\n修复建议:")
                if "没有店铺分解数据" in str(issues):
                    print("  1. 在目标管理页面为目标创建店铺分解")
                if "需要同步" in str(issues):
                    print("  2. 运行同步脚本: python scripts/sync_all_targets.py")
                    print("  3. 或手动触发同步（见下方代码）")
            else:
                print("[OK] 未发现问题")
            
            break
        except Exception as e:
            logger.error(f"诊断失败: {e}", exc_info=True)
            print(f"\n[ERROR] 诊断失败: {e}")
            break


async def sync_all_targets():
    """同步所有活跃目标"""
    print("\n" + "=" * 60)
    print("开始同步所有活跃目标")
    print("=" * 60)
    
    async for db in get_async_db():
        try:
            from backend.services.target_sync_service import TargetSyncService
            service = TargetSyncService(db)
            result = await service.sync_all_active_targets()
            
            print(f"\n同步结果:")
            print(f"  - 总目标数: {result.get('total_targets', 0)}")
            print(f"  - 已同步目标数: {result.get('synced_targets', 0)}")
            print(f"  - 已同步记录数: {result.get('synced_records', 0)}")
            
            if result.get('errors'):
                print(f"  - 错误数: {len(result['errors'])}")
                for error in result['errors'][:5]:
                    print(f"    * {error}")
            
            break
        except Exception as e:
            logger.error(f"同步失败: {e}", exc_info=True)
            print(f"\n[ERROR] 同步失败: {e}")
            break


if __name__ == "__main__":
    import asyncio
    
    import argparse
    parser = argparse.ArgumentParser(description="目标数据同步诊断工具")
    parser.add_argument("--sync", action="store_true", help="执行同步操作")
    args = parser.parse_args()
    
    if args.sync:
        asyncio.run(sync_all_targets())
    else:
        asyncio.run(check_target_data())
