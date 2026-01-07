#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整端到端自动化测试：字段映射系统
测试流程：扫描 → 预览 → 映射 → 入库验证
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001/api/field-mapping"

def safe_print(text):
    """Windows安全打印（避免Unicode错误）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_step_1_scan():
    """步骤1: 扫描文件"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 1/6] 扫描采集文件")
    safe_print("="*60)
    
    response = requests.post(f"{BASE_URL}/scan", timeout=30)
    result = response.json()
    
    safe_print(f"状态: {response.status_code}")
    safe_print(f"扫描结果: 发现 {result['data']['total_files']} 个文件")
    safe_print(f"注册数量: {result['data']['registered']} 个")
    
    assert result['success'], "扫描失败"
    return result

def test_step_2_get_file_groups():
    """步骤2: 获取文件分组"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 2/6] 获取文件分组")
    safe_print("="*60)
    
    response = requests.get(f"{BASE_URL}/file-groups", timeout=10)
    result = response.json()
    
    safe_print(f"平台列表: {result['platforms']}")
    safe_print(f"数据域: {list(result['domains'].keys())}")
    
    # 选择第一个shopee products文件
    shopee_products = result['files'].get('shopee', {}).get('products', [])
    if not shopee_products:
        safe_print("警告: 没有shopee products文件，尝试其他文件...")
        # 尝试任意可用文件
        for platform in result['files']:
            for domain in result['files'][platform]:
                if result['files'][platform][domain]:
                    shopee_products = result['files'][platform][domain]
                    break
            if shopee_products:
                break
    
    assert shopee_products, "没有可用文件"
    
    test_file = shopee_products[0]
    safe_print(f"\n选中测试文件:")
    safe_print(f"  ID: {test_file['id']}")
    safe_print(f"  文件名: {test_file['file_name']}")
    safe_print(f"  粒度: {test_file['granularity']}")
    
    return test_file

def test_step_3_get_file_info(file_id):
    """步骤3: 获取文件信息"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 3/6] 获取文件详细信息")
    safe_print("="*60)
    
    response = requests.get(f"{BASE_URL}/file-info?file_id={file_id}", timeout=10)
    result = response.json()
    
    safe_print(f"文件名: {result['file_name']}")
    safe_print(f"文件路径: {result['actual_path']}")
    safe_print(f"文件存在: {result['file_exists']}")
    safe_print(f"文件大小: {result.get('file_size', 0) / 1024:.2f}KB")
    
    assert result['success'], "获取文件信息失败"
    assert result['file_exists'], "文件不存在"
    
    return result

def test_step_4_preview(file_id):
    """步骤4: 预览文件"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 4/6] 预览文件数据")
    safe_print("="*60)
    
    payload = {"file_id": file_id, "header_row": 1}
    response = requests.post(f"{BASE_URL}/preview", json=payload, timeout=60)
    
    safe_print(f"状态: {response.status_code}")
    
    if response.status_code != 200:
        safe_print(f"预览失败: {response.text}")
        return None
    
    result = response.json()
    
    safe_print(f"列数: {len(result['columns'])}")
    safe_print(f"总行数: {result['total_rows']}")
    safe_print(f"预览行数: {result['preview_rows']}")
    safe_print(f"前5列: {result['columns'][:5]}")
    
    # 合并单元格还原报告
    norm_report = result.get('normalization_report', {})
    if norm_report.get('filled_columns'):
        safe_print(f"\n[合并单元格还原]")
        safe_print(f"  填充列: {norm_report['filled_columns']}")
        safe_print(f"  填充行数: {norm_report['filled_rows']}")
        safe_print(f"  策略: {norm_report['strategy']}")
    
    return result

def test_step_5_generate_mapping(columns, domain="products"):
    """步骤5: 生成字段映射"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 5/6] 生成智能字段映射")
    safe_print("="*60)
    
    payload = {"columns": columns, "domain": domain}
    response = requests.post(f"{BASE_URL}/generate-mapping", json=payload, timeout=30)
    result = response.json()
    
    safe_print(f"映射数量: {len(result['mappings'])}")
    safe_print(f"\n前5个映射:")
    for m in result['mappings'][:5]:
        safe_print(f"  {m['original']} -> {m['standard']} (置信度:{m['confidence']}, 方式:{m['method']})")
    
    return result

def test_step_6_ingest(file_id, platform, domain, mappings, preview_data):
    """步骤6: 数据入库"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 6/6] 数据入库验证")
    safe_print("="*60)
    
    # 构建映射字典
    mapping_dict = {m['original']: m['standard'] for m in mappings}
    
    # 使用预览数据作为入库数据（前20行）
    rows = preview_data['data'][:20]
    
    payload = {
        "file_id": file_id,
        "platform": platform,
        "domain": domain,
        "mappings": mapping_dict,
        "rows": rows
    }
    
    safe_print(f"入库参数:")
    safe_print(f"  file_id: {file_id}")
    safe_print(f"  platform: {platform}")
    safe_print(f"  domain: {domain}")
    safe_print(f"  映射数量: {len(mapping_dict)}")
    safe_print(f"  数据行数: {len(rows)}")
    
    response = requests.post(f"{BASE_URL}/ingest", json=payload, timeout=60)
    
    safe_print(f"\n入库响应状态: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        safe_print(f"[OK] 入库成功!")
        safe_print(f"  暂存行数: {result.get('staged', 0)}")
        safe_print(f"  导入行数: {result.get('imported', 0)}")
        safe_print(f"  隔离行数: {result.get('quarantined', 0)}")
        return result
    else:
        safe_print(f"[ERROR] 入库失败: {response.text}")
        return None

def test_step_7_catalog_status():
    """步骤7: 检查Catalog状态"""
    safe_print("\n" + "="*60)
    safe_print("[步骤 7/7] 检查Catalog状态")
    safe_print("="*60)
    
    response = requests.get(f"{BASE_URL}/catalog-status", timeout=10)
    result = response.json()
    
    safe_print(f"总文件数: {result['total']}")
    safe_print(f"状态统计:")
    for status_info in result['by_status']:
        safe_print(f"  {status_info['status']}: {status_info['count']}")
    
    return result

def run_complete_test():
    """运行完整测试"""
    safe_print("\n" + "#"*60)
    safe_print("# 字段映射系统完整端到端测试")
    safe_print("#"*60)
    
    try:
        # 步骤1: 扫描文件
        scan_result = test_step_1_scan()
        time.sleep(1)
        
        # 步骤2: 获取文件分组并选择测试文件
        test_file = test_step_2_get_file_groups()
        file_id = test_file['id']
        file_name = test_file['file_name']
        time.sleep(1)
        
        # 步骤3: 获取文件信息
        file_info = test_step_3_get_file_info(file_id)
        time.sleep(1)
        
        # 步骤4: 预览文件
        preview_result = test_step_4_preview(file_id)
        if not preview_result:
            safe_print("\n[SKIP] 预览失败，跳过后续步骤")
            return
        time.sleep(1)
        
        # 步骤5: 生成字段映射
        columns = preview_result['columns']
        domain = preview_result.get('data_domain', 'products')
        platform = preview_result.get('platform', 'shopee')
        
        mapping_result = test_step_5_generate_mapping(columns, domain)
        time.sleep(1)
        
        # 步骤6: 数据入库
        ingest_result = test_step_6_ingest(
            file_id, 
            platform, 
            domain, 
            mapping_result['mappings'],
            preview_result
        )
        time.sleep(1)
        
        # 步骤7: 检查Catalog状态
        catalog_status = test_step_7_catalog_status()
        
        # 最终总结
        safe_print("\n" + "#"*60)
        safe_print("# 测试完成总结")
        safe_print("#"*60)
        safe_print(f"[OK] 测试文件: {file_name} (ID:{file_id})")
        safe_print(f"[OK] 预览列数: {len(columns)}")
        safe_print(f"[OK] 映射数量: {len(mapping_result['mappings'])}")
        if ingest_result:
            safe_print(f"[OK] 入库行数: {ingest_result.get('imported', 0)}")
        safe_print(f"[OK] Catalog总数: {catalog_status['total']}")
        
        safe_print("\n" + "="*60)
        safe_print("[SUCCESS] 所有测试通过！字段映射系统功能正常！")
        safe_print("="*60)
        
    except Exception as e:
        safe_print(f"\n[FAILED] 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    safe_print("提示: 确保后端服务已启动（python run.py）")
    safe_print("等待5秒后开始测试...")
    time.sleep(5)
    
    run_complete_test()

