#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询所有用户信息脚本

查询所有用户及其角色信息
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.models.database import AsyncSessionLocal
from modules.core.db import DimUser, DimRole
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def query_all_users():
    """查询所有用户信息"""
    async with AsyncSessionLocal() as db:
        try:
            print("=" * 70)
            print("  查询所有用户信息")
            print("=" * 70)
            
            # 查询所有用户（预加载角色关系）
            result = await db.execute(
                select(DimUser)
                .options(selectinload(DimUser.roles))
                .order_by(DimUser.user_id)
            )
            users = result.scalars().all()
            
            if not users:
                print("\n[提示] 未找到任何用户")
                return True
            
            print(f"\n找到 {len(users)} 个用户：\n")
            
            for user in users:
                await db.refresh(user, ["roles"])
                roles_list = [role.role_name for role in user.roles]
                
                print(f"[用户] {user.username} ({user.email})")
                print(f"  用户ID: {user.user_id}")
                print(f"  姓名: {user.full_name or '未设置'}")
                print(f"  状态: {user.status}")
                print(f"  是否激活: {user.is_active}")
                print(f"  是否超级用户: {user.is_superuser}")
                print(f"  角色: {', '.join(roles_list) if roles_list else '未分配角色'}")
                print(f"  创建时间: {user.created_at}")
                print(f"  注意: 密码是哈希存储的（bcrypt），无法直接查看")
                print("-" * 70)
            
            print("\n" + "=" * 70)
            print("  查询完成")
            print("=" * 70)
            print("\n[提示] 密码是哈希存储的（bcrypt），无法直接查看原始密码")
            print("[提示] 如需重置密码，请联系系统管理员或使用密码重置功能")
            print("=" * 70)
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 查询用户失败: {e}", exc_info=True)
            print(f"\n[ERROR] 查询失败: {e}")
            return False


async def main():
    """主函数"""
    try:
        await query_all_users()
        return True
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n[INFO] 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

