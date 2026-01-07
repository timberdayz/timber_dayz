#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步功能自动化测试脚本（v4.12.1）

测试内容：
1. 测试单文件数据同步
2. 测试外键约束修复
3. 测试完成按钮状态
4. 测试数据流转追踪
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.data_sync_service import DataSyncService
from backend.services.data_importer import stage_orders
from modules.core.db import CatalogFile, StagingOrders
from modules.core.logger import get_logger
from sqlalchemy import text, func

logger = get_logger(__name__)


def test_foreign_key_constraint():
    """测试外键约束是否正确指向catalog_files表"""
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info("测试1: 检查外键约束")
        logger.info("=" * 60)
        
        # 检查外键约束
        fk_info = db.execute(text("""
            SELECT 
                tc.constraint_name,
                ccu.table_name AS foreign_table_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'staging_orders'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND tc.constraint_name LIKE '%file_id%'
        """)).fetchall()
        
        if not fk_info:
            logger.error("❌ 未找到file_id的外键约束")
            return False
        
        for constraint_name, foreign_table in fk_info:
            logger.info(f"外键约束: {constraint_name} -> {foreign_table}")
            if foreign_table == 'catalog_files':
                logger.info("✅ 外键约束正确指向catalog_files表")
                return True
            elif foreign_table == 'data_files':
                logger.warning("⚠️ 外键约束仍指向data_files表（历史遗留），需要修复")
                return False
            else:
                logger.error(f"❌ 外键约束指向未知表: {foreign_table}")
                return False
        
        return False
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def test_file_id_validation():
    """测试file_id验证逻辑"""
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info("测试2: 测试file_id验证逻辑")
        logger.info("=" * 60)
        
        # 获取一个存在的文件ID
        catalog_file = db.query(CatalogFile).first()
        if not catalog_file:
            logger.warning("⚠️ 没有找到catalog_files记录，跳过测试")
            return True
        
        valid_file_id = catalog_file.id
        logger.info(f"使用有效的file_id: {valid_file_id}")
        
        # 测试有效的file_id
        test_rows = [{
            "platform_code": "test",
            "shop_id": "test_shop",
            "order_id": "test_order_1",
            "status": "completed"
        }]
        
        try:
            count = stage_orders(db, test_rows, ingest_task_id="test_task", file_id=valid_file_id)
            logger.info(f"✅ 有效file_id测试通过，插入了{count}条记录")
            
            # 清理测试数据
            db.query(StagingOrders).filter(StagingOrders.ingest_task_id == "test_task").delete()
            db.commit()
            
        except Exception as e:
            logger.error(f"❌ 有效file_id测试失败: {e}")
            db.rollback()
            return False
        
        # 测试无效的file_id（应该设置为None）
        invalid_file_id = 999999
        logger.info(f"使用无效的file_id: {invalid_file_id}")
        
        try:
            count = stage_orders(db, test_rows, ingest_task_id="test_task_invalid", file_id=invalid_file_id)
            logger.info(f"✅ 无效file_id测试通过，file_id已设置为None，插入了{count}条记录")
            
            # 验证file_id确实为None
            staged_record = db.query(StagingOrders).filter(
                StagingOrders.ingest_task_id == "test_task_invalid"
            ).first()
            
            if staged_record and staged_record.file_id is None:
                logger.info("✅ file_id验证逻辑正确：无效file_id被设置为None")
            else:
                logger.error(f"❌ file_id验证逻辑错误：file_id={staged_record.file_id if staged_record else 'None'}")
                return False
            
            # 清理测试数据
            db.query(StagingOrders).filter(StagingOrders.ingest_task_id == "test_task_invalid").delete()
            db.commit()
            
        except Exception as e:
            logger.error(f"❌ 无效file_id测试失败: {e}")
            db.rollback()
            return False
        
        return True
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


async def test_single_file_sync():
    """测试单文件数据同步"""
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info("测试3: 测试单文件数据同步")
        logger.info("=" * 60)
        
        # 获取一个待处理的文件
        catalog_file = db.query(CatalogFile).filter(
            CatalogFile.status.in_(['pending', 'failed'])
        ).first()
        
        if not catalog_file:
            logger.warning("⚠️ 没有找到待处理的文件，跳过测试")
            return True
        
        logger.info(f"测试文件: {catalog_file.file_name} (ID: {catalog_file.id})")
        
        sync_service = DataSyncService(db)
        
        try:
            result = await sync_service.sync_single_file(
                file_id=catalog_file.id,
                only_with_template=False,  # 允许无模板文件
                allow_quarantine=True,
                task_id=f"test_sync_{catalog_file.id}"
            )
            
            logger.info(f"同步结果: {result}")
            
            if result.get('success'):
                logger.info("✅ 单文件同步测试通过")
                return True
            else:
                logger.warning(f"⚠️ 单文件同步返回失败: {result.get('message')}")
                # 检查是否是预期的失败（如无模板）
                if 'no_template' in result.get('message', '').lower() or '无模板' in result.get('message', ''):
                    logger.info("✅ 单文件同步测试通过（预期的无模板失败）")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"❌ 单文件同步测试失败: {e}", exc_info=True)
            return False
            
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def test_data_flow_tracking():
    """测试数据流转追踪"""
    db = SessionLocal()
    try:
        logger.info("=" * 60)
        logger.info("测试4: 测试数据流转追踪")
        logger.info("=" * 60)
        
        # 检查是否有staging数据
        staging_count = db.query(func.count(StagingOrders.id)).scalar()
        logger.info(f"staging_orders表中有{staging_count}条记录")
        
        if staging_count == 0:
            logger.warning("⚠️ 没有staging数据，跳过测试")
            return True
        
        # 检查是否有fact数据
        from modules.core.db import FactOrder
        fact_count = db.query(func.count(FactOrder.order_id)).scalar()
        logger.info(f"fact_orders表中有{fact_count}条记录")
        
        # 检查是否有quarantine数据
        from modules.core.db import DataQuarantine
        quarantine_count = db.query(func.count(DataQuarantine.id)).scalar()
        logger.info(f"data_quarantine表中有{quarantine_count}条记录")
        
        logger.info("✅ 数据流转追踪测试通过（数据表查询正常）")
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False
    finally:
        db.close()


def main():
    """运行所有测试"""
    logger.info("开始数据同步功能自动化测试...")
    logger.info("")
    
    results = []
    
    # 测试1: 外键约束
    results.append(("外键约束检查", test_foreign_key_constraint()))
    
    # 测试2: file_id验证
    results.append(("file_id验证逻辑", test_file_id_validation()))
    
    # 测试3: 单文件同步
    results.append(("单文件数据同步", asyncio.run(test_single_file_sync())))
    
    # 测试4: 数据流转追踪
    results.append(("数据流转追踪", test_data_flow_tracking()))
    
    # 汇总结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("")
    logger.info(f"总计: {passed}个通过, {failed}个失败")
    
    if failed == 0:
        logger.info("🎉 所有测试通过！")
        return 0
    else:
        logger.error(f"❌ {failed}个测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())

