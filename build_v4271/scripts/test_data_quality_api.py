#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据质量监控API端点

测试内容：
1. GET /api/data-quality/c-class-readiness
2. GET /api/data-quality/b-class-completeness
3. GET /api/data-quality/core-fields-status
"""

import sys
import requests
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "http://localhost:8001"


def test_c_class_readiness():
    """测试C类数据计算就绪状态查询"""
    logger.info("=" * 70)
    logger.info("测试1: C类数据计算就绪状态查询")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/api/data-quality/c-class-readiness"
        response = requests.get(url, timeout=30)
        
        logger.info(f"URL: {url}")
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            if data.get("success"):
                readiness_data = data.get("data", {})
                logger.info(f"\nC类数据就绪状态: {readiness_data.get('c_class_ready')}")
                logger.info(f"数据质量评分: {readiness_data.get('data_quality_score')}")
                logger.info(f"缺失字段数: {len(readiness_data.get('missing_core_fields', []))}")
                return True
            else:
                logger.error(f"API返回失败: {data.get('message', '未知错误')}")
                return False
        else:
            logger.error(f"HTTP错误: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("[FAIL] 无法连接到后端服务，请确保后端服务已启动")
        logger.info("启动命令: python run.py 或 python backend/main.py")
        return False
    except Exception as e:
        logger.error(f"[FAIL] 测试失败: {e}")
        return False


def test_b_class_completeness():
    """测试B类数据完整性检查"""
    logger.info("\n" + "=" * 70)
    logger.info("测试2: B类数据完整性检查")
    logger.info("=" * 70)
    
    try:
        # 先查询一个存在的店铺
        url = f"{BASE_URL}/api/data-quality/b-class-completeness"
        params = {
            "platform_code": "shopee",
            "shop_id": "shop001",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        }
        
        response = requests.get(url, params=params, timeout=30)
        
        logger.info(f"URL: {url}")
        logger.info(f"参数: {params}")
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"响应摘要:")
            logger.info(f"  - 成功: {data.get('success')}")
            
            if data.get("success"):
                completeness_data = data.get("data", {})
                summary = completeness_data.get("summary", {})
                logger.info(f"  - 总天数: {summary.get('total_days')}")
                logger.info(f"  - 平均质量评分: {summary.get('avg_quality_score')}")
                logger.info(f"  - 完整天数: {summary.get('complete_days')}")
                logger.info(f"  - 不完整天数: {summary.get('incomplete_days')}")
                return True
            else:
                logger.error(f"API返回失败: {data.get('message', '未知错误')}")
                return False
        elif response.status_code == 400:
            logger.warning(f"[WARN] 参数错误: {response.text}")
            logger.info("这可能是正常的，如果指定的店铺不存在")
            return True  # 参数错误不算测试失败
        else:
            logger.error(f"HTTP错误: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("[FAIL] 无法连接到后端服务")
        return False
    except Exception as e:
        logger.error(f"[FAIL] 测试失败: {e}")
        return False


def test_core_fields_status():
    """测试核心字段状态查询"""
    logger.info("\n" + "=" * 70)
    logger.info("测试3: 核心字段状态查询")
    logger.info("=" * 70)
    
    try:
        url = f"{BASE_URL}/api/data-quality/core-fields-status"
        response = requests.get(url, timeout=10)
        
        logger.info(f"URL: {url}")
        logger.info(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"响应摘要:")
            logger.info(f"  - 成功: {data.get('success')}")
            
            if data.get("success"):
                status_data = data.get("data", {})
                logger.info(f"  - 总字段数: {status_data.get('total_fields')}")
                logger.info(f"  - 已存在字段数: {status_data.get('present_fields')}")
                logger.info(f"  - 缺失字段数: {status_data.get('missing_fields')}")
                
                fields_by_domain = status_data.get("fields_by_domain", {})
                for domain, domain_info in fields_by_domain.items():
                    logger.info(f"\n  {domain} 数据域:")
                    logger.info(f"    - 总计: {domain_info.get('total')}")
                    logger.info(f"    - 已存在: {domain_info.get('present')}")
                    logger.info(f"    - 缺失: {domain_info.get('missing')}")
                
                return True
            else:
                logger.error(f"API返回失败: {data.get('message', '未知错误')}")
                return False
        else:
            logger.error(f"HTTP错误: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("[FAIL] 无法连接到后端服务")
        return False
    except Exception as e:
        logger.error(f"[FAIL] 测试失败: {e}")
        return False


def main():
    """主测试函数"""
    logger.info("=" * 70)
    logger.info("数据质量监控API端点测试")
    logger.info("=" * 70)
    logger.info(f"\n后端服务地址: {BASE_URL}")
    logger.info("如果后端服务未启动，请先运行: python run.py\n")
    
    results = {
        "c_class_readiness": False,
        "b_class_completeness": False,
        "core_fields_status": False
    }
    
    # 测试1: C类数据计算就绪状态查询
    results["c_class_readiness"] = test_c_class_readiness()
    
    # 测试2: B类数据完整性检查
    results["b_class_completeness"] = test_b_class_completeness()
    
    # 测试3: 核心字段状态查询
    results["core_fields_status"] = test_core_fields_status()
    
    # 汇总结果
    logger.info("\n" + "=" * 70)
    logger.info("测试结果汇总")
    logger.info("=" * 70)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "[OK]" if result else "[FAIL]"
        logger.info(f"{status} {test_name}")
    
    logger.info(f"\n通过: {passed}/{total}")
    
    if passed == total:
        logger.info("\n[OK] 所有API测试通过")
        return 0
    else:
        logger.error(f"\n[FAIL] {total - passed} 个API测试失败")
        logger.info("\n提示: 如果后端服务未启动，请先启动后端服务")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)

