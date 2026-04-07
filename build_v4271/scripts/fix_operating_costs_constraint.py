#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复 a_class.operating_costs 表的唯一约束

问题描述:
- ORM 定义使用英文字段名 (shop_id, year_month)
- 数据库实际表使用中文字段名 (店铺ID, 年月)
- 导致唯一约束不匹配，UPSERT 失败

修复方案:
1. 删除旧的唯一约束（如果存在）
2. 创建新的唯一约束，使用中文字段名

使用方法:
    python scripts/fix_operating_costs_constraint.py
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 加载 .env 文件
env_path = Path(project_root) / '.env'
if env_path.exists():
    load_dotenv(env_path)

from sqlalchemy import create_engine, text


def safe_print(msg):
    """Safe print for Windows GBK encoding"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def get_database_url():
    """获取数据库连接URL"""
    return os.environ.get(
        "DATABASE_URL", 
        "postgresql://erp_user:erp_password@localhost:5432/xihong_erp"
    )


def fix_operating_costs_constraint():
    """修复 operating_costs 表的唯一约束"""
    
    database_url = get_database_url()
    engine = create_engine(database_url)
    
    with engine.connect() as conn:
        safe_print("=" * 60)
        safe_print("修复 a_class.operating_costs 表唯一约束")
        safe_print("=" * 60)
        
        # 1. 检查表是否存在
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'a_class' AND table_name = 'operating_costs'
            )
        """))
        table_exists = result.scalar()
        
        if not table_exists:
            safe_print("[ERROR] 表 a_class.operating_costs 不存在!")
            safe_print("请先运行 alembic upgrade head 创建表")
            return False
        
        safe_print("[OK] 表 a_class.operating_costs 存在")
        
        # 2. 检查表的实际字段名
        safe_print("\n--- 检查表字段 ---")
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'a_class' AND table_name = 'operating_costs'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        
        column_names = []
        for col in columns:
            safe_print(f"  - {col[0]} ({col[1]})")
            column_names.append(col[0])
        
        # 判断字段是中文还是英文
        uses_chinese_fields = "店铺ID" in column_names
        safe_print(f"\n[INFO] 表使用{'中文' if uses_chinese_fields else '英文'}字段名")
        
        # 3. 检查现有唯一约束
        safe_print("\n--- 检查现有唯一约束 ---")
        result = conn.execute(text("""
            SELECT conname, pg_get_constraintdef(oid) 
            FROM pg_constraint 
            WHERE conrelid = 'a_class.operating_costs'::regclass 
              AND contype = 'u'
        """))
        constraints = result.fetchall()
        
        if constraints:
            for con in constraints:
                safe_print(f"  - {con[0]}: {con[1]}")
        else:
            safe_print("  [WARN] 没有找到唯一约束")
        
        # 4. 确定需要的约束字段名
        if uses_chinese_fields:
            shop_field = '"店铺ID"'
            month_field = '"年月"'
        else:
            shop_field = 'shop_id'
            month_field = 'year_month'
        
        # 5. 删除旧约束（如果存在）
        safe_print("\n--- 删除旧约束 ---")
        old_constraint_names = [
            'uq_operating_costs_a_shop_month',
            'uq_operating_costs_shop_month',
            'operating_costs_shop_id_year_month_key',
        ]
        
        for con_name in old_constraint_names:
            try:
                conn.execute(text(f"""
                    ALTER TABLE a_class.operating_costs 
                    DROP CONSTRAINT IF EXISTS {con_name}
                """))
                safe_print(f"  [OK] 已删除约束 {con_name} (如果存在)")
            except Exception as e:
                safe_print(f"  [SKIP] 约束 {con_name}: {e}")
        
        # 6. 创建新的唯一约束
        safe_print("\n--- 创建新唯一约束 ---")
        constraint_name = 'uq_operating_costs_shop_month'
        
        try:
            conn.execute(text(f"""
                ALTER TABLE a_class.operating_costs 
                ADD CONSTRAINT {constraint_name} 
                UNIQUE ({shop_field}, {month_field})
            """))
            safe_print(f"  [OK] 已创建约束 {constraint_name} ON ({shop_field}, {month_field})")
        except Exception as e:
            if 'already exists' in str(e).lower():
                safe_print(f"  [OK] 约束 {constraint_name} 已存在")
            else:
                safe_print(f"  [ERROR] 创建约束失败: {e}")
                return False
        
        # 7. 提交事务
        conn.commit()
        
        # 8. 验证约束
        safe_print("\n--- 验证约束 ---")
        result = conn.execute(text("""
            SELECT conname, pg_get_constraintdef(oid) 
            FROM pg_constraint 
            WHERE conrelid = 'a_class.operating_costs'::regclass 
              AND contype = 'u'
        """))
        final_constraints = result.fetchall()
        
        if final_constraints:
            for con in final_constraints:
                safe_print(f"  [OK] {con[0]}: {con[1]}")
        else:
            safe_print("  [ERROR] 验证失败 - 没有找到唯一约束")
            return False
        
        safe_print("\n" + "=" * 60)
        safe_print("[SUCCESS] 修复完成!")
        safe_print("=" * 60)
        return True


if __name__ == "__main__":
    try:
        success = fix_operating_costs_constraint()
        sys.exit(0 if success else 1)
    except Exception as e:
        safe_print(f"\n[ERROR] 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
