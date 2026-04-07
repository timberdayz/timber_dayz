#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询管理员用户信息脚本

查询超级管理员和系统管理员的用户信息（用户名、邮箱等）
注意：密码是哈希存储的，无法直接查看，如需重置密码请使用重置脚本
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


async def query_admin_users():
    """查询管理员用户信息"""
    async with AsyncSessionLocal() as db:
        try:
            # 查询超级管理员角色（role_name 包含"超级管理员"或 role_code 为 "super_admin"）
            result = await db.execute(
                select(DimRole)
                .where(
                    (DimRole.role_name.like("%超级管理员%")) |
                    (DimRole.role_code == "super_admin") |
                    (DimRole.role_code == "super_administrator")
                )
            )
            super_admin_role = result.scalar_one_or_none()
            
            # 查询系统管理员角色（role_name 包含"系统管理员"或 role_code 为 "admin"）
            result = await db.execute(
                select(DimRole)
                .where(
                    (DimRole.role_name.like("%系统管理员%")) |
                    (DimRole.role_code == "admin")
                )
            )
            system_admin_role = result.scalar_one_or_none()
            
            print("=" * 70)
            print("  查询管理员用户信息")
            print("=" * 70)
            
            # 查询超级管理员用户
            if super_admin_role:
                print(f"\n[超级管理员角色] {super_admin_role.role_name} (role_code: {super_admin_role.role_code})")
                result = await db.execute(
                    select(DimUser)
                    .options(selectinload(DimUser.roles))
                    .join(DimUser.roles)
                    .where(DimRole.role_id == super_admin_role.role_id)
                )
                super_users = result.unique().scalars().all()
                
                if super_users:
                    for user in super_users:
                        await db.refresh(user, ["roles"])
                        roles_list = [role.role_name for role in user.roles]
                        print(f"  用户名: {user.username}")
                        print(f"  邮箱: {user.email}")
                        print(f"  姓名: {user.full_name or '未设置'}")
                        print(f"  状态: {user.status}")
                        print(f"  是否激活: {user.is_active}")
                        print(f"  是否超级用户: {user.is_superuser}")
                        print(f"  角色: {', '.join(roles_list)}")
                        print(f"  创建时间: {user.created_at}")
                        print(f"  注意: 密码是哈希存储的，无法直接查看")
                        print("-" * 70)
                else:
                    print("  未找到超级管理员用户")
            else:
                print("\n[超级管理员角色] 未找到超级管理员角色")
            
            # 查询系统管理员用户
            if system_admin_role:
                print(f"\n[系统管理员角色] {system_admin_role.role_name} (role_code: {system_admin_role.role_code})")
                result = await db.execute(
                    select(DimUser)
                    .options(selectinload(DimUser.roles))
                    .join(DimUser.roles)
                    .where(DimRole.role_id == system_admin_role.role_id)
                )
                system_users = result.unique().scalars().all()
                
                if system_users:
                    for user in system_users:
                        await db.refresh(user, ["roles"])
                        roles_list = [role.role_name for role in user.roles]
                        print(f"  用户名: {user.username}")
                        print(f"  邮箱: {user.email}")
                        print(f"  姓名: {user.full_name or '未设置'}")
                        print(f"  状态: {user.status}")
                        print(f"  是否激活: {user.is_active}")
                        print(f"  是否超级用户: {user.is_superuser}")
                        print(f"  角色: {', '.join(roles_list)}")
                        print(f"  创建时间: {user.created_at}")
                        print(f"  注意: 密码是哈希存储的，无法直接查看")
                        print("-" * 70)
                else:
                    print("  未找到系统管理员用户")
            else:
                print("\n[系统管理员角色] 未找到系统管理员角色")
            
            # 如果没有找到角色，尝试通过 is_superuser 标志查找
            if not super_admin_role or not system_admin_role:
                print("\n[备用查询] 通过 is_superuser 标志查找管理员用户")
                result = await db.execute(
                    select(DimUser)
                    .options(selectinload(DimUser.roles))
                    .where(DimUser.is_superuser == True)
                )
                superuser_list = result.scalars().all()
                
                if superuser_list:
                    for user in superuser_list:
                        await db.refresh(user, ["roles"])
                        roles_list = [role.role_name for role in user.roles]
                        print(f"  用户名: {user.username}")
                        print(f"  邮箱: {user.email}")
                        print(f"  姓名: {user.full_name or '未设置'}")
                        print(f"  状态: {user.status}")
                        print(f"  是否激活: {user.is_active}")
                        print(f"  是否超级用户: {user.is_superuser}")
                        print(f"  角色: {', '.join(roles_list) if roles_list else '未分配角色'}")
                        print(f"  创建时间: {user.created_at}")
                        print(f"  注意: 密码是哈希存储的，无法直接查看")
                        print("-" * 70)
                else:
                    print("  未找到超级用户")
            
            print("\n" + "=" * 70)
            print("  查询完成")
            print("=" * 70)
            print("\n[提示] 密码是哈希存储的（bcrypt），无法直接查看原始密码")
            print("[提示] 如需重置密码，请联系系统管理员或使用密码重置功能")
            print("=" * 70)
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 查询管理员用户失败: {e}", exc_info=True)
            print(f"\n[ERROR] 查询失败: {e}")
            return False


async def main():
    """主函数"""
    try:
        await query_admin_users()
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

