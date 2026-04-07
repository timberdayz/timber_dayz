#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试费用管理 API"""

import requests
import json

def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))

def main():
    base_url = 'http://localhost:8001/api'
    
    safe_print("=" * 60)
    safe_print("测试费用管理 API")
    safe_print("=" * 60)
    
    # 1. 测试健康检查
    try:
        r = requests.get(f'{base_url}/health', timeout=5)
        safe_print(f'[OK] Health check: {r.status_code}')
    except Exception as e:
        safe_print(f'[FAIL] Health check: {e}')
        return 1
    
    # 2. 测试登录获取 token
    try:
        login_data = {'username': 'admin', 'password': 'admin123'}
        r = requests.post(f'{base_url}/auth/login', json=login_data, timeout=5)
        if r.status_code == 200:
            data = r.json()
            token = data.get('data', {}).get('access_token') or data.get('access_token')
            if token:
                safe_print(f'[OK] Login successful, got token')
            else:
                safe_print(f'[FAIL] No token in response')
                return 1
        else:
            safe_print(f'[FAIL] Login failed: {r.status_code}')
            return 1
    except Exception as e:
        safe_print(f'[FAIL] Login error: {e}')
        return 1
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # 3. 测试费用管理店铺列表
    safe_print("")
    safe_print("--- 测试费用管理店铺列表 ---")
    try:
        r = requests.get(f'{base_url}/expenses/shops', headers=headers, timeout=5)
        safe_print(f'[INFO] Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            shops = data.get('data', [])
            safe_print(f'[OK] Got {len(shops)} shops')
            if shops:
                safe_print(f'[INFO] Sample: {shops[0]}')
        else:
            safe_print(f'[FAIL] Response: {r.text[:300]}')
    except Exception as e:
        safe_print(f'[FAIL] Error: {e}')
    
    # 4. 测试费用列表
    safe_print("")
    safe_print("--- 测试费用列表 (2025-09) ---")
    try:
        r = requests.get(f'{base_url}/expenses', headers=headers, params={'year_month': '2025-09'}, timeout=10)
        safe_print(f'[INFO] Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', {}).get('items', [])
            safe_print(f'[OK] Got {len(items)} expense records')
            if items:
                safe_print(f'[INFO] Sample: {items[0]}')
        else:
            safe_print(f'[FAIL] Response: {r.text[:500]}')
    except Exception as e:
        safe_print(f'[FAIL] Error: {e}')
    
    # 5. 测试目标管理
    safe_print("")
    safe_print("--- 测试目标管理列表 ---")
    try:
        r = requests.get(f'{base_url}/targets', headers=headers, timeout=10)
        safe_print(f'[INFO] Status: {r.status_code}')
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', {}).get('items', [])
            safe_print(f'[OK] Got {len(items)} targets')
        else:
            safe_print(f'[FAIL] Response: {r.text[:500]}')
    except Exception as e:
        safe_print(f'[FAIL] Error: {e}')
    
    safe_print("")
    safe_print("=" * 60)
    safe_print("测试完成")
    safe_print("=" * 60)
    return 0

if __name__ == "__main__":
    exit(main())
