#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试v4.13.1新增功能
- 数据流转可视化
- 丢失数据导出功能
"""

import os
import sys
import requests
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 禁用代理（本地请求）
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'

BASE_URL = "http://127.0.0.1:8001/api"
TIMEOUT = 30

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_export_lost_data():
    """测试丢失数据导出功能"""
    safe_print("\n[TEST] 测试丢失数据导出功能")
    safe_print("=" * 60)
    
    # 1. 获取一个文件ID（从catalog_files表）
    try:
        from backend.models.database import SessionLocal
        from modules.core.db import CatalogFile
        from sqlalchemy import select
        
        db = SessionLocal()
        try:
            # 查找一个已入库的文件
            catalog_file = db.execute(
                select(CatalogFile).where(
                    CatalogFile.status == 'ingested'
                ).limit(1)
            ).scalar_one_or_none()
            
            if not catalog_file:
                safe_print("[SKIP] 没有找到已入库的文件，跳过测试")
                return True
            
            file_id = catalog_file.id
            safe_print(f"[OK] 找到测试文件: file_id={file_id}, file_name={catalog_file.file_name}")
            
            # 2. 调用导出API
            url = f"{BASE_URL}/raw-layer/export-lost-data/{file_id}"
            safe_print(f"[INFO] 请求URL: {url}")
            
            response = requests.get(url, timeout=TIMEOUT)
            safe_print(f"[INFO] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 检查响应头
                content_type = response.headers.get('Content-Type', '')
                content_disposition = response.headers.get('Content-Disposition', '')
                
                safe_print(f"[OK] Content-Type: {content_type}")
                safe_print(f"[OK] Content-Disposition: {content_disposition}")
                
                # 检查文件大小
                content_length = len(response.content)
                safe_print(f"[OK] 文件大小: {content_length} bytes")
                
                if 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type:
                    safe_print("[OK] 文件格式正确（Excel）")
                    
                    # 保存测试文件
                    test_output_dir = project_root / "temp" / "outputs"
                    test_output_dir.mkdir(parents=True, exist_ok=True)
                    test_file = test_output_dir / f"test_lost_data_export_{file_id}.xlsx"
                    
                    with open(test_file, 'wb') as f:
                        f.write(response.content)
                    
                    safe_print(f"[OK] 测试文件已保存: {test_file}")
                    return True
                else:
                    safe_print(f"[ERROR] 文件格式不正确: {content_type}")
                    return False
            else:
                safe_print(f"[ERROR] API返回错误: {response.status_code}")
                safe_print(f"[ERROR] 响应内容: {response.text[:500]}")
                return False
                
        finally:
            db.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_flow_api():
    """测试数据流转API（用于可视化）"""
    safe_print("\n[TEST] 测试数据流转API")
    safe_print("=" * 60)
    
    try:
        from backend.models.database import SessionLocal
        from modules.core.db import CatalogFile
        from sqlalchemy import select
        
        db = SessionLocal()
        try:
            # 查找一个已入库的文件
            catalog_file = db.execute(
                select(CatalogFile).where(
                    CatalogFile.status == 'ingested'
                ).limit(1)
            ).scalar_one_or_none()
            
            if not catalog_file:
                safe_print("[SKIP] 没有找到已入库的文件，跳过测试")
                return True
            
            file_id = catalog_file.id
            safe_print(f"[OK] 找到测试文件: file_id={file_id}")
            
            # 调用数据流转API
            url = f"{BASE_URL}/data-flow/trace/file/{file_id}"
            safe_print(f"[INFO] 请求URL: {url}")
            
            response = requests.get(url, timeout=TIMEOUT)
            safe_print(f"[INFO] 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    flow_data = data.get('data', {})
                    safe_print(f"[OK] API调用成功")
                    safe_print(f"[INFO] Raw层: {flow_data.get('raw_count', 0)}")
                    safe_print(f"[INFO] Staging层: {flow_data.get('staging_count', 0)}")
                    safe_print(f"[INFO] Fact层: {flow_data.get('fact_count', 0)}")
                    safe_print(f"[INFO] Quarantine层: {flow_data.get('quarantine_count', 0)}")
                    return True
                else:
                    safe_print(f"[ERROR] API返回失败: {data.get('message', 'Unknown error')}")
                    return False
            else:
                safe_print(f"[ERROR] API返回错误: {response.status_code}")
                safe_print(f"[ERROR] 响应内容: {response.text[:500]}")
                return False
                
        finally:
            db.close()
            
    except Exception as e:
        safe_print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    safe_print("\n" + "=" * 60)
    safe_print("v4.13.1 功能测试")
    safe_print("=" * 60)
    
    results = []
    
    # 测试1: 丢失数据导出功能
    results.append(("丢失数据导出", test_export_lost_data()))
    
    # 测试2: 数据流转API
    results.append(("数据流转API", test_data_flow_api()))
    
    # 汇总结果
    safe_print("\n" + "=" * 60)
    safe_print("测试结果汇总")
    safe_print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    safe_print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        safe_print("\n[OK] 所有测试通过！")
        return 0
    else:
        safe_print(f"\n[ERROR] {failed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())

