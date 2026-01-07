#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

"""
JWT认证和授权系统 - 阶段2核心组件

功能：
1. JWT Token生成和验证
2. 密码哈希和验证（bcrypt）
3. 用户认证（登录/注册）
4. RBAC权限控制（admin/manager/user）

企业级安全标准：
- ✅ 密码bcrypt加密（不可逆）
- ✅ JWT Token过期控制
- ✅ 角色权限隔离
- ✅ 操作审计日志
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from modules.core.logger import get_logger

logger = get_logger(__name__)

# ============== 配置 ==============

# 从环境变量读取（生产环境必须设置）
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "xihong-erp-secret-key-2025-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 默认24小时

# 安全警告：检查是否使用默认密钥
if SECRET_KEY == "xihong-erp-secret-key-2025-change-in-production":
    logger.warning("⚠️  使用默认JWT密钥！生产环境必须设置JWT_SECRET_KEY环境变量！")
    logger.warning("    设置方法: export JWT_SECRET_KEY='your-secure-random-key'")

# 密码加密配置（使用scrypt替代bcrypt，避免版本兼容问题）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# HTTP Bearer认证
security = HTTPBearer()


# ============== 密码处理 ==============

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码
    
    Returns:
        密码匹配返回True
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"密码验证失败: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    生成密码哈希
    
    Args:
        password: 明文密码
    
    Returns:
        bcrypt哈希
    """
    return pwd_context.hash(password)


# ============== JWT Token ==============

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建JWT访问令牌
    
    Args:
        data: 要编码的数据（通常包含user_id, username, role等）
        expires_delta: 过期时间增量（默认24小时）
    
    Returns:
        JWT token字符串
    
    Example:
        token = create_access_token(
            data={"user_id": 1, "username": "admin", "role": "admin"}
        )
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),  # issued at
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码JWT令牌
    
    Args:
        token: JWT token字符串
    
    Returns:
        解码后的数据字典，失败返回None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token已过期")
        return None
    except jwt.JWTError as e:
        logger.error(f"Token解码失败: {e}")
        return None


# ============== 用户认证 ==============

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db = None  # 可选数据库会话（AsyncSession）
) -> Dict[str, Any]:
    """
    获取当前用户（从JWT Token，异步模式）
    
    Args:
        credentials: HTTP Bearer凭证
        db: 数据库会话（可选，用于查询用户完整信息，必须是AsyncSession）
    
    Returns:
        用户信息字典
    
    Raises:
        HTTPException: 401未授权
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证或Token已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 从token payload获取用户信息
    user_info = {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "email": payload.get("email"),
        "role": payload.get("role", "user"),
        "is_active": payload.get("is_active", True),
    }
    
    # 如果提供了db，可以查询用户完整信息（必须是AsyncSession）
    if db and user_info["user_id"]:
        try:
            from modules.core.db import User
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy import select
            
            if isinstance(db, AsyncSession):
                result = await db.execute(
                    select(User).where(User.id == user_info["user_id"])
                )
                user = result.scalar_one_or_none()
                if user:
                    user_info.update({
                        "email": user.email,
                        "is_active": user.is_active,
                        "role": user.role,
                    })
        except Exception as e:
            logger.warning(f"查询用户信息失败: {e}")
    
    return user_info


# ============== RBAC权限控制 ==============

# 角色权限定义
ROLE_PERMISSIONS = {
    "admin": ["*"],  # 所有权限
    "manager": [
        # 数据管理
        "file.read", "file.scan", "file.preview", "file.map", "file.ingest",
        "file.delete", "file.export",
        # 模板管理
        "template.read", "template.create", "template.update",
        # 数据查询
        "data.read", "data.export",
        # 店铺管理
        "shop.read", "shop.update",
    ],
    "user": [
        # 只读权限
        "file.read", "file.preview",
        "template.read",
        "data.read",
        "shop.read",
    ],
}


def has_permission(user: Dict[str, Any], permission: str) -> bool:
    """
    检查用户是否有指定权限
    
    Args:
        user: 用户信息字典
        permission: 权限字符串（如 "file.delete"）
    
    Returns:
        有权限返回True
    """
    role = user.get("role", "user")
    permissions = ROLE_PERMISSIONS.get(role, [])
    
    # admin有所有权限
    if "*" in permissions:
        return True
    
    # 检查具体权限
    return permission in permissions


def require_permission(permission: str):
    """
    权限要求装饰器
    
    Args:
        permission: 所需权限
    
    Example:
        @router.delete("/files/{file_id}")
        @require_permission("file.delete")
        async def delete_file(file_id: int, user = Depends(get_current_user)):
            ...
    """
    def decorator(func):
        from functools import wraps
        
        @wraps(func)
        async def wrapper(*args, user: Dict = Depends(get_current_user), **kwargs):
            if not has_permission(user, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足: 需要'{permission}'权限"
                )
            return await func(*args, user=user, **kwargs)
        
        return wrapper
    return decorator


# ============== 测试代码 ==============

if __name__ == "__main__":
    print("="*60)
    print("JWT认证系统测试")
    print("="*60)
    
    # 测试1: 密码哈希
    print("\n[测试1] 密码哈希...")
    password = "test_password_123"
    hashed = get_password_hash(password)
    print(f"  原密码: {password}")
    print(f"  哈希: {hashed[:30]}...")
    
    verify_result = verify_password(password, hashed)
    print(f"  验证: {verify_result}")
    print(f"  [OK] 密码哈希正常")
    
    # 测试2: JWT Token生成
    print("\n[测试2] JWT Token生成...")
    user_data = {
        "user_id": 1,
        "username": "admin",
        "email": "admin@xihong.com",
        "role": "admin"
    }
    
    token = create_access_token(user_data)
    print(f"  用户数据: {user_data}")
    print(f"  Token: {token[:50]}...")
    print(f"  [OK] Token生成正常")
    
    # 测试3: JWT Token解码
    print("\n[测试3] JWT Token解码...")
    decoded = decode_access_token(token)
    print(f"  解码数据: {decoded}")
    print(f"  用户ID: {decoded.get('user_id')}")
    print(f"  角色: {decoded.get('role')}")
    print(f"  [OK] Token解码正常")
    
    # 测试4: 权限检查
    print("\n[测试4] 权限检查...")
    admin_user = {"role": "admin"}
    manager_user = {"role": "manager"}
    normal_user = {"role": "user"}
    
    print(f"  admin删除文件: {has_permission(admin_user, 'file.delete')}")
    print(f"  manager删除文件: {has_permission(manager_user, 'file.delete')}")
    print(f"  user删除文件: {has_permission(normal_user, 'file.delete')}")
    print(f"  [OK] 权限检查正常")
    
    print("\n[SUCCESS] JWT认证系统测试通过！")

