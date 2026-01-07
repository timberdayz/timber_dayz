"""
综合测试脚本：数据库浏览器 + TikTok订单入库
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001/api"

def safe_print(text):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_database_browser():
    """测试数据库浏览器API"""
    safe_print("\n[TEST] ========== 数据库浏览器测试 ==========")
    
    # 1. 获取表列表
    safe_print("\n[STEP 1] 获取表列表...")
    try:
        response = requests.get(f"{BASE_URL}/data-browser/tables", timeout=10)
        if response.status_code == 200:
            data = response.json()
            tables = data.get('tables', [])
            safe_print(f"[OK] 成功获取 {len(tables)} 个表")
            if tables:
                safe_print(f"[OK] 示例表: {tables[0].get('name')} ({tables[0].get('row_count', 0)}行)")
            return tables
        else:
            safe_print(f"[ERROR] 获取表列表失败: {response.status_code}")
            safe_print(f"[ERROR] 响应: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        safe_print("[WARN] 后端服务未启动，跳过API测试")
        return None
    except Exception as e:
        safe_print(f"[ERROR] 获取表列表异常: {e}")
        return None
    
    # 2. 查询数据
    if tables:
        safe_print("\n[STEP 2] 查询数据（fact_orders表）...")
        try:
            params = {
                "table": "fact_orders",
                "page": 1,
                "page_size": 5
            }
            response = requests.get(f"{BASE_URL}/data-browser/query", params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                safe_print(f"[OK] 查询成功: {data.get('total', 0)} 条记录")
                safe_print(f"[OK] 返回 {len(data.get('data', []))} 行数据")
                if data.get('performance'):
                    perf = data['performance']
                    safe_print(f"[OK] 查询耗时: {perf.get('query_time_ms', 0)}ms ({perf.get('status', 'unknown')})")
            else:
                safe_print(f"[ERROR] 查询失败: {response.status_code}")
        except Exception as e:
            safe_print(f"[ERROR] 查询数据异常: {e}")
    
    return tables

def test_tiktok_order_ingest():
    """测试TikTok订单入库"""
    safe_print("\n[TEST] ========== TikTok订单入库测试 ==========")
    
    try:
        # 1. 查找文件
        safe_print("\n[STEP 1] 查找TikTok订单文件...")
        response = requests.get(f"{BASE_URL}/field-mapping/files", params={
            "platform": "tiktok",
            "data_domain": "orders",
            "granularity": "monthly"
        }, timeout=10)
        
        if response.status_code != 200:
            safe_print(f"[ERROR] 获取文件列表失败: {response.status_code}")
            return False
        
        files = response.json().get("files", [])
        if not files:
            safe_print("[WARN] 未找到TikTok订单文件，跳过入库测试")
            return False
        
        file_info = files[0]
        file_id = file_info["file_id"]
        safe_print(f"[OK] 找到文件: {file_info['file_name']} (ID: {file_id})")
        
        # 2. 预览文件
        safe_print("\n[STEP 2] 预览文件...")
        preview_response = requests.post(f"{BASE_URL}/field-mapping/preview", json={
            "file_id": file_id,
            "header_row": 2
        }, timeout=30)
        
        if preview_response.status_code != 200:
            safe_print(f"[ERROR] 预览失败: {preview_response.status_code}")
            return False
        
        preview_data = preview_response.json()
        safe_print(f"[OK] 预览成功: {preview_data.get('total_rows', 0)}行 x {len(preview_data.get('columns', []))}列")
        
        # 3. 获取字段映射建议
        safe_print("\n[STEP 3] 获取字段映射建议...")
        suggest_response = requests.post(f"{BASE_URL}/field-mapping/suggest-mappings", json={
            "file_id": file_id,
            "platform": "tiktok",
            "data_domain": "orders",
            "granularity": "monthly",
            "columns": preview_data.get("columns", [])
        }, timeout=30)
        
        if suggest_response.status_code != 200:
            safe_print(f"[ERROR] 获取映射建议失败: {suggest_response.status_code}")
            return False
        
        mappings = suggest_response.json().get("mappings", {})
        safe_print(f"[OK] 映射建议: {len(mappings)}个字段")
        
        # 4. 执行入库
        safe_print("\n[STEP 4] 执行入库...")
        ingest_response = requests.post(f"{BASE_URL}/field-mapping/ingest", json={
            "file_id": file_id,
            "platform": "tiktok",
            "domain": "orders",
            "mappings": mappings,
            "header_row": 2
        }, timeout=180)
        
        if ingest_response.status_code == 200:
            result = ingest_response.json()
            safe_print(f"[OK] 入库成功!")
            safe_print(f"[OK] 暂存: {result.get('staged', 0)}条")
            safe_print(f"[OK] 入库: {result.get('imported', 0)}条")
            safe_print(f"[OK] 隔离: {result.get('quarantined', 0)}条")
            safe_print(f"[OK] 消息: {result.get('message', '')}")
            return True
        else:
            safe_print(f"[ERROR] 入库失败: {ingest_response.status_code}")
            error_text = ingest_response.text[:1000]
            safe_print(f"[ERROR] 响应: {error_text}")
            return False
            
    except requests.exceptions.ConnectionError:
        safe_print("[WARN] 后端服务未启动，跳过入库测试")
        return False
    except Exception as e:
        safe_print(f"[ERROR] 入库测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    safe_print(f"\n{'='*60}")
    safe_print(f"综合测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print(f"{'='*60}")
    
    # 测试数据库浏览器
    tables = test_database_browser()
    
    # 测试TikTok订单入库
    ingest_success = test_tiktok_order_ingest()
    
    # 如果入库成功，再次查询数据库验证
    if ingest_success:
        safe_print("\n[STEP 5] 验证数据库中的数据...")
        try:
            response = requests.get(f"{BASE_URL}/data-browser/query", params={
                "table": "fact_orders",
                "page": 1,
                "page_size": 10,
                "platform": "tiktok"
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                safe_print(f"[OK] 验证成功: 共{data.get('total', 0)}条TikTok订单记录")
                if data.get('data'):
                    safe_print(f"[OK] 最新订单ID: {data['data'][0].get('order_id', 'N/A')}")
            else:
                safe_print(f"[WARN] 查询失败: {response.status_code}")
        except Exception as e:
            safe_print(f"[WARN] 验证查询异常: {e}")
    
    safe_print(f"\n{'='*60}")
    safe_print("测试完成！")
    safe_print(f"{'='*60}")

if __name__ == "__main__":
    main()

