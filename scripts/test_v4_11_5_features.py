#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.11.5功能测试脚本

测试内容：
1. 原始数据层查看API
2. 数据流转追踪API
3. 连带率指标API
4. 平台对比API
5. 数据一致性验证API
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from backend.models.database import get_db
from modules.core.db import CatalogFile
from modules.core.logger import get_logger
import requests
import json

logger = get_logger(__name__)

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_raw_layer_api():
    """测试原始数据层查看API"""
    safe_print("\n[测试1] 原始数据层查看API")
    safe_print("=" * 60)
    
    # 获取一个测试文件ID
    db = next(get_db())
    test_file = db.query(CatalogFile).first()
    
    if not test_file:
        safe_print("[跳过] 没有测试文件")
        return
    
    file_id = test_file.id
    safe_print(f"测试文件ID: {file_id}, 文件名: {test_file.file_name}")
    
    # 测试API端点
    base_url = "http://localhost:8001"
    
    try:
        # 1. 查看原始Excel数据
        response = requests.get(f"{base_url}/api/raw-layer/view/{file_id}", params={"header_row": 0, "limit": 10})
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 查看原始Excel数据: {len(data.get('data', []))} 行")
        else:
            safe_print(f"[失败] 查看原始Excel数据: {response.status_code}")
        
        # 2. 查看Staging数据
        response = requests.get(f"{base_url}/api/raw-layer/staging/{file_id}", params={"limit": 10, "offset": 0})
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 查看Staging数据: {len(data.get('data', []))} 行")
        else:
            safe_print(f"[失败] 查看Staging数据: {response.status_code}")
        
        # 3. 对比原始数据与Staging数据
        response = requests.get(f"{base_url}/api/raw-layer/compare/{file_id}", params={"header_row": 0})
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 对比数据: {data.get('summary', {}).get('total_rows', 0)} 行")
        else:
            safe_print(f"[失败] 对比数据: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        safe_print("[跳过] 后端服务未运行（需要启动后端服务）")
    except Exception as e:
        safe_print(f"[错误] {e}")


def test_data_flow_api():
    """测试数据流转追踪API"""
    safe_print("\n[测试2] 数据流转追踪API")
    safe_print("=" * 60)
    
    base_url = "http://localhost:8001"
    
    try:
        # 获取一个测试文件ID
        db = next(get_db())
        test_file = db.query(CatalogFile).first()
        
        if not test_file:
            safe_print("[跳过] 没有测试文件")
            return
        
        file_id = test_file.id
        
        # 测试文件流转追踪
        response = requests.get(f"{base_url}/api/data-flow/trace/file/{file_id}", params={"header_row": 0})
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 文件流转追踪: {data.get('flow_status', {}).get('overall', {}).get('success_rate', 0)}%")
        else:
            safe_print(f"[失败] 文件流转追踪: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        safe_print("[跳过] 后端服务未运行（需要启动后端服务）")
    except Exception as e:
        safe_print(f"[错误] {e}")


def test_attach_rate_api():
    """测试连带率指标API"""
    safe_print("\n[测试3] 连带率指标API")
    safe_print("=" * 60)
    
    base_url = "http://localhost:8001"
    
    try:
        from datetime import date, timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        # 测试连带率趋势
        response = requests.get(
            f"{base_url}/api/metrics/attach-rate/trend",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": "daily"
            }
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 连带率趋势: {len(data.get('data', []))} 个数据点")
        else:
            safe_print(f"[失败] 连带率趋势: {response.status_code}")
        
        # 测试连带率对比
        response = requests.get(
            f"{base_url}/api/metrics/attach-rate/comparison",
            params={"date_range": "7d"}
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 连带率对比: {len(data.get('data', []))} 个平台/店铺")
        else:
            safe_print(f"[失败] 连带率对比: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        safe_print("[跳过] 后端服务未运行（需要启动后端服务）")
    except Exception as e:
        safe_print(f"[错误] {e}")


def test_platform_comparison_api():
    """测试平台对比API"""
    safe_print("\n[测试4] 平台对比API")
    safe_print("=" * 60)
    
    base_url = "http://localhost:8001"
    
    try:
        from datetime import date, timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        response = requests.get(
            f"{base_url}/api/metrics/platform/comparison",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 平台对比: {len(data.get('platforms', []))} 个平台")
        else:
            safe_print(f"[失败] 平台对比: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        safe_print("[跳过] 后端服务未运行（需要启动后端服务）")
    except Exception as e:
        safe_print(f"[错误] {e}")


def test_data_consistency_api():
    """测试数据一致性验证API"""
    safe_print("\n[测试5] 数据一致性验证API")
    safe_print("=" * 60)
    
    base_url = "http://localhost:8001"
    
    try:
        from datetime import date, timedelta
        
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        # 测试跨平台一致性检查
        response = requests.get(
            f"{base_url}/api/data-consistency/cross-platform",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 跨平台一致性检查: 一致性评分 {data.get('summary', {}).get('consistency_score', 0)}%")
        else:
            safe_print(f"[失败] 跨平台一致性检查: {response.status_code}")
        
        # 测试异常数据检测
        response = requests.get(
            f"{base_url}/api/data-consistency/anomaly-detection",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "metric": "gmv",
                "threshold": 3.0
            }
        )
        if response.status_code == 200:
            data = response.json()
            safe_print(f"[OK] 异常数据检测: {data.get('summary', {}).get('anomaly_count', 0)} 个异常点")
        else:
            safe_print(f"[失败] 异常数据检测: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        safe_print("[跳过] 后端服务未运行（需要启动后端服务）")
    except Exception as e:
        safe_print(f"[错误] {e}")


def main():
    """主函数"""
    safe_print("\n" + "=" * 60)
    safe_print("v4.11.5功能测试")
    safe_print("=" * 60)
    
    # 运行所有测试
    test_raw_layer_api()
    test_data_flow_api()
    test_attach_rate_api()
    test_platform_comparison_api()
    test_data_consistency_api()
    
    safe_print("\n" + "=" * 60)
    safe_print("测试完成")
    safe_print("=" * 60)
    safe_print("\n注意：部分测试需要后端服务运行在 http://localhost:8001")
    safe_print("如果后端未运行，相关测试将被跳过")


if __name__ == "__main__":
    main()

