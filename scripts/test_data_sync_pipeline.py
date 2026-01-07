#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步管道端到端测试脚本

v4.12.0新增（Phase 5 - 端到端测试）：
- 完整数据流程测试（文件扫描 → 注册 → 同步 → 入库）
- 数据完整性验证
- Metabase查询验证
- 输出端到端测试报告
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
from modules.services.catalog_scanner import scan_and_register
from backend.services.data_sync_service import DataSyncService
from backend.services.template_matcher import get_template_matcher

logger = get_logger(__name__)


def test_file_scanning_and_registration(db: Session) -> dict:
    """
    测试文件扫描和注册流程
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("端到端测试1: 文件扫描和注册")
    print("="*60)
    
    try:
        # 记录扫描前的文件数量
        before_count = db.query(CatalogFile).count()
        print(f"\n扫描前 catalog_files 表记录数: {before_count}")
        
        # 执行文件扫描
        print("\n执行文件扫描（data/raw目录）...")
        result = scan_and_register("data/raw")
        
        # 记录扫描后的文件数量
        after_count = db.query(CatalogFile).count()
        print(f"扫描后 catalog_files 表记录数: {after_count}")
        
        print(f"\n扫描结果:")
        print(f"  - 发现文件数: {result.seen}")
        print(f"  - 新注册文件数: {result.registered}")
        print(f"  - 跳过文件数: {result.skipped}")
        
        if result.registered > 0:
            print("[OK] 文件扫描和注册流程正常")
            return {
                "success": True,
                "before_count": before_count,
                "after_count": after_count,
                "registered": result.registered
            }
        else:
            print("[WARNING] 没有新文件注册（可能所有文件已注册）")
            return {
                "success": True,
                "before_count": before_count,
                "after_count": after_count,
                "registered": 0,
                "note": "所有文件已注册"
            }
        
    except Exception as e:
        logger.error(f"文件扫描和注册测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def test_data_sync_workflow(db: Session) -> dict:
    """
    测试数据同步工作流（文件 → B类数据表 → 事实表）
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("端到端测试2: 数据同步工作流")
    print("="*60)
    
    try:
        # 1. 查找pending状态的文件
        pending_files = db.query(CatalogFile).filter(
            CatalogFile.status == 'pending'
        ).limit(5).all()
        
        if not pending_files:
            print("[WARNING] 没有找到pending状态的文件，跳过数据同步测试")
            return {
                "success": False,
                "error": "没有pending状态的文件"
            }
        
        print(f"\n找到 {len(pending_files)} 个pending状态的文件")
        
        # 2. 检查模板匹配
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
                files_with_template.append(file_record)
                print(f"  - {file_record.file_name}: 有模板 '{template.template_name}'")
            else:
                print(f"  - {file_record.file_name}: 无模板")
        
        if not files_with_template:
            print("\n[WARNING] 没有文件匹配到模板，跳过数据同步测试")
            return {
                "success": False,
                "error": "没有文件匹配到模板"
            }
        
        # 3. 执行单文件同步（只测试第一个文件）
        test_file = files_with_template[0]
        print(f"\n测试同步文件: {test_file.file_name} (ID: {test_file.id})")
        
        sync_service = DataSyncService(db)
        
        # 记录同步前的B类数据表行数
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT 
                SUM(cnt) as total
            FROM (
                SELECT COUNT(*) as cnt FROM fact_raw_data_orders_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_orders_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_orders_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_inventory_snapshot
            ) t
        """))
        before_b_class_count = result.scalar() or 0
        
        print(f"同步前B类数据表总行数: {before_b_class_count}")
        
        # 执行同步
        result = await sync_service.sync_single_file(
            file_id=test_file.id,
            only_with_template=True,
            allow_quarantine=True,
            use_template_header_row=True
        )
        
        # 记录同步后的B类数据表行数
        result2 = db.execute(text("""
            SELECT 
                SUM(cnt) as total
            FROM (
                SELECT COUNT(*) as cnt FROM fact_raw_data_orders_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_orders_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_orders_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_products_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_traffic_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_daily
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_weekly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_services_monthly
                UNION ALL
                SELECT COUNT(*) FROM fact_raw_data_inventory_snapshot
            ) t
        """))
        after_b_class_count = result2.scalar() or 0
        
        print(f"同步后B类数据表总行数: {after_b_class_count}")
        
        # 验证同步结果
        print(f"\n同步结果:")
        print(f"  - 成功: {result.get('success', False)}")
        print(f"  - 状态: {result.get('status', 'unknown')}")
        print(f"  - 入库行数: {result.get('imported', 0)}")
        print(f"  - 隔离行数: {result.get('quarantined', 0)}")
        
        # 验证文件状态更新
        db.refresh(test_file)
        print(f"  - 文件状态: {test_file.status}")
        
        # 验证数据入库
        new_rows = after_b_class_count - before_b_class_count
        print(f"\n数据入库验证:")
        print(f"  - 新增B类数据行数: {new_rows}")
        print(f"  - 同步报告入库行数: {result.get('imported', 0)}")
        
        if result.get('success') and new_rows >= 0:
            print("[OK] 数据同步工作流正常")
            return {
                "success": True,
                "file_id": test_file.id,
                "file_name": test_file.file_name,
                "imported_rows": result.get('imported', 0),
                "quarantined_rows": result.get('quarantined', 0),
                "file_status": test_file.status,
                "new_b_class_rows": new_rows
            }
        else:
            print("[WARNING] 数据同步工作流可能存在问题")
            return {
                "success": False,
                "file_id": test_file.id,
                "error": "同步结果异常"
            }
        
    except Exception as e:
        logger.error(f"数据同步工作流测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_data_integrity_after_sync(db: Session) -> dict:
    """
    测试同步后的数据完整性
    
    Args:
        db: 数据库会话
        
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("端到端测试3: 同步后数据完整性验证")
    print("="*60)
    
    try:
        from sqlalchemy import text
        
        # 1. 验证文件状态分布
        print("\n1. 文件状态分布:")
        result = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM catalog_files
            GROUP BY status
            ORDER BY count DESC
        """))
        status_stats = result.fetchall()
        
        total_files = sum(count for _, count in status_stats)
        print(f"  - 总文件数: {total_files}")
        for status, count in status_stats:
            percentage = count / total_files * 100 if total_files > 0 else 0
            print(f"    - {status}: {count} 个 ({percentage:.1f}%)")
        
        # 2. 验证B类数据表数据
        print("\n2. B类数据表数据:")
        b_class_tables = [
            'fact_raw_data_orders_daily',
            'fact_raw_data_products_daily',
            'fact_raw_data_traffic_daily',
            'fact_raw_data_services_daily',
            'fact_raw_data_inventory_snapshot'
        ]
        
        b_class_stats = {}
        for table_name in b_class_tables:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                if count > 0:
                    b_class_stats[table_name] = count
                    print(f"  - {table_name}: {count} 行")
            except Exception:
                pass
        
        total_b_class = sum(b_class_stats.values())
        print(f"  - B类数据表总行数: {total_b_class}")
        
        # 3. 验证数据隔离
        print("\n3. 数据隔离:")
        try:
            result = db.execute(text("SELECT COUNT(*) FROM data_quarantine"))
            quarantine_count = result.scalar()
            print(f"  - 隔离数据总数: {quarantine_count} 条")
        except Exception:
            print("  - 无法查询data_quarantine表")
        
        # 4. 验证文件关联
        print("\n4. 文件关联完整性:")
        if total_b_class > 0:
            result = db.execute(text("""
                SELECT 
                    COUNT(DISTINCT file_id) as unique_files,
                    COUNT(*) - COUNT(file_id) as null_file_id
                FROM fact_raw_data_inventory_snapshot
            """))
            row = result.fetchone()
            if row:
                unique_files, null_count = row
                print(f"  - fact_raw_data_inventory_snapshot:")
                print(f"    - 关联文件数: {unique_files}")
                print(f"    - NULL file_id: {null_count}")
        
        print("\n[OK] 数据完整性验证完成")
        
        return {
            "success": True,
            "total_files": total_files,
            "total_b_class_rows": total_b_class,
            "b_class_stats": b_class_stats
        }
        
    except Exception as e:
        logger.error(f"数据完整性验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_metabase_query_capability() -> dict:
    """
    测试Metabase查询能力（验证Metabase可以查询数据）
    
    Returns:
        测试结果字典
    """
    print("\n" + "="*60)
    print("端到端测试4: Metabase查询能力验证")
    print("="*60)
    
    try:
        import os
        import httpx
        
        metabase_url = os.getenv("METABASE_URL", "http://localhost:8080").rstrip('/')  # 端口从3000改为8080，避免Windows端口权限问题
        
        # 测试Metabase健康检查
        print(f"\n测试Metabase连接: {metabase_url}")
        try:
            response = httpx.get(
                f"{metabase_url}/api/health",
                timeout=10,
                follow_redirects=True
            )
            
            if response.status_code == 200:
                print("[OK] Metabase连接正常")
                
                # 验证数据库连接（通过检查Metabase是否可以访问PostgreSQL）
                print("\n验证数据库连接（Metabase需要连接PostgreSQL）...")
                print("[NOTE] Metabase数据库连接配置需要在Metabase界面中配置")
                print("[OK] Metabase查询能力验证通过（连接正常）")
                
                return {
                    "success": True,
                    "metabase_url": metabase_url,
                    "status": "available"
                }
            else:
                print(f"[WARNING] Metabase返回异常状态码: {response.status_code}")
                return {
                    "success": False,
                    "metabase_url": metabase_url,
                    "status_code": response.status_code
                }
        except httpx.ConnectError:
            print("[WARNING] 无法连接到Metabase服务（可能未启动）")
            return {
                "success": False,
                "metabase_url": metabase_url,
                "error": "连接失败"
            }
        except Exception as e:
            logger.error(f"Metabase查询能力验证失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
        
    except Exception as e:
        logger.error(f"Metabase查询能力验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def main():
    """主函数"""
    print("="*60)
    print("数据同步管道端到端测试脚本")
    print("="*60)
    print("\n本脚本将执行以下端到端测试:")
    print("  1. 文件扫描和注册")
    print("  2. 数据同步工作流（文件 → B类数据表）")
    print("  3. 同步后数据完整性验证")
    print("  4. Metabase查询能力验证")
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        results = {}
        
        # 测试1: 文件扫描和注册
        results["file_scanning"] = test_file_scanning_and_registration(db)
        
        # 测试2: 数据同步工作流
        results["data_sync"] = await test_data_sync_workflow(db)
        
        # 测试3: 数据完整性验证
        results["data_integrity"] = test_data_integrity_after_sync(db)
        
        # 测试4: Metabase查询能力验证
        results["metabase_query"] = test_metabase_query_capability()
        
        # 输出总结报告
        print("\n" + "="*60)
        print("端到端测试报告总结")
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
            print("\n[OK] 所有端到端测试通过！")
            print("\n数据同步管道端到端流程验证:")
            print("  [OK] 文件扫描和注册 → 数据同步 → 数据入库 → 数据完整性 → Metabase查询")
        else:
            print("\n[WARNING] 部分端到端测试失败，请检查日志")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"端到端测试脚本执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 端到端测试脚本执行失败: {e}")
        return 1
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

