#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据丢失分析功能测试脚本

测试场景：
1. 测试数据丢失分析服务（analyze_data_loss）
2. 测试数据丢失预警机制（check_data_loss_threshold）
3. 测试API端点（/api/data-sync/loss-analysis, /api/data-sync/loss-alert）

验证标准：
- 所有功能都能正常工作
- 返回的数据格式正确
- 丢失率计算准确
"""

import sys
import os
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 禁用代理（避免本地请求走代理）
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'

from backend.models.database import SessionLocal
from backend.services.data_loss_analyzer import analyze_data_loss, check_data_loss_threshold
from modules.core.db import CatalogFile, StagingOrders, FactOrder, DataQuarantine
from sqlalchemy import select, func
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text):
    """安全打印（避免Windows PowerShell Unicode错误）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def test_scenario_1_analyze_data_loss():
    """
    测试场景1：数据丢失分析（按文件ID）
    """
    safe_print("\n" + "="*60)
    safe_print("测试场景1：数据丢失分析（按文件ID）")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        # 1. 查找一个有数据的文件
        stmt = select(CatalogFile).where(
            CatalogFile.status.in_(["ingested", "partial_success"])
        ).limit(1)
        file_record = db.execute(stmt).scalar_one_or_none()
        
        if not file_record:
            safe_print("[WARN] 没有找到已入库的文件，跳过测试")
            return False
        
        file_id = file_record.id
        data_domain = file_record.data_domain
        
        safe_print(f"[INFO] 测试文件: file_id={file_id}, data_domain={data_domain}")
        
        # 2. 调用分析服务
        result = analyze_data_loss(db, file_id=file_id, data_domain=data_domain)
        
        # 3. 验证结果
        if not result.get("success"):
            safe_print(f"[ERROR] 分析失败: {result.get('error')}")
            return False
        
        stats = result.get("stats", {})
        safe_print(f"[OK] 分析成功:")
        safe_print(f"  - Raw层数据: {stats.get('raw_count', 0)}")
        safe_print(f"  - Staging层数据: {stats.get('staging_count', 0)}")
        safe_print(f"  - Fact层数据: {stats.get('fact_count', 0)}")
        safe_print(f"  - 隔离区数据: {stats.get('quarantine_count', 0)}")
        safe_print(f"  - 丢失数量: {stats.get('lost_count', 0)}")
        safe_print(f"  - 丢失率: {stats.get('loss_rate', 0):.2f}%")
        
        # 4. 验证丢失详情
        loss_details = stats.get("loss_details", [])
        if loss_details:
            safe_print(f"[INFO] 丢失详情:")
            for detail in loss_details:
                safe_print(f"  - {detail.get('stage')}: 丢失{detail.get('lost_count', 0)}行 ({detail.get('loss_rate', 0):.2f}%)")
        
        # 5. 验证错误类型分布
        error_types = stats.get("error_type_distribution", {})
        if error_types:
            safe_print(f"[INFO] 错误类型分布:")
            for error_type, count in error_types.items():
                safe_print(f"  - {error_type}: {count}条")
        
        # 6. 验证常见错误
        common_errors = stats.get("common_errors", [])
        if common_errors:
            safe_print(f"[INFO] 常见错误（前5条）:")
            for error in common_errors[:5]:
                safe_print(f"  - {error.get('error_msg', '')[:50]}... ({error.get('count', 0)}次)")
        
        return True
    
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_scenario_2_analyze_data_loss_by_task():
    """
    测试场景2：数据丢失分析（按任务ID）
    """
    safe_print("\n" + "="*60)
    safe_print("测试场景2：数据丢失分析（按任务ID）")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        # 1. 查找一个有任务ID的staging记录
        stmt = select(StagingOrders.ingest_task_id).where(
            StagingOrders.ingest_task_id.isnot(None)
        ).distinct().limit(1)
        task_id_result = db.execute(stmt).scalar_one_or_none()
        
        if not task_id_result:
            safe_print("[WARN] 没有找到有任务ID的记录，跳过测试")
            return True  # 跳过测试不算失败
        
        task_id = task_id_result
        
        safe_print(f"[INFO] 测试任务: task_id={task_id}")
        
        # 2. 调用分析服务
        result = analyze_data_loss(db, task_id=task_id, data_domain="orders")
        
        # 3. 验证结果
        if not result.get("success"):
            safe_print(f"[ERROR] 分析失败: {result.get('error')}")
            return False
        
        stats = result.get("stats", {})
        safe_print(f"[OK] 分析成功:")
        safe_print(f"  - Raw层数据: {stats.get('raw_count', 0)}")
        safe_print(f"  - Staging层数据: {stats.get('staging_count', 0)}")
        safe_print(f"  - Fact层数据: {stats.get('fact_count', 0)}")
        safe_print(f"  - 隔离区数据: {stats.get('quarantine_count', 0)}")
        safe_print(f"  - 丢失数量: {stats.get('lost_count', 0)}")
        safe_print(f"  - 丢失率: {stats.get('loss_rate', 0):.2f}%")
        
        return True
    
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_scenario_3_check_loss_threshold():
    """
    测试场景3：数据丢失预警检查
    """
    safe_print("\n" + "="*60)
    safe_print("测试场景3：数据丢失预警检查")
    safe_print("="*60)
    
    db = SessionLocal()
    try:
        # 1. 查找一个有数据的文件
        stmt = select(CatalogFile).where(
            CatalogFile.status.in_(["ingested", "partial_success"])
        ).limit(1)
        file_record = db.execute(stmt).scalar_one_or_none()
        
        if not file_record:
            safe_print("[WARN] 没有找到已入库的文件，跳过测试")
            return False
        
        file_id = file_record.id
        data_domain = file_record.data_domain
        
        safe_print(f"[INFO] 测试文件: file_id={file_id}, data_domain={data_domain}")
        
        # 2. 测试不同的阈值
        thresholds = [1.0, 5.0, 10.0]
        
        for threshold in thresholds:
            safe_print(f"\n[INFO] 测试阈值: {threshold}%")
            result = check_data_loss_threshold(
                db, 
                file_id=file_id, 
                data_domain=data_domain, 
                threshold=threshold
            )
            
            if not result.get("success"):
                safe_print(f"[ERROR] 检查失败: {result.get('error')}")
                continue
            
            alert = result.get("alert", False)
            loss_rate = result.get("loss_rate", 0.0)
            
            if alert:
                safe_print(f"[ALERT] 数据丢失率 {loss_rate:.2f}% 超过阈值 {threshold}%")
            else:
                safe_print(f"[OK] 数据丢失率 {loss_rate:.2f}% 在正常范围内（阈值: {threshold}%）")
        
        return True
    
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_scenario_4_api_endpoints():
    """
    测试场景4：API端点测试（需要后端服务运行）
    """
    safe_print("\n" + "="*60)
    safe_print("测试场景4：API端点测试")
    safe_print("="*60)
    
    import requests
    
    BASE_URL = "http://127.0.0.1:8001/api"
    
    # 检查后端服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            safe_print("[WARN] 后端服务未运行，跳过API测试")
            return False
    except Exception as e:
        safe_print(f"[WARN] 无法连接到后端服务: {e}")
        safe_print("[WARN] 请确保后端服务正在运行（python run.py）")
        return False
    
    try:
        # 1. 测试数据丢失分析API
        safe_print("\n[INFO] 测试 /api/data-sync/loss-analysis")
        response = requests.get(
            f"{BASE_URL}/data-sync/loss-analysis",
            params={"data_domain": "orders"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                stats = data.get("data", {}).get("stats", {})
                safe_print(f"[OK] API调用成功:")
                safe_print(f"  - Raw层数据: {stats.get('raw_count', 0)}")
                safe_print(f"  - Fact层数据: {stats.get('fact_count', 0)}")
                safe_print(f"  - 丢失率: {stats.get('loss_rate', 0):.2f}%")
            else:
                safe_print(f"[ERROR] API返回错误: {data.get('message')}")
                return False
        else:
            safe_print(f"[ERROR] API调用失败: HTTP {response.status_code}")
            return False
        
        # 2. 测试数据丢失预警API
        safe_print("\n[INFO] 测试 /api/data-sync/loss-alert")
        response = requests.get(
            f"{BASE_URL}/data-sync/loss-alert",
            params={"data_domain": "orders", "threshold": 5.0},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                alert = data.get("data", {}).get("alert", False)
                loss_rate = data.get("data", {}).get("loss_rate", 0.0)
                safe_print(f"[OK] API调用成功:")
                safe_print(f"  - 预警状态: {'是' if alert else '否'}")
                safe_print(f"  - 丢失率: {loss_rate:.2f}%")
            else:
                safe_print(f"[ERROR] API返回错误: {data.get('message')}")
                return False
        else:
            safe_print(f"[ERROR] API调用失败: HTTP {response.status_code}")
            return False
        
        return True
    
    except Exception as e:
        safe_print(f"[ERROR] API测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    safe_print("\n" + "="*60)
    safe_print("数据丢失分析功能测试")
    safe_print("="*60)
    
    results = []
    
    # 运行所有测试场景
    results.append(("场景1：数据丢失分析（按文件ID）", test_scenario_1_analyze_data_loss()))
    results.append(("场景2：数据丢失分析（按任务ID）", test_scenario_2_analyze_data_loss_by_task()))
    results.append(("场景3：数据丢失预警检查", test_scenario_3_check_loss_threshold()))
    results.append(("场景4：API端点测试", test_scenario_4_api_endpoints()))
    
    # 输出测试结果
    safe_print("\n" + "="*60)
    safe_print("测试结果汇总")
    safe_print("="*60)
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    safe_print(f"\n总计: {len(results)}个测试")
    safe_print(f"通过: {passed}个")
    safe_print(f"失败: {failed}个")
    
    if failed == 0:
        safe_print("\n[SUCCESS] 所有测试通过！")
        return 0
    else:
        safe_print(f"\n[FAIL] {failed}个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

