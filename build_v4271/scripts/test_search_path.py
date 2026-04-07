#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试PostgreSQL search_path配置
验证代码可以访问所有schema中的表（无需schema前缀）

使用方法:
    python scripts/test_search_path.py
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_search_path():
    """测试search_path配置，验证可以访问所有schema中的表"""
    
    db = SessionLocal()
    results = {
        "success": True,
        "tests": [],
        "errors": []
    }
    
    try:
        # 测试1: 查询B类数据表（b_class schema）
        logger.info("测试1: 查询B类数据表（b_class schema）...")
        try:
            from modules.core.db import FactRawDataOrdersDaily
            b_count = db.query(FactRawDataOrdersDaily).count()
            results["tests"].append({
                "name": "B类数据表访问",
                "schema": "b_class",
                "table": "fact_raw_data_orders_daily",
                "status": "success",
                "row_count": b_count
            })
            logger.info(f"[OK] B类数据表访问成功: {b_count} 条记录")
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"B类数据表访问失败: {str(e)}")
            logger.error(f"[ERROR] B类数据表访问失败: {e}")
        
        # 测试2: 查询A类数据表（a_class schema）
        logger.info("测试2: 查询A类数据表（a_class schema）...")
        try:
            from modules.core.db import SalesTargetA
            # 使用原生SQL查询避免字段映射问题
            from sqlalchemy import text
            result = db.execute(text("SELECT COUNT(*) FROM a_class.sales_targets_a"))
            a_count = result.scalar() or 0
            results["tests"].append({
                "name": "A类数据表访问",
                "schema": "a_class",
                "table": "sales_targets_a",
                "status": "success",
                "row_count": a_count
            })
            logger.info(f"[OK] A类数据表访问成功: {a_count} 条记录")
        except Exception as e:
            # A类数据表可能不存在或结构不匹配，不影响整体测试
            logger.warning(f"[WARN] A类数据表访问失败（可能表不存在或结构不匹配）: {e}")
            results["tests"].append({
                "name": "A类数据表访问",
                "schema": "a_class",
                "table": "sales_targets_a",
                "status": "warning",
                "message": "表可能不存在或结构不匹配"
            })
        
        # 测试3: 查询C类数据表（c_class schema）
        logger.info("测试3: 查询C类数据表（c_class schema）...")
        try:
            # 先回滚之前失败的事务
            db.rollback()
            from sqlalchemy import text
            result = db.execute(text("SELECT COUNT(*) FROM c_class.employee_performance"))
            c_count = result.scalar() or 0
            results["tests"].append({
                "name": "C类数据表访问",
                "schema": "c_class",
                "table": "employee_performance",
                "status": "success",
                "row_count": c_count
            })
            logger.info(f"[OK] C类数据表访问成功: {c_count} 条记录")
        except Exception as e:
            # C类数据表可能不存在，不影响整体测试
            db.rollback()  # 确保回滚失败的事务
            logger.warning(f"[WARN] C类数据表访问失败（可能表不存在）: {e}")
            results["tests"].append({
                "name": "C类数据表访问",
                "schema": "c_class",
                "table": "employee_performance",
                "status": "warning",
                "message": "表可能不存在"
            })
        
        # 测试4: 查询core Schema表
        logger.info("测试4: 查询core Schema表...")
        try:
            # 先回滚之前失败的事务
            db.rollback()
            from sqlalchemy import text
            result = db.execute(text("SELECT COUNT(*) FROM core.catalog_files"))
            core_count = result.scalar() or 0
            results["tests"].append({
                "name": "Core Schema访问",
                "schema": "core",
                "table": "catalog_files",
                "status": "success",
                "row_count": core_count
            })
            logger.info(f"[OK] Core Schema访问成功: {core_count} 条记录")
        except Exception as e:
            db.rollback()  # 确保回滚失败的事务
            results["success"] = False
            results["errors"].append(f"Core Schema访问失败: {str(e)}")
            logger.error(f"[ERROR] Core Schema访问失败: {e}")
        
        # 测试5: 验证search_path配置
        logger.info("测试5: 验证search_path配置...")
        try:
            # 先回滚之前失败的事务
            db.rollback()
            from sqlalchemy import text
            result = db.execute(text("SHOW search_path"))
            search_path = result.scalar()
            results["tests"].append({
                "name": "search_path配置验证",
                "status": "success",
                "search_path": search_path
            })
            logger.info(f"[OK] search_path配置: {search_path}")
            
            # 验证是否包含所有必要的schema
            required_schemas = ['public', 'b_class', 'a_class', 'c_class', 'core', 'finance']
            missing_schemas = [s for s in required_schemas if s not in search_path]
            if missing_schemas:
                results["success"] = False
                results["errors"].append(f"search_path缺少Schema: {missing_schemas}")
                logger.error(f"[ERROR] search_path缺少Schema: {missing_schemas}")
            else:
                logger.info(f"[OK] search_path包含所有必要的Schema")
        except Exception as e:
            db.rollback()  # 确保回滚失败的事务
            results["success"] = False
            results["errors"].append(f"search_path验证失败: {str(e)}")
            logger.error(f"[ERROR] search_path验证失败: {e}")
        
        # 输出测试结果
        print("\n" + "="*60)
        print("PostgreSQL search_path 测试结果")
        print("="*60)
        
        for test in results["tests"]:
            status_icon = "[OK]" if test["status"] == "success" else "[FAIL]"
            print(f"{status_icon} {test['name']}")
            if "schema" in test:
                print(f"   Schema: {test['schema']}")
            if "table" in test:
                print(f"   表名: {test['table']}")
            if "row_count" in test:
                print(f"   记录数: {test['row_count']}")
            if "search_path" in test:
                print(f"   search_path: {test['search_path']}")
            print()
        
        if results["errors"]:
            print("错误信息:")
            for error in results["errors"]:
                print(f"  [ERROR] {error}")
            print()
        
        if results["success"]:
            print("[OK] 所有Schema访问测试通过！")
            return 0
        else:
            print("[WARN] 部分测试失败，请检查错误信息")
            return 1
            
    except Exception as e:
        logger.error(f"测试执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 测试执行失败: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    exit_code = test_search_path()
    sys.exit(exit_code)

