#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断Shopee订单文件问题

检查：
1. 数据库中Shopee订单文件的状态分布
2. 文件系统中有多少Shopee订单文件
3. 文件名是否符合规范
4. 为什么只显示1个文件
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
from modules.core.path_manager import get_data_raw_dir
from modules.core.logger import get_logger

logger = get_logger(__name__)


def diagnose_shopee_orders_issue():
    """诊断Shopee订单文件问题"""
    db = SessionLocal()
    
    try:
        print(f"\n{'='*80}")
        print(f"📊 Shopee订单文件问题诊断")
        print(f"{'='*80}\n")
        
        # 1. 检查数据库中Shopee订单文件的状态分布
        print(f"📋 数据库中Shopee订单文件状态分布:")
        status_query = db.query(
            CatalogFile.status,
            func.count(CatalogFile.id).label('count')
        ).filter(
            CatalogFile.platform_code == 'shopee',
            CatalogFile.data_domain == 'orders'
        ).group_by(CatalogFile.status).all()
        
        total_in_db = 0
        for status, count in status_query:
            print(f"   {status}: {count}个")
            total_in_db += count
        
        print(f"   总计: {total_in_db}个")
        print()
        
        # 2. 检查文件系统中有多少Shopee订单文件
        print(f"📋 文件系统中Shopee订单文件统计:")
        scan_dir = get_data_raw_dir()
        shopee_orders_files = []
        
        # 扫描年份目录
        for year_dir in scan_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
                for file_path in year_dir.rglob("*.*"):
                    if file_path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                        if file_path.suffix != '.json':
                            file_name_lower = file_path.name.lower()
                            # 检查是否是Shopee订单文件
                            if 'shopee' in file_name_lower and 'order' in file_name_lower:
                                shopee_orders_files.append(file_path)
        
        print(f"   扫描到的文件数: {len(shopee_orders_files)}个")
        if shopee_orders_files:
            print(f"   文件列表（前10个）:")
            for file_path in shopee_orders_files[:10]:
                print(f"     - {file_path.name}")
            if len(shopee_orders_files) > 10:
                print(f"     ... 还有 {len(shopee_orders_files) - 10} 个文件")
        print()
        
        # 3. 检查数据库中pending状态的Shopee订单文件
        print(f"📋 数据库中pending状态的Shopee订单文件:")
        pending_files = db.query(CatalogFile).filter(
            CatalogFile.platform_code == 'shopee',
            CatalogFile.data_domain == 'orders',
            CatalogFile.status == 'pending'
        ).all()
        
        print(f"   pending状态文件数: {len(pending_files)}个")
        if pending_files:
            print(f"   文件列表（前10个）:")
            for file_record in pending_files[:10]:
                print(f"     - {file_record.file_name} (ID: {file_record.id}, 状态: {file_record.status})")
            if len(pending_files) > 10:
                print(f"     ... 还有 {len(pending_files) - 10} 个文件")
        print()
        
        # 4. 检查needs_shop状态的Shopee订单文件
        print(f"📋 数据库中needs_shop状态的Shopee订单文件:")
        needs_shop_files = db.query(CatalogFile).filter(
            CatalogFile.platform_code == 'shopee',
            CatalogFile.data_domain == 'orders',
            CatalogFile.status == 'needs_shop'
        ).all()
        
        print(f"   needs_shop状态文件数: {len(needs_shop_files)}个")
        if needs_shop_files:
            print(f"   文件列表（前10个）:")
            for file_record in needs_shop_files[:10]:
                print(f"     - {file_record.file_name} (ID: {file_record.id}, 状态: {file_record.status})")
            if len(needs_shop_files) > 10:
                print(f"     ... 还有 {len(needs_shop_files) - 10} 个文件")
        print()
        
        # 5. 检查文件路径匹配
        # v4.18.0: 使用相对路径，与数据库存储格式一致
        print(f"📋 文件路径匹配检查:")
        matched_count = 0
        unmatched_files = []
        
        for file_path in shopee_orders_files:
            relative_path = str(file_path)  # 保持相对路径格式
            # 检查数据库中是否有这个文件
            db_file = db.query(CatalogFile).filter(
                CatalogFile.file_path == relative_path
            ).first()
            
            if db_file:
                matched_count += 1
            else:
                unmatched_files.append(file_path.name)
        
        print(f"   匹配的文件数: {matched_count}个")
        print(f"   未匹配的文件数: {len(unmatched_files)}个")
        if unmatched_files:
            print(f"   未匹配的文件列表（前10个）:")
            for file_name in unmatched_files[:10]:
                print(f"     - {file_name}")
            if len(unmatched_files) > 10:
                print(f"     ... 还有 {len(unmatched_files) - 10} 个文件")
        print()
        
        # 6. 检查文件名解析
        print(f"📋 文件名解析检查:")
        from modules.core.file_naming import StandardFileName
        
        parse_success = 0
        parse_failed = []
        
        for file_path in shopee_orders_files[:20]:  # 只检查前20个
            try:
                file_metadata = StandardFileName.parse(file_path.name)
                platform = file_metadata.get('source_platform', '').lower()
                domain = file_metadata.get('data_domain', '').lower()
                
                if platform == 'shopee' and domain == 'orders':
                    parse_success += 1
                else:
                    parse_failed.append((file_path.name, f"platform={platform}, domain={domain}"))
            except Exception as e:
                parse_failed.append((file_path.name, f"解析失败: {str(e)}"))
        
        print(f"   解析成功: {parse_success}个")
        print(f"   解析失败或不符合: {len(parse_failed)}个")
        if parse_failed:
            print(f"   失败详情（前10个）:")
            for file_name, reason in parse_failed[:10]:
                print(f"     - {file_name}: {reason}")
        print()
        
        # 7. 总结
        print(f"{'='*80}")
        print(f"📊 诊断总结")
        print(f"{'='*80}")
        print(f"文件系统中Shopee订单文件: {len(shopee_orders_files)}个")
        print(f"数据库中Shopee订单文件总数: {total_in_db}个")
        print(f"数据库中pending状态: {len(pending_files)}个")
        print(f"数据库中needs_shop状态: {len(needs_shop_files)}个")
        print(f"文件路径匹配: {matched_count}/{len(shopee_orders_files)}个")
        print()
        
        # 8. 问题分析
        print(f"🔍 问题分析:")
        if len(pending_files) == 1:
            print(f"   ⚠️  问题确认：数据库中只有1个pending状态的Shopee订单文件")
            print(f"   💡 可能原因：")
            print(f"      1. 其他文件的状态是needs_shop（{len(needs_shop_files)}个）")
            print(f"      2. 其他文件的状态是ingested（已同步）")
            print(f"      3. 其他文件的状态是failed或其他状态")
            print(f"   💡 解决方案：")
            print(f"      1. 前端筛选条件改为包含needs_shop状态")
            print(f"      2. 或者修改后端统计逻辑，包含needs_shop状态")
        
        if len(unmatched_files) > 0:
            print(f"   ⚠️  发现未匹配的文件: {len(unmatched_files)}个")
            print(f"   💡 可能原因：文件还未注册到数据库，需要重新扫描")
        
        print(f"{'='*80}\n")
        
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)
        print(f"\n❌ 诊断失败: {e}\n")
    finally:
        db.close()


if __name__ == "__main__":
    diagnose_shopee_orders_issue()

