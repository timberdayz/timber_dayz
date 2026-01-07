#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询所有角色信息脚本

查询所有角色及其用户数量
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from backend.models.database import AsyncSessionLocal
from modules.core.db import DimUser, DimRole
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def query_all_roles():
    """查询所有角色信息"""
    async with AsyncSessionLocal() as db:
        try:
            print("=" * 70)
            print("  查询所有角色信息")
            print("=" * 70)
            
            # 查询所有角色
            result = await db.execute(
                select(DimRole)
                .order_by(DimRole.role_id)
            )
            roles = result.scalars().all()
            
            if not roles:
                print("\n[提示] 未找到任何角色")
                return True
            
            print(f"\n找到 {len(roles)} 个角色：\n")
            
            for role in roles:
                # 查询该角色的用户数量
                user_count_result = await db.execute(
                    select(func.count(DimUser.user_id))
                    .join(DimUser.roles)
                    .where(DimRole.role_id == role.role_id)
                )
                user_count = user_count_result.scalar() or 0
                
                print(f"[角色] {role.role_name} (role_code: {role.role_code})")
                print(f"  描述: {role.description or '未设置'}")
                print(f"  用户数量: {user_count}")
                print(f"  是否激活: {role.is_active}")
                print(f"  是否系统角色: {role.is_system}")
                print(f"  创建时间: {role.created_at}")
                
                # 查询该角色的所有用户
                if user_count > 0:
                    result = await db.execute(
                        select(DimUser)
                        .options(selectinload(DimUser.roles))
                        .join(DimUser.roles)
                        .where(DimRole.role_id == role.role_id)
                    )
                    users = result.unique().scalars().all()
                    
                    print(f"  用户列表:")
                    for user in users:
                        await db.refresh(user, ["roles"])
                        roles_list = [r.role_name for r in user.roles]
                        print(f"    - {user.username} ({user.email})")
                        print(f"      姓名: {user.full_name or '未设置'}")
                        print(f"      状态: {user.status}")
                        print(f"      是否激活: {user.is_active}")
                        print(f"      是否超级用户: {user.is_superuser}")
                        print(f"      所有角色: {', '.join(roles_list)}")
                
                print("-" * 70)
            
            print("\n" + "=" * 70)
            print("  查询完成")
            print("=" * 70)
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 查询角色失败: {e}", exc_info=True)
            print(f"\n[ERROR] 查询失败: {e}")
            return False


async def main():
    """主函数"""
    try:
        await query_all_roles()
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

