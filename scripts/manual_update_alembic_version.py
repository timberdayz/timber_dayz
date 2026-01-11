#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动更新 Alembic 版本号

用于跳过有问题的迁移文件，直接标记为最新版本。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from sqlalchemy import text


def main():
    target_version = '20260111_0001_complete_missing_tables'
    
    print(f"[INFO] 准备更新 Alembic 版本到: {target_version}")
    
    conn = engine.connect()
    
    # 查询当前版本
    result = conn.execute(text('SELECT version_num FROM alembic_version'))
    current_version = result.scalar()
    print(f"[INFO] 当前版本: {current_version}")
    
    # 更新版本
    conn.execute(text(f"UPDATE alembic_version SET version_num = '{target_version}'"))
    conn.commit()
    
    # 验证更新
    result2 = conn.execute(text('SELECT version_num FROM alembic_version'))
    new_version = result2.scalar()
    print(f"[OK] 新版本: {new_version}")
    
    conn.close()
    
    print("[OK] Alembic 版本更新成功！")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] 更新失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
