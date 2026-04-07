#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生产环境 Day-1 Bootstrap 脚本

用于在生产部署时自动初始化系统：
- 验证环境变量（CRLF检查）
- 创建基础角色（如果不存在）
- 可选：创建管理员账号（需显式启用）

特性：
- 幂等执行：可重复运行，无副作用
- 事务原子性：所有操作在单个事务中执行
- 并发安全：使用数据库唯一约束保护
"""

import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, text
from backend.models.database import AsyncSessionLocal
from modules.core.db import DimUser, DimRole
from backend.services.auth_service import auth_service
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 基础角色定义
BASELINE_ROLES = [
    {
        "role_code": "admin",
        "role_name": "管理员",
        "description": "系统管理员，拥有所有系统权限，包括用户审批、系统配置、数据管理等",
        "is_system": True,
    },
    {
        "role_code": "manager",
        "role_name": "主管",
        "description": "部门主管，拥有业务管理、审批和配置权限，可管理账号、目标、采购、报表等",
        "is_system": False,
    },
    {
        "role_code": "operator",
        "role_name": "操作员",
        "description": "日常操作人员，拥有基础业务操作权限，可进行数据同步、订单处理等日常操作",
        "is_system": False,
    },
    {
        "role_code": "finance",
        "role_name": "财务",
        "description": "财务人员，拥有财务和销售数据查看权限，可进行财务管理和报表查看",
        "is_system": False,
    },
]


def validate_environment_variables():
    """
    验证关键环境变量（检查CRLF和必需变量）
    
    Returns:
        bool: 验证是否通过
    """
    logger.info("[INFO] Validating environment variables...")
    
    # 关键环境变量列表
    critical_vars = [
        "DATABASE_URL",
        "SECRET_KEY",
        "JWT_SECRET_KEY",
    ]
    
    # 检查必需变量是否存在
    missing_vars = []
    crlf_issues = []
    
    for var_name in critical_vars:
        value = os.getenv(var_name)
        if not value:
            missing_vars.append(var_name)
            continue
        
        # 检查是否包含 CRLF
        if "\r" in value:
            crlf_issues.append(var_name)
            logger.error(f"[FAIL] Environment variable {var_name} contains CRLF (\\r) character")
    
    # 验证生产环境禁止默认占位符
    forbidden_defaults = {
        "SECRET_KEY": ["xihong-erp-secret-key-2025", "your-secret-key-change-this", "change-me"],
        "JWT_SECRET_KEY": ["xihong-erp-jwt-secret-2025", "your-jwt-secret-change-this", "change-me"],
    }
    
    default_value_issues = []
    for var_name, defaults in forbidden_defaults.items():
        value = os.getenv(var_name, "")
        if value in defaults:
            default_value_issues.append(var_name)
            logger.error(f"[FAIL] Environment variable {var_name} uses forbidden default value")
    
    # 汇总错误
    if missing_vars:
        logger.error(f"[FAIL] Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    if crlf_issues:
        logger.error(f"[FAIL] Environment variables with CRLF issues: {', '.join(crlf_issues)}")
        logger.error("[INFO] Please clean .env file before deployment")
        return False
    
    if default_value_issues:
        logger.error(f"[FAIL] Environment variables using default placeholders: {', '.join(default_value_issues)}")
        logger.error("[INFO] Production environment must use strong random secrets")
        return False
    
    # 输出验证通过信息（掩码形式）
    for var_name in critical_vars:
        value = os.getenv(var_name, "")
        if value:
            masked_value = f"{value[:2]}***{value[-2:]}" if len(value) > 4 else "***"
            logger.info(f"[INFO] {var_name} is set (length: {len(value)}, masked: {masked_value})")
    
    logger.info("[OK] Environment variables validation passed")
    return True


async def check_existing_admin(db: AsyncSession) -> bool:
    """
    检查是否存在管理员账号
    
    管理员判定标准（任一满足即可）：
    - is_superuser = True
    - 绑定了 role_code == "admin" 的角色
    - 绑定了 role_name == "admin" 的角色
    
    Returns:
        bool: True if admin exists, False otherwise
    """
    # 方法1：检查 is_superuser
    result = await db.execute(
        select(DimUser).where(DimUser.is_superuser == True).limit(1)
    )
    if result.scalar_one_or_none():
        logger.info("[INFO] Found existing superuser (is_superuser=True)")
        return True
    
    # 方法2：检查角色绑定
    result = await db.execute(
        select(DimUser)
        .join(DimUser.roles)
        .where(
            or_(
                DimRole.role_code == "admin",
                DimRole.role_name == "admin"
            )
        )
        .limit(1)
    )
    if result.scalar_one_or_none():
        logger.info("[INFO] Found existing admin user (bound to admin role)")
        return True
    
    return False


async def create_baseline_roles(db: AsyncSession):
    """
    创建基础角色（如果不存在）
    
    幂等操作：如果角色已存在，跳过创建
    """
    logger.info("[INFO] Creating baseline roles...")
    
    created_count = 0
    skipped_count = 0
    
    for role_data in BASELINE_ROLES:
        role_code = role_data["role_code"]
        
        # 检查角色是否已存在
        result = await db.execute(
            select(DimRole).where(DimRole.role_code == role_code)
        )
        existing_role = result.scalar_one_or_none()
        
        if existing_role:
            logger.info(f"[INFO] Role '{role_code}' already exists, skipping")
            skipped_count += 1
            continue
        
        # 创建新角色
        new_role = DimRole(
            role_code=role_code,
            role_name=role_data["role_name"],
            description=role_data["description"],
            permissions="[]",  # 默认空权限列表
            is_active=True,
            is_system=role_data["is_system"]
        )
        db.add(new_role)
        logger.info(f"[INFO] Created role '{role_code}' ({role_data['role_name']})")
        created_count += 1
    
    await db.flush()  # 刷新到数据库但不提交
    
    logger.info(f"[OK] Baseline roles: {created_count} created, {skipped_count} skipped")


async def create_admin_user_if_needed(db: AsyncSession):
    """
    创建管理员账号（如果启用且不存在）
    
    安全边界：
    - 默认关闭（需要显式启用）
    - 仅在无任何 superuser 时允许创建
    - 密码必须来自环境变量（不能使用默认值）
    """
    # 检查是否启用管理员创建
    create_admin = os.getenv("BOOTSTRAP_CREATE_ADMIN", "false").lower() == "true"
    if not create_admin:
        logger.info("[INFO] Admin creation is disabled (BOOTSTRAP_CREATE_ADMIN=false), skipping")
        return
    
    logger.info("[INFO] Admin creation is enabled, checking prerequisites...")
    
    # 检查是否已存在管理员
    if await check_existing_admin(db):
        logger.info("[INFO] Admin user already exists, skipping creation (safe-by-default)")
        return
    
    # 获取管理员创建参数
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@xihong.com")
    
    # 验证密码是否设置
    if not password:
        logger.error("[FAIL] BOOTSTRAP_ADMIN_PASSWORD is required but not set")
        raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be set when BOOTSTRAP_CREATE_ADMIN=true")
    
    # 验证密码不是默认值
    if password in ["admin", "password", "123456", "change-me"]:
        logger.error("[FAIL] BOOTSTRAP_ADMIN_PASSWORD must not use default/common passwords")
        raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be a strong password")
    
    # 检查用户名是否已存在
    result = await db.execute(
        select(DimUser).where(DimUser.username == username)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        logger.warning(f"[WARN] Username '{username}' already exists, skipping admin creation")
        return
    
    # 创建管理员用户
    user = DimUser(
        username=username,
        email=email,
        password_hash=auth_service.hash_password(password),
        full_name="System Administrator",
        status="active",
        is_active=True,
        is_superuser=True
    )
    db.add(user)
    await db.flush()  # 获取 user_id
    
    # 分配 admin 角色
    result = await db.execute(
        select(DimRole).where(DimRole.role_code == "admin")
    )
    admin_role = result.scalar_one_or_none()
    
    if not admin_role:
        logger.error("[FAIL] Admin role not found, cannot assign role to admin user")
        raise ValueError("Admin role must exist before creating admin user")
    
    # 使用 SQL 直接插入关联（避免懒加载问题）
    # 注意：user_roles 表使用复合主键 (user_id, role_id)，ON CONFLICT 需要指定主键
    await db.execute(
        text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT (user_id, role_id) DO NOTHING"),
        {"user_id": user.user_id, "role_id": admin_role.role_id}
    )
    
    logger.info(f"[OK] Admin user '{username}' created successfully")
    logger.info(f"[INFO] Admin user ID: {user.user_id}, Email: {email}")


async def verify_bootstrap(db: AsyncSession):
    """
    验证 Bootstrap 结果
    
    检查：
    - 关键表存在
    - 基础角色存在
    - 管理员记录存在（如果启用创建）
    """
    logger.info("[INFO] Verifying bootstrap results...")
    
    # 验证基础角色
    required_role_codes = [role["role_code"] for role in BASELINE_ROLES]
    result = await db.execute(
        select(DimRole).where(DimRole.role_code.in_(required_role_codes))
    )
    roles = result.scalars().all()
    found_role_codes = {role.role_code for role in roles}
    missing_roles = set(required_role_codes) - found_role_codes
    
    if missing_roles:
        logger.error(f"[FAIL] Missing required roles: {', '.join(missing_roles)}")
        raise ValueError(f"Bootstrap verification failed: missing roles {missing_roles}")
    
    logger.info(f"[OK] All required roles exist: {', '.join(sorted(found_role_codes))}")
    
    # 验证管理员（如果启用创建）
    create_admin = os.getenv("BOOTSTRAP_CREATE_ADMIN", "false").lower() == "true"
    if create_admin:
        has_admin = await check_existing_admin(db)
        if not has_admin:
            logger.warning("[WARN] Admin creation was enabled but no admin user found")
        else:
            logger.info("[OK] Admin user verification passed")


async def main():
    """
    Bootstrap 主函数
    
    执行顺序：
    1. 验证环境变量（CRLF检查）
    2. 创建基础角色（如果不存在）
    3. 创建管理员（如果启用且不存在）
    4. 验证 Bootstrap 结果
    """
    logger.info("[INFO] Starting production bootstrap...")
    
    # 步骤1：验证环境变量
    if not validate_environment_variables():
        raise ValueError("Environment variable validation failed")
    
    # 步骤2-4：数据库操作（在事务中执行）
    async with AsyncSessionLocal() as db:
        try:
            # 步骤2：创建基础角色
            await create_baseline_roles(db)
            
            # 步骤3：创建管理员（如果启用）
            await create_admin_user_if_needed(db)
            
            # 步骤4：验证结果
            await verify_bootstrap(db)
            
            # 提交事务
            await db.commit()
            logger.info("[OK] Bootstrap completed successfully")
            
        except Exception as e:
            # 回滚事务
            await db.rollback()
            logger.error(f"[FAIL] Bootstrap failed: {type(e).__name__}: {str(e)}")
            raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
        sys.exit(0)  # 成功退出
    except Exception as e:
        # 输出诊断信息（不含敏感信息）
        print(f"[FAIL] Bootstrap failed: {type(e).__name__}: {str(e)}")
        sys.exit(1)  # 失败退出，部署流程会检测到非零退出码
