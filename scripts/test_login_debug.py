#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录调试脚本

用于调试登录问题，查看详细错误信息。
"""

import sys
import requests
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

API_BASE_URL = "http://localhost:8001"
LOGIN_ENDPOINT = f"{API_BASE_URL}/api/auth/login"

def test_login():
    """测试登录"""
    print("=" * 70)
    print("  登录调试测试")
    print("=" * 70)
    print(f"\nAPI 地址: {LOGIN_ENDPOINT}")
    print(f"用户名: admin")
    print(f"密码: admin")
    
    payload = {
        "username": "admin",
        "password": "admin",
        "remember_me": True
    }
    
    try:
        print("\n[INFO] 发送登录请求...")
        response = requests.post(
            LOGIN_ENDPOINT,
            json=payload,
            timeout=10
        )
        
        print(f"\n[INFO] 响应状态码: {response.status_code}")
        print(f"[INFO] 响应头: {dict(response.headers)}")
        
        try:
            response_data = response.json()
            print(f"\n[INFO] 响应内容:")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
        except:
            print(f"\n[INFO] 响应内容（非JSON）:")
            print(response.text)
        
        if response.status_code == 200:
            print("\n[SUCCESS] 登录成功！")
            return True
        else:
            print(f"\n[ERROR] 登录失败，状态码: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] 请求失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = test_login()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INFO] 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

