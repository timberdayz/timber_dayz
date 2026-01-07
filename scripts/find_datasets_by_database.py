#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过数据库查找数据集
"""

import sys
import os
import requests
import json
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

def find_database(session, db_name='xihong_erp'):
    """查找数据库"""
    # 尝试不同的查询方式
    db_url = f"{SUPERSET_URL}/api/v1/database/"
    
    # 方法1: 直接查询
    resp1 = session.get(db_url)
    data1 = resp1.json()
    print(f"方法1 - count: {data1.get('count')}, ids: {len(data1.get('ids', []))}")
    
    # 方法2: 使用过滤器
    filters = [{'col': 'database_name', 'opr': 'eq', 'value': db_name}]
    resp2 = session.get(db_url, params={'q': json.dumps({'filters': filters})})
    data2 = resp2.json()
    print(f"方法2 - count: {data2.get('count')}, ids: {len(data2.get('ids', []))}")
    
    # 获取ID列表
    ids = data1.get('ids', []) or data2.get('ids', [])
    
    if ids:
        print(f"\n找到 {len(ids)} 个数据库ID，获取详细信息...")
        for db_id in ids:
            detail_resp = session.get(f"{db_url}{db_id}")
            if detail_resp.status_code == 200:
                detail = detail_resp.json().get('result', {})
                if isinstance(detail, dict):
                    name = detail.get('database_name', 'N/A')
                    print(f"  ID {db_id}: {name}")
                    if name == db_name:
                        return db_id, detail
    
    return None, None

def find_datasets_by_database(session, db_id):
    """通过数据库ID查找数据集"""
    # Superset可能有专门的API通过数据库查询数据集
    # 尝试不同的端点
    
    # 方法1: 通过数据库的datasets端点
    try:
        db_datasets_url = f"{SUPERSET_URL}/api/v1/database/{db_id}/datasets/"
        resp = session.get(db_datasets_url)
        if resp.status_code == 200:
            datasets = resp.json().get('result', [])
            print(f"\n通过数据库datasets端点找到 {len(datasets)} 个数据集")
            return datasets
    except:
        pass
    
    # 方法2: 查询所有数据集然后过滤
    ds_url = f"{SUPERSET_URL}/api/v1/dataset/"
    resp = session.get(ds_url, params={'page': 0, 'page_size': 1000})
    data = resp.json()
    
    ids = data.get('ids', [])
    print(f"\n数据集API返回 {len(ids)} 个ID")
    
    datasets = []
    for ds_id in ids:
        try:
            detail_resp = session.get(f"{ds_url}{ds_id}")
            if detail_resp.status_code == 200:
                detail = detail_resp.json().get('result', {})
                if isinstance(detail, dict):
                    ds_db = detail.get('database', {})
                    ds_db_id = ds_db.get('id') if isinstance(ds_db, dict) else ds_db
                    if ds_db_id == db_id:
                        datasets.append(detail)
        except:
            continue
    
    return datasets

if __name__ == '__main__':
    print("=" * 80)
    print("通过数据库查找数据集")
    print("=" * 80)
    
    try:
        session = login()
        print("[OK] 登录成功\n")
        
        db_id, db_info = find_database(session)
        if db_id:
            print(f"\n[OK] 找到数据库: xihong_erp (ID: {db_id})")
            print(f"连接字符串: {db_info.get('sqlalchemy_uri', 'N/A')[:80]}...")
            
            datasets = find_datasets_by_database(session, db_id)
            print(f"\n找到 {len(datasets)} 个数据集:")
            for i, ds in enumerate(datasets, 1):
                print(f"  {i}. {ds.get('table_name', 'N/A')} (ID: {ds.get('id')})")
        else:
            print("\n[WARNING] 未找到数据库连接")
            print("请在Superset UI中确认数据库连接已创建")
        
    except Exception as e:
        print(f"\n[ERROR] 失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

