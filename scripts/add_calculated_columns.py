#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为Superset数据集添加计算列（Metrics）
"""

import sys
import os
import requests
import json
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

SUPERSET_URL = os.getenv('SUPERSET_URL', 'http://localhost:8088')
SUPERSET_USERNAME = os.getenv('SUPERSET_USERNAME', 'admin')
SUPERSET_PASSWORD = os.getenv('SUPERSET_PASSWORD', 'admin')

def login():
    """登录Superset"""
    session = requests.Session()
    session.proxies = {'http': None, 'https': None}
    
    login_resp = session.post(f'{SUPERSET_URL}/api/v1/security/login', json={
        'username': SUPERSET_USERNAME,
        'password': SUPERSET_PASSWORD,
        'provider': 'db',
        'refresh': True
    })
    token = login_resp.json().get('access_token')
    session.headers.update({'Authorization': f'Bearer {token}'})
    
    csrf_resp = session.get(f'{SUPERSET_URL}/api/v1/security/csrf_token/')
    csrf_token = csrf_resp.json().get('result')
    session.headers.update({'X-CSRFToken': csrf_token})
    
    return session

def get_dataset_by_name(session, table_name, db_name='xihong_erp'):
    """通过表名查找数据集ID"""
    # 获取所有数据集ID
    ds_url = f"{SUPERSET_URL}/api/v1/dataset/"
    resp = session.get(ds_url, params={'page': 0, 'page_size': 1000})
    data = resp.json()
    
    ids = data.get('ids', [])
    if not ids:
        # 尝试从result中获取
        result = data.get('result', {})
        if isinstance(result, dict):
            ids = result.get('ids', [])
    
    # 通过ID查找
    for ds_id in ids:
        try:
            detail_resp = session.get(f"{ds_url}{ds_id}")
            if detail_resp.status_code == 200:
                detail = detail_resp.json().get('result', {})
                if isinstance(detail, dict):
                    if detail.get('table_name') == table_name:
                        db_info = detail.get('database', {})
                        db_name_found = db_info.get('database_name', '') if isinstance(db_info, dict) else ''
                        if db_name_found == db_name:
                            return ds_id, detail
        except:
            continue
    
    return None, None

def add_metrics_to_dataset(session, dataset_id, metrics_config):
    """为数据集添加Metrics（计算列）"""
    # 获取数据集当前配置
    get_url = f"{SUPERSET_URL}/api/v1/dataset/{dataset_id}"
    resp = session.get(get_url)
    if resp.status_code != 200:
        print(f"    [ERROR] 无法获取数据集详情: {resp.status_code}")
        return False
    
    dataset = resp.json().get('result', {})
    current_metrics = dataset.get('metrics', []) or []
    current_columns = dataset.get('columns', []) or []
    
    # 添加新的metrics
    new_metrics = []
    for metric_config in metrics_config:
        metric_name = metric_config['metric_name']
        expression = metric_config['expression']
        description = metric_config.get('description', '')
        
        # 检查是否已存在
        existing = next((m for m in current_metrics if m.get('metric_name') == metric_name), None)
        if existing:
            print(f"    [SKIP] Metric已存在: {metric_name}")
            continue
        
        # 创建新的metric
        new_metric = {
            'metric_name': metric_name,
            'expression': expression,
            'description': description,
            'metric_type': 'CUSTOM',
            'd3format': None,
            'verbose_name': metric_name,
            'warning_text': None
        }
        new_metrics.append(new_metric)
        current_metrics.append(new_metric)
    
    if not new_metrics:
        print(f"    [INFO] 所有Metrics已存在")
        return True
    
    # 更新数据集
    update_data = {
        'metrics': current_metrics,
        'columns': current_columns
    }
    
    put_url = f"{SUPERSET_URL}/api/v1/dataset/{dataset_id}"
    update_resp = session.put(put_url, json=update_data)
    
    if update_resp.status_code in [200, 201]:
        print(f"    [OK] 已添加 {len(new_metrics)} 个Metrics: {[m['metric_name'] for m in new_metrics]}")
        return True
    else:
        print(f"    [ERROR] 更新失败: {update_resp.status_code}")
        print(f"    响应: {update_resp.text[:200]}")
        return False

def main():
    """主函数"""
    print("=" * 80)
    print("为Superset数据集添加计算列（Metrics）")
    print("=" * 80)
    
    session = login()
    print("[OK] 登录成功\n")
    
    # 配置计算列
    datasets_config = [
        {
            'table_name': 'view_shop_performance_wide',
            'metrics': [
                {
                    'metric_name': 'conversion_rate',
                    'expression': 'order_count / NULLIF(buyer_count, 0) * 100',
                    'description': '转化率（订单数/买家数*100）'
                },
                {
                    'metric_name': 'attachment_rate',
                    'expression': 'total_items / NULLIF(order_count, 0)',
                    'description': '客单价（总商品数/订单数）'
                }
            ]
        },
        {
            'table_name': 'view_product_performance_wide',
            'metrics': [
                {
                    'metric_name': 'stock_days',
                    'expression': 'current_stock / NULLIF(avg_daily_sales, 0)',
                    'description': '库存天数（当前库存/日均销量）'
                }
            ]
        }
    ]
    
    success_count = 0
    for config in datasets_config:
        table_name = config['table_name']
        print(f"\n[{table_name}]")
        
        # 查找数据集
        dataset_id, dataset_info = get_dataset_by_name(session, table_name)
        if not dataset_id:
            print(f"  [ERROR] 未找到数据集: {table_name}")
            continue
        
        print(f"  [OK] 找到数据集 (ID: {dataset_id})")
        
        # 添加metrics
        if add_metrics_to_dataset(session, dataset_id, config['metrics']):
            success_count += 1
        
        time.sleep(0.5)  # 避免请求过快
    
    print("\n" + "=" * 80)
    print("完成")
    print("=" * 80)
    print(f"成功配置: {success_count}/{len(datasets_config)} 个数据集")
    
    if success_count == len(datasets_config):
        print("\n✅ 所有计算列已配置完成！")
        print("现在可以在Superset中创建图表和Dashboard了")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

