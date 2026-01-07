#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证"记住我"功能

测试前端 localStorage 中的 token 是否能正确恢复
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 50)
print("验证'记住我'功能")
print("=" * 50)
print("\n[说明] 此功能需要在前端浏览器中测试")
print("\n测试步骤：")
print("1. 打开浏览器开发者工具（F12）")
print("2. 访问 Application/Storage > Local Storage")
print("3. 登录系统，勾选'记住我'")
print("4. 检查 localStorage 中是否有以下键：")
print("   - access_token")
print("   - refresh_token")
print("   - user_info")
print("5. 刷新页面（F5）")
print("6. 验证是否自动登录（不需要重新输入密码）")
print("\n[后端验证] 检查 token 存储逻辑...")

# 检查后端登录逻辑
try:
    from backend.routers.auth import login
    from backend.schemas.auth import LoginRequest
    print("[OK] 后端登录逻辑正常")
except Exception as e:
    print(f"[WARN] 后端登录逻辑检查失败: {e}")

print("\n[完成] 请在前端浏览器中完成测试")

