#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化数据库表脚本

用于在Docker容器中创建所有数据库表
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine, Base
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))

def check_tables_exist():
    """检查表是否存在"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
            """))
            count = result.scalar()
            return count > 0
    except Exception as e:
        safe_print(f"检查表时出错: {e}")
        return False

def init_tables():
    """初始化数据库表"""
    safe_print("\n" + "="*80)
    safe_print("开始初始化数据库表...")
    safe_print("="*80)
    
    # 检查是否已有表
    if check_tables_exist():
        safe_print("\n[INFO] 检测到数据库中已有表，跳过创建")
        safe_print("提示: 如需重新创建，请先删除所有表")
        return True
    
    try:
        safe_print("\n[步骤1] 创建所有表...")
        # 创建所有表
        Base.metadata.create_all(bind=engine, checkfirst=True)
        safe_print("[OK] 表创建命令执行完成")
        
        # 验证表是否真的创建了
        safe_print("\n[步骤2] 验证表创建...")
        if check_tables_exist():
            safe_print("[OK] 数据库表初始化成功！")
            
            # 显示创建的表数量
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                """))
                count = result.scalar()
                safe_print(f"[INFO] 共创建 {count} 张表")
                
                # 显示部分表名
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    LIMIT 10
                """))
                tables = [row[0] for row in result]
                safe_print(f"[INFO] 部分表名: {', '.join(tables)}")
            
            return True
        else:
            safe_print("[ERROR] 表创建失败，表中不存在")
            return False
            
    except Exception as e:
        error_str = str(e)
        if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
            safe_print(f"[WARNING] 某些表/索引已存在: {e}")
            safe_print("[INFO] 继续验证表创建...")
            
            if check_tables_exist():
                safe_print("[OK] 数据库表已存在，初始化完成")
                return True
            else:
                safe_print("[ERROR] 表仍然不存在")
                return False
        else:
            safe_print(f"[ERROR] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = init_tables()
    
    safe_print("\n" + "="*80)
    if success:
        safe_print("数据库表初始化完成！")
    else:
        safe_print("数据库表初始化失败！")
        sys.exit(1)
    safe_print("="*80)

