#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试 ORM 映射是否正确"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(project_root / ".env")


def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8"))


def main():
    safe_print("=" * 60)
    safe_print("测试 ORM 映射")
    safe_print("=" * 60)
    
    # 导入数据库模块
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    
    database_url = os.getenv("DATABASE_URL", "postgresql://erp_user:erp_password@localhost:15432/xihong_erp")
    
    safe_print(f"[INFO] 数据库: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    
    # 创建引擎（设置 search_path）
    engine = create_engine(
        database_url,
        connect_args={
            "options": "-c search_path=public,b_class,a_class,c_class,core,finance"
        }
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 测试 1: 直接 SQL 查询 operating_costs
        safe_print("")
        safe_print("--- 测试 1: 直接 SQL 查询 a_class.operating_costs ---")
        result = session.execute(text('SELECT COUNT(*) FROM a_class.operating_costs'))
        count = result.scalar()
        safe_print(f"[OK] a_class.operating_costs 有 {count} 条记录")
        
        # 测试 2: 查询字段名
        safe_print("")
        safe_print("--- 测试 2: 检查字段名 ---")
        result = session.execute(text('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'a_class' AND table_name = 'operating_costs'
            ORDER BY ordinal_position
        '''))
        columns = [row[0] for row in result]
        safe_print(f"[INFO] 字段列表: {columns}")
        
        # 测试 3: 使用 ORM 查询
        safe_print("")
        safe_print("--- 测试 3: ORM 查询 ---")
        from modules.core.db import OperatingCost
        
        # 打印 ORM 表信息
        safe_print(f"[INFO] ORM 表名: {OperatingCost.__tablename__}")
        safe_print(f"[INFO] ORM Schema: {OperatingCost.__table__.schema}")
        safe_print(f"[INFO] ORM 列: {[c.name for c in OperatingCost.__table__.columns]}")
        
        # 尝试 ORM 查询
        try:
            records = session.query(OperatingCost).limit(3).all()
            safe_print(f"[OK] ORM 查询成功，获取 {len(records)} 条记录")
            for r in records:
                safe_print(f"  - ID: {r.id}, 店铺ID: {r.shop_id}, 年月: {r.year_month}, 租金: {r.rent}")
        except Exception as e:
            safe_print(f"[FAIL] ORM 查询失败: {e}")
        
        # 测试 4: 测试 TargetBreakdown ORM
        safe_print("")
        safe_print("--- 测试 4: TargetBreakdown ORM ---")
        from modules.core.db import TargetBreakdown
        
        safe_print(f"[INFO] ORM 表名: {TargetBreakdown.__tablename__}")
        safe_print(f"[INFO] ORM Schema: {TargetBreakdown.__table__.schema}")
        
        try:
            count = session.query(TargetBreakdown).count()
            safe_print(f"[OK] TargetBreakdown 查询成功，共 {count} 条记录")
        except Exception as e:
            safe_print(f"[FAIL] TargetBreakdown 查询失败: {e}")
        
    except Exception as e:
        safe_print(f"[FAIL] 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()
    
    safe_print("")
    safe_print("=" * 60)
    safe_print("测试完成")
    safe_print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
