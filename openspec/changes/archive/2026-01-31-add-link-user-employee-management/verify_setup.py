#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户与员工关联功能 - 部署后验证脚本

检查项：
1. dim_roles 中存在游客角色 (tourist)
2. a_class.employees 表存在 user_id 列

运行：在项目根目录执行
  python openspec/changes/add-link-user-employee-management/verify_setup.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


def safe_print(text):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            print(text.encode("gbk", errors="ignore").decode("gbk"), flush=True)
        except Exception:
            print(text.encode("ascii", errors="ignore").decode("ascii"), flush=True)


def main():
    ok = True
    safe_print("=== 用户与员工关联 - 部署验证 ===\n")

    try:
        from sqlalchemy import create_engine, text
        from backend.utils.config import get_settings

        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)

        with engine.connect() as conn:
            # 1. 检查游客角色
            r = conn.execute(
                text("SELECT role_code, role_name FROM dim_roles WHERE role_code = 'tourist'")
            )
            row = r.fetchone()
            if row:
                safe_print("[OK] dim_roles 中存在游客角色: role_code=tourist, role_name=" + str(row[1]))
            else:
                safe_print("[FAIL] dim_roles 中未找到游客角色，请执行: python scripts/ensure_all_roles.py")
                ok = False

            # 2. 检查 a_class.employees.user_id 列
            r = conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'a_class' AND table_name = 'employees' AND column_name = 'user_id'
                """)
            )
            if r.fetchone():
                safe_print("[OK] a_class.employees 表存在 user_id 列")
            else:
                safe_print("[FAIL] a_class.employees 缺少 user_id 列，请执行: alembic upgrade head")
                ok = False

    except Exception as e:
        safe_print("[ERROR] " + str(e))
        import traceback
        traceback.print_exc()
        return 1

    safe_print("")
    if ok:
        safe_print("=== 验证通过 ===")
        safe_print("建议按 tasks.md 第 6 节进行手工验证：")
        safe_print("  6.1 创建游客账号，确认仅可访问业务概览")
        safe_print("  6.2 创建用户后在员工管理中关联，确认双向展示正确")
        safe_print("  6.3 解除关联后确认双方均显示未关联")
        safe_print("  6.4 已关联用户访问「我的档案」可自助编辑，HR 可见更新")
        safe_print("  6.5 用户被拒绝后，关联员工的 user_id 已置空")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
