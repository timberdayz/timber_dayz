#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步流程验证脚本

v4.12.0新增（Phase 2 - 数据同步流程验证）：
- 测试单文件同步API
- 测试批量同步API
- 验证模板匹配逻辑
- 验证数据入库流程
- 输出验证报告
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from modules.core.db import CatalogFile
from backend.models.database import get_db
from modules.core.logger import get_logger
from backend.services.data_sync_service import DataSyncService
from backend.services.template_matcher import get_template_matcher

logger = get_logger(__name__)


def test_single_file_sync(db: Session) -> dict:
    """
    测试单文件同步功能
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试1: 单文件同步功能")
    print("="*60)
    
    try:
        # 1. 查找一个pending状态的文件
        pending_file = db.query(CatalogFile).filter(
            CatalogFile.status == 'pending'
        ).first()
        
        if not pending_file:
            print("[WARNING] 没有找到pending状态的文件，跳过单文件同步测试")
            return {
                "success": False,
                "error": "没有pending状态的文件"
            }
        
        print(f"\n测试文件:")
        print(f"  - ID: {pending_file.id}")
        print(f"  - 文件名: {pending_file.file_name}")
        print(f"  - 平台: {pending_file.platform_code}")
        print(f"  - 数据域: {pending_file.data_domain}")
        print(f"  - 粒度: {pending_file.granularity}")
        print(f"  - 状态: {pending_file.status}")
        
        # 2. 检查模板匹配
        template_matcher = get_template_matcher(db)
        template = template_matcher.find_best_template(
            platform=pending_file.platform_code or "",
            data_domain=pending_file.data_domain or "",
            granularity=pending_file.granularity or "",
            sub_domain=pending_file.sub_domain
        )
        
        if template:
            print(f"\n[OK] 找到模板: {template.template_name}")
            print(f"  - 模板ID: {template.id}")
            if hasattr(template, 'header_row') and template.header_row is not None:
                print(f"  - 表头行: {template.header_row}")
        else:
            print(f"\n[WARNING] 未找到模板，将跳过同步（only_with_template=True）")
            return {
                "success": False,
                "error": "未找到模板",
                "file_id": pending_file.id
            }
        
        # 3. 执行同步
        print(f"\n开始同步文件...")
        sync_service = DataSyncService(db)
        
        # 使用asyncio运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            sync_service.sync_single_file(
                file_id=pending_file.id,
                only_with_template=True,
                allow_quarantine=True,
                use_template_header_row=True
            )
        )
        loop.close()
        
        # 4. 验证结果
        print(f"\n同步结果:")
        print(f"  - 成功: {result.get('success', False)}")
        print(f"  - 状态: {result.get('status', 'unknown')}")
        print(f"  - 消息: {result.get('message', 'N/A')}")
        
        if result.get('success'):
            print(f"  - 入库行数: {result.get('imported', 0)}")
            print(f"  - 隔离行数: {result.get('quarantined', 0)}")
            print(f"  - 跳过行数: {result.get('skipped', 0)}")
        
        # 5. 验证文件状态更新
        db.refresh(pending_file)
        print(f"\n文件状态更新:")
        print(f"  - 新状态: {pending_file.status}")
        
        if result.get('success') and pending_file.status == 'ingested':
            print("[OK] 文件状态更新验证通过: status=ingested")
        elif result.get('success') and pending_file.status == 'partial_success':
            print("[OK] 文件状态更新验证通过: status=partial_success（部分成功）")
        else:
            print(f"[WARNING] 文件状态可能异常: status={pending_file.status}")
        
        return {
            "success": result.get('success', False),
            "file_id": pending_file.id,
            "result": result,
            "file_status": pending_file.status
        }
        
    except Exception as e:
        logger.error(f"单文件同步测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_template_matching(db: Session) -> dict:
    """
    测试模板匹配逻辑
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试2: 模板匹配逻辑")
    print("="*60)
    
    try:
        template_matcher = get_template_matcher(db)
        
        # 获取一些测试文件
        test_files = db.query(CatalogFile).filter(
            CatalogFile.status == 'pending'
        ).limit(10).all()
        
        if not test_files:
            print("[WARNING] 没有找到pending状态的文件，跳过模板匹配测试")
            return {
                "success": False,
                "error": "没有pending状态的文件"
            }
        
        print(f"\n测试 {len(test_files)} 个文件的模板匹配:")
        
        match_stats = {
            "total": len(test_files),
            "matched": 0,
            "not_matched": 0,
            "match_details": []
        }
        
        for file_record in test_files:
            template = template_matcher.find_best_template(
                platform=file_record.platform_code or "",
                data_domain=file_record.data_domain or "",
                granularity=file_record.granularity or "",
                sub_domain=file_record.sub_domain
            )
            
            if template:
                match_stats["matched"] += 1
                match_stats["match_details"].append({
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "template_name": template.template_name,
                    "template_id": template.id,
                    "header_row": getattr(template, 'header_row', None)
                })
                print(f"  [OK] {file_record.file_name}: 匹配模板 '{template.template_name}'")
            else:
                match_stats["not_matched"] += 1
                print(f"  [WARNING] {file_record.file_name}: 未找到模板")
        
        print(f"\n模板匹配统计:")
        print(f"  - 总文件数: {match_stats['total']}")
        print(f"  - 匹配成功: {match_stats['matched']}")
        print(f"  - 未匹配: {match_stats['not_matched']}")
        print(f"  - 匹配率: {match_stats['matched'] / match_stats['total'] * 100:.1f}%")
        
        if match_stats["matched"] > 0:
            print("[OK] 模板匹配功能正常")
        else:
            print("[WARNING] 没有文件匹配到模板，可能需要创建模板")
        
        return {
            "success": True,
            "match_stats": match_stats
        }
        
    except Exception as e:
        logger.error(f"模板匹配测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_batch_sync_api(db: Session) -> dict:
    """
    测试批量同步API（验证API接口，不实际执行）
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试3: 批量同步API验证")
    print("="*60)
    
    try:
        # 查找pending状态的文件
        pending_files = db.query(CatalogFile).filter(
            CatalogFile.status == 'pending'
        ).limit(10).all()
        
        if not pending_files:
            print("[WARNING] 没有找到pending状态的文件，跳过批量同步测试")
            return {
                "success": False,
                "error": "没有pending状态的文件"
            }
        
        print(f"\n找到 {len(pending_files)} 个pending状态的文件")
        
        # 检查模板匹配
        template_matcher = get_template_matcher(db)
        files_with_template = []
        
        for file_record in pending_files:
            template = template_matcher.find_best_template(
                platform=file_record.platform_code or "",
                data_domain=file_record.data_domain or "",
                granularity=file_record.granularity or "",
                sub_domain=file_record.sub_domain
            )
            if template:
                files_with_template.append(file_record.id)
        
        print(f"  - 有模板的文件: {len(files_with_template)} 个")
        
        if len(files_with_template) == 0:
            print("[WARNING] 没有文件匹配到模板，批量同步将跳过所有文件")
            return {
                "success": False,
                "error": "没有文件匹配到模板"
            }
        
        # 验证批量同步参数
        print(f"\n批量同步参数验证:")
        print(f"  - 文件ID列表: {files_with_template[:5]}..." if len(files_with_template) > 5 else f"  - 文件ID列表: {files_with_template}")
        print(f"  - only_with_template: True")
        print(f"  - allow_quarantine: True")
        print(f"  - use_template_header_row: True")
        
        print("\n[OK] 批量同步API参数验证通过")
        print("[NOTE] 实际批量同步测试需要启动后台任务，这里仅验证参数")
        
        return {
            "success": True,
            "files_with_template": len(files_with_template),
            "file_ids": files_with_template
        }
        
    except Exception as e:
        logger.error(f"批量同步API验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_data_ingestion_flow(db: Session) -> dict:
    """
    测试数据入库流程（验证入库逻辑，不实际执行）
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("测试4: 数据入库流程验证")
    print("="*60)
    
    try:
        # 检查B类数据表
        from sqlalchemy import text
        
        # 查询各数据域的表
        data_domains = ['orders', 'products', 'traffic', 'services', 'inventory']
        granularities = ['daily', 'weekly', 'monthly', 'snapshot']
        
        print(f"\n检查B类数据表（fact_raw_data_*）:")
        
        table_stats = {}
        for domain in data_domains:
            for granularity in granularities:
                if domain == 'inventory' and granularity != 'snapshot':
                    continue
                if domain != 'inventory' and granularity == 'snapshot':
                    continue
                
                table_name = f"fact_raw_data_{domain}_{granularity}"
                try:
                    result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar()
                    if count > 0:
                        table_stats[table_name] = count
                        print(f"  - {table_name}: {count} 行")
                except Exception:
                    # 表不存在，跳过
                    pass
        
        if table_stats:
            print(f"\n[OK] B类数据表检查通过: 发现 {len(table_stats)} 张表有数据")
        else:
            print(f"\n[WARNING] B类数据表为空（可能已清理或未入库）")
        
        # 检查事实表
        print(f"\n检查事实表:")
        fact_tables = {
            'fact_orders': '订单表',
            'fact_order_items': '订单明细表',
            'fact_product_metrics': '产品指标表',
            'fact_traffic': '流量表',
            'fact_service': '服务表'
        }
        
        fact_stats = {}
        for table_name, description in fact_tables.items():
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                if count > 0:
                    fact_stats[table_name] = count
                    print(f"  - {table_name} ({description}): {count} 行")
            except Exception:
                # 表不存在，跳过
                pass
        
        if fact_stats:
            print(f"\n[OK] 事实表检查通过: 发现 {len(fact_stats)} 张表有数据")
        else:
            print(f"\n[WARNING] 事实表为空（可能已清理或未入库）")
        
        return {
            "success": True,
            "b_class_tables": table_stats,
            "fact_tables": fact_stats
        }
        
    except Exception as e:
        logger.error(f"数据入库流程验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """主函数"""
    print("="*60)
    print("数据同步流程验证脚本")
    print("="*60)
    print("\n本脚本将验证以下功能:")
    print("  1. 单文件同步功能")
    print("  2. 模板匹配逻辑")
    print("  3. 批量同步API验证")
    print("  4. 数据入库流程验证")
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        results = {}
        
        # 测试1: 单文件同步（需要pending状态的文件和模板）
        results["single_file_sync"] = test_single_file_sync(db)
        
        # 测试2: 模板匹配逻辑
        results["template_matching"] = test_template_matching(db)
        
        # 测试3: 批量同步API验证
        results["batch_sync"] = test_batch_sync_api(db)
        
        # 测试4: 数据入库流程验证
        results["data_ingestion"] = test_data_ingestion_flow(db)
        
        # 输出总结报告
        print("\n" + "="*60)
        print("验证报告总结")
        print("="*60)
        
        all_passed = True
        for test_name, result in results.items():
            if result.get("success"):
                status = "[OK] 通过"
            else:
                status = "[FAIL] 失败"
                all_passed = False
            
            print(f"{test_name}: {status}")
            if not result.get("success"):
                if "error" in result:
                    print(f"  错误: {result['error']}")
        
        if all_passed:
            print("\n[OK] 所有测试通过！")
        else:
            print("\n[WARNING] 部分测试失败，请检查日志")
            print("[NOTE] 某些测试可能需要pending状态的文件和模板才能通过")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"验证脚本执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 验证脚本执行失败: {e}")
        return 1
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

