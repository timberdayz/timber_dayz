#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用Alembic autogenerate生成迁移文件

通过Python脚本调用Alembic autogenerate，避免编码问题。
"""

import sys
import os
from pathlib import Path

# 设置UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command


def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def generate_migration():
    """使用Alembic autogenerate生成迁移文件"""
    try:
        safe_print("[INFO] 使用Alembic autogenerate生成迁移文件...")
        
        # 加载Alembic配置
        alembic_cfg = Config("alembic.ini")
        
        # 生成迁移文件
        command.revision(
            alembic_cfg,
            autogenerate=True,
            message="complete_missing_tables_migration"
        )
        
        safe_print("[OK] 迁移文件生成成功")
        safe_print("[INFO] 请检查生成的迁移文件，确认正确后提交")
        
    except Exception as e:
        safe_print(f"[ERROR] 生成迁移文件失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    generate_migration()
